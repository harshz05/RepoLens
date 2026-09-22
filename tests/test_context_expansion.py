import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.session import init_db, AsyncSessionLocal
from packages.db.models import Repository, RepositoryVersion, File, Symbol, Dependency, CodeChunk
from packages.code_intel.models import RankedChunk
from packages.code_intel.retrieval.context_expansion import ContextExpander

@pytest.mark.asyncio
async def test_ast_dependency_context_expansion():
    await init_db()
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        repo = Repository(
            github_url=f"https://github.com/repolens/test-expansion-{suffix}",
            owner=f"repolens_{suffix}",
            name=f"test-expansion-{suffix}",
            default_branch="main",
        )
        session.add(repo)
        await session.flush()

        ver = RepositoryVersion(
            repository_id=repo.id,
            commit_hash="graphctx123",
            branch="main",
            status="COMPLETED",
        )
        session.add(ver)
        await session.flush()

        file_rec = File(
            repository_version_id=ver.id,
            path="services/pipeline.py",
            language="python",
            line_count=60,
            byte_size=1500,
            sha256_hash="hash3",
        )
        session.add(file_rec)
        await session.flush()

        sym_caller = Symbol(
            file_id=file_rec.id,
            name="api_handler",
            fully_qualified_name="api.routes.api_handler",
            kind="function",
            start_line=1,
            end_line=10,
            start_col=0,
            end_col=20,
        )
        sym_target = Symbol(
            file_id=file_rec.id,
            name="execute_pipeline",
            fully_qualified_name="services.pipeline.execute_pipeline",
            kind="function",
            start_line=15,
            end_line=30,
            start_col=0,
            end_col=25,
        )
        sym_callee = Symbol(
            file_id=file_rec.id,
            name="run_step",
            fully_qualified_name="utils.runner.run_step",
            kind="function",
            start_line=35,
            end_line=45,
            start_col=0,
            end_col=15,
        )
        session.add_all([sym_caller, sym_target, sym_callee])
        await session.flush()

        # Upstream edge: sym_caller calls sym_target
        dep_in = Dependency(
            caller_symbol_id=sym_caller.id,
            callee_symbol_id=sym_target.id,
            dependency_type="call",
            file_id=file_rec.id,
            line_number=5,
        )
        # Downstream edge: sym_target calls sym_callee
        dep_out = Dependency(
            caller_symbol_id=sym_target.id,
            callee_symbol_id=sym_callee.id,
            dependency_type="call",
            file_id=file_rec.id,
            line_number=20,
        )
        session.add_all([dep_in, dep_out])
        await session.commit()

        # Create sample RankedChunk targeting execute_pipeline
        chunk = RankedChunk(
            chunk_id="chunk-1",
            file_id=file_rec.id,
            file_path="services/pipeline.py",
            language="python",
            start_line=15,
            end_line=30,
            content="def execute_pipeline(): pass",
            score=0.95,
            match_type="semantic",
            symbol_id=sym_target.id,
            symbol_fqn="services.pipeline.execute_pipeline",
            symbol_kind="function",
        )

        expanded = await ContextExpander.expand_chunks(session=session, chunks=[chunk])
        assert len(expanded) == 1
        assert expanded[0].graph_context is not None

        g_ctx = expanded[0].graph_context
        assert any("api.routes.api_handler" in c for c in g_ctx.callers)
        assert any("utils.runner.run_step" in c for c in g_ctx.callees)
