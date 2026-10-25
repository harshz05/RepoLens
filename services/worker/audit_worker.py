import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.db.models import (
    AuditRun,
    RepositoryVersion,
    File,
    FileContent,
    Symbol,
    Dependency,
    SecurityFinding,
    QualityFinding,
)
from packages.code_intel.models import (
    ExtractedSymbol,
    ResolvedDependency,
    ExtractedFileContext,
)
from packages.code_intel.parsers.registry import parser_registry
from packages.code_intel.security.registry import security_registry
from packages.code_intel.security.graph_analyzer import GraphSecurityAnalyzer
from packages.code_intel.quality.complexity import CyclomaticComplexityCalculator
from packages.code_intel.quality.metrics import CodeMetricsAnalyzer, QualityFindingData
from packages.code_intel.quality.coupling import CouplingAnalyzer
from packages.code_intel.audit.health_score import HealthScoreCalculator
from packages.code_intel.audit.ai_advisor import AIAuditAdvisor
from services.worker.ingestion_worker import EventBroker

logger = logging.getLogger(__name__)

FILE_BATCH_SIZE = 100  # files loaded per DB round-trip (bounds memory on large repos)


def _load_metadata(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


async def emit_audit_progress(
    session: AsyncSession,
    audit_run: AuditRun,
    step: str,
    progress: float,
    details: str,
):
    """Update AuditRun DB record and broadcast live progress event via EventBroker."""
    audit_run.current_step = step
    audit_run.progress_percentage = progress
    audit_run.step_details = details
    await session.commit()

    event_payload = {
        "audit_run_id": audit_run.id,
        "step": step,
        "progress": progress,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    EventBroker.publish(audit_run.id, event_payload)

async def run_audit_pipeline(
    audit_run_id: str,
    session: AsyncSession,
    enable_ai_review: bool = True,
) -> None:
    """
    Main asynchronous repository security and code quality audit pipeline.
    Stages:
    QUEUED -> STATIC_SECURITY -> AST_SECURITY -> GRAPH_SECURITY -> QUALITY_ANALYSIS -> AI_REVIEW -> AGGREGATION -> COMPLETED
    """
    stmt = select(AuditRun).where(AuditRun.id == audit_run_id)
    res = await session.execute(stmt)
    audit_run = res.scalar_one_or_none()
    if not audit_run:
        return

    audit_run.status = "IN_PROGRESS"
    audit_run.started_at = datetime.now(timezone.utc)
    await emit_audit_progress(session, audit_run, "INITIALIZING", 5.0, "Loading repository AST and dependency graphs...")

    try:
        ver_stmt = select(RepositoryVersion).where(RepositoryVersion.id == audit_run.repository_version_id)
        ver_res = await session.execute(ver_stmt)
        version = ver_res.scalar_one()

        # Load all Files, Symbols, Dependencies
        file_stmt = select(File).where(File.repository_version_id == version.id)
        file_res = await session.execute(file_stmt)
        files = file_res.scalars().all()
        file_map = {f.path: f for f in files}
        file_id_map = {f.id: f for f in files}

        if not files:
            audit_run.status = "FAILED"
            audit_run.error_log = "No indexed files found for this repository version."
            await emit_audit_progress(session, audit_run, "FAILED", 0.0, "No files found to audit.")
            return

        file_ids = list(file_id_map.keys())

        sym_stmt = select(Symbol).where(Symbol.file_id.in_(file_ids))
        sym_res = await session.execute(sym_stmt)
        symbols = sym_res.scalars().all()
        sym_map = {s.fully_qualified_name: s for s in symbols}
        sym_id_map = {s.id: s for s in symbols}

        dep_stmt = select(Dependency).where(Dependency.file_id.in_(file_ids))
        dep_res = await session.execute(dep_stmt)
        dependencies = dep_res.scalars().all()

        total_loc = sum(f.line_count for f in files)

        # Reconstruct ExtractedSymbol and ResolvedDependency objects
        extracted_symbols: List[ExtractedSymbol] = []
        for s in symbols:
            f_obj = file_id_map.get(s.file_id)
            f_path = f_obj.path if f_obj else ""
            extracted_symbols.append(
                ExtractedSymbol(
                    name=s.name,
                    fully_qualified_name=s.fully_qualified_name,
                    kind=s.kind,
                    start_line=s.start_line,
                    end_line=s.end_line,
                    start_col=s.start_col,
                    end_col=s.end_col,
                    signature=s.signature,
                    docstring=s.docstring,
                    file_path=f_path,
                    metadata=_load_metadata(s.metadata_json),
                )
            )

        # Group once: avoids O(files x symbols) filtering inside the file loop
        symbols_by_path: Dict[str, List[ExtractedSymbol]] = {}
        for es in extracted_symbols:
            symbols_by_path.setdefault(es.file_path or "", []).append(es)

        resolved_deps: List[ResolvedDependency] = []
        for d in dependencies:
            c_sym = sym_id_map.get(d.caller_symbol_id)
            t_sym = sym_id_map.get(d.callee_symbol_id)
            f_obj = file_id_map.get(d.file_id)
            if c_sym and t_sym:
                resolved_deps.append(
                    ResolvedDependency(
                        caller_symbol_id=d.caller_symbol_id,
                        callee_symbol_id=d.callee_symbol_id,
                        caller_fqn=c_sym.fully_qualified_name,
                        callee_fqn=t_sym.fully_qualified_name,
                        dependency_type=d.dependency_type,
                        file_id=d.file_id,
                        file_path=f_obj.path if f_obj else "",
                        line_number=d.line_number,
                    )
                )

        # Stage 1 & 2: Security Analysis (Static & AST)
        await emit_audit_progress(
            session,
            audit_run,
            "SECURITY_ANALYSIS",
            20.0,
            f"Executing {len(security_registry.all_rules)} security rules across {len(files)} files...",
        )

        raw_security_findings = []
        rule_errors: List[dict] = []  # rules that crashed (reported in the audit summary, never silent)
        quality_findings: List[QualityFindingData] = []

        # Source is loaded in batches from file_contents (original text, exact line numbers).
        files_scanned = 0
        files_missing_source = 0

        for batch_start in range(0, len(files), FILE_BATCH_SIZE):
            batch = files[batch_start:batch_start + FILE_BATCH_SIZE]
            content_res = await session.execute(
                select(FileContent).where(FileContent.file_id.in_([bf.id for bf in batch]))
            )
            content_map = {c.file_id: c.content for c in content_res.scalars().all()}

            for f in batch:
                code_text = content_map.get(f.id)
                if code_text is None:
                    files_missing_source += 1
                    continue
                files_scanned += 1
                code_bytes = code_text.encode("utf-8", errors="ignore")

                # Re-parse the original source: gives rules real call references + symbol metadata
                parsed_ctx = parser_registry.parse_file(code_bytes, f.path)
                f_symbols = symbols_by_path.get(f.path, [])
                f_ctx = ExtractedFileContext(
                    file_path=f.path,
                    language=f.language,
                    symbols=f_symbols,
                    calls=parsed_ctx.calls if parsed_ctx else [],
                    imports=parsed_ctx.imports if parsed_ctx else [],
                )

                # Security scan
                f_findings = security_registry.scan_file(
                    code_text=code_text,
                    file_path=f.path,
                    language=f.language,
                    context=f_ctx,
                    errors=rule_errors,
                )
                raw_security_findings.extend(f_findings)

                # Quality metrics per file
                file_qual = CodeMetricsAnalyzer.analyze_file_metrics(
                    code_text=code_text,
                    file_path=f.path,
                    language=f.language,
                    context=f_ctx,
                )
                quality_findings.extend(file_qual)

                # Complexity calculation per function
                cc_results = CyclomaticComplexityCalculator.calculate_for_symbols(
                    code_bytes=code_bytes,
                    file_path=f.path,
                    language=f.language,
                )
                for fn_name, s_line, e_line, cc in cc_results:
                    if cc > 10:
                        sev = "CRITICAL" if cc > 30 else ("HIGH" if cc > 20 else "MEDIUM")
                        quality_findings.append(
                            QualityFindingData(
                                rule_id="QUAL-001",
                                metric_name="cyclomatic_complexity",
                                title=f"High Cyclomatic Complexity ({fn_name}: {cc})",
                                description=f"Function '{fn_name}' has cyclomatic complexity of {cc} (threshold: 10). High branching logic significantly increases defect density.",
                                severity=sev,
                                confidence=1.0,
                                value=float(cc),
                                threshold=10.0,
                                file_path=f.path,
                                start_line=s_line,
                                end_line=e_line,
                                recommendation="Refactor branching conditions into smaller polymorphic methods or lookup dispatch tables.",
                                symbol_fqn=f"{f.path}::{fn_name}",
                            )
                        )

        if files_scanned == 0:
            audit_run.status = "FAILED"
            audit_run.error_log = (
                "No stored source found for this repository version. "
                "Re-ingest the repository so original file contents are persisted."
            )
            await emit_audit_progress(session, audit_run, "FAILED", 0.0, audit_run.error_log)
            return
        if files_missing_source:
            logger.warning("Audit %s: %d files had no stored source and were skipped", audit_run.id, files_missing_source)

        # Stage 3: Graph Reachability Security Analysis
        await emit_audit_progress(
            session,
            audit_run,
            "GRAPH_SECURITY",
            50.0,
            f"Evaluating call-graph reachability for {len(raw_security_findings)} security findings...",
        )

        graph_analyzer = GraphSecurityAnalyzer(
            symbols=extracted_symbols,
            dependencies=resolved_deps,
        )
        enriched_security_findings = graph_analyzer.enrich_findings_with_graph_context(raw_security_findings)

        # Stage 4: Architectural Quality & Coupling Analysis
        await emit_audit_progress(
            session,
            audit_run,
            "QUALITY_ANALYSIS",
            70.0,
            "Computing coupling metrics, circular dependencies, and dead symbols...",
        )

        coupling_findings, coupling_metrics = CouplingAnalyzer.analyze_symbol_coupling(
            symbols=extracted_symbols,
            dependencies=resolved_deps,
        )
        quality_findings.extend(coupling_findings)
        circular_cycles = CouplingAnalyzer.detect_circular_dependencies(resolved_deps)

        # Stage 5: AI Review (Selective & Grounded)
        if enable_ai_review:
            await emit_audit_progress(
                session,
                audit_run,
                "AI_REVIEW",
                85.0,
                "Generating grounded remediation advice and architectural explanations...",
            )
            enriched_security_findings = await AIAuditAdvisor.review_findings(enriched_security_findings)

        # Stage 6: Aggregation & Health Scoring
        await emit_audit_progress(
            session,
            audit_run,
            "AGGREGATION",
            92.0,
            "Calculating 5-dimensional repository health metrics...",
        )

        health_matrix = HealthScoreCalculator.calculate(
            total_loc=total_loc,
            total_files=len(files),
            total_symbols=len(symbols),
            security_findings=enriched_security_findings,
            quality_findings=quality_findings,
            coupling_metrics=coupling_metrics,
            circular_cycles_count=len(circular_cycles),
        )

        audit_run.health_score = health_matrix.overall_health
        audit_run.security_score = health_matrix.security_score
        audit_run.maintainability_score = health_matrix.maintainability_score
        audit_run.complexity_score = health_matrix.complexity_score
        audit_run.coupling_score = health_matrix.coupling_score
        audit_run.architecture_score = health_matrix.architecture_score
        summary = dict(health_matrix.dimensions_summary)
        summary["security_rule_errors"] = len(rule_errors)
        if rule_errors:
            summary["security_rule_error_samples"] = rule_errors[:5]
        audit_run.summary_metrics_json = json.dumps(summary)

        # Persist Security Findings
        for sf in enriched_security_findings:
            f_rec = file_map.get(sf.file_path)
            if not f_rec:
                continue
            sym_rec = sym_map.get(sf.symbol_fqn) if sf.symbol_fqn else None

            db_sf = SecurityFinding(
                audit_run_id=audit_run.id,
                file_id=f_rec.id,
                symbol_id=sym_rec.id if sym_rec else None,
                rule_id=sf.rule_id,
                category=sf.category,
                severity=sf.severity.value,
                confidence=sf.confidence,
                detection_source=sf.detection_source.value,
                start_line=sf.start_line,
                end_line=sf.end_line,
                title=sf.title,
                description=sf.description,
                evidence=sf.evidence,
                remediation=sf.remediation,
                graph_reachability_path=sf.graph_reachability_path,
                is_ai_assisted=sf.is_ai_assisted,
            )
            session.add(db_sf)

        # Persist Quality Findings
        for qf in quality_findings:
            f_rec = file_map.get(qf.file_path)
            if not f_rec:
                continue
            sym_rec = sym_map.get(qf.symbol_fqn) if qf.symbol_fqn else None

            db_qf = QualityFinding(
                audit_run_id=audit_run.id,
                file_id=f_rec.id,
                symbol_id=sym_rec.id if sym_rec else None,
                rule_id=qf.rule_id,
                metric_name=qf.metric_name,
                title=qf.title,
                description=qf.description,
                severity=qf.severity,
                confidence=qf.confidence,
                detection_source="AST_ANALYSIS",
                value=qf.value,
                threshold=qf.threshold,
                start_line=qf.start_line,
                end_line=qf.end_line,
                recommendation=qf.recommendation,
                is_ai_assisted=False,
            )
            session.add(db_qf)

        audit_run.status = "COMPLETED"
        audit_run.completed_at = datetime.now(timezone.utc)
        await session.commit()

        await emit_audit_progress(
            session,
            audit_run,
            "COMPLETED",
            100.0,
            f"Audit completed successfully: Health Score {health_matrix.overall_health}/100 ({len(enriched_security_findings)} security, {len(quality_findings)} quality findings)",
        )

    except Exception as exc:
        audit_run.status = "FAILED"
        audit_run.error_log = str(exc)
        await emit_audit_progress(session, audit_run, "FAILED", 0.0, f"Audit error: {str(exc)}")