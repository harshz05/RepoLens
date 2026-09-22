"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Flame,
  CheckCircle2,
  RefreshCw,
  Search,
  Filter,
  ExternalLink,
  ChevronRight,
  Code2,
  Activity,
  Layers,
  Sparkles,
  ArrowRight,
  FileText,
  Lock,
  X,
  SlidersHorizontal,
} from "lucide-react";

interface DimensionsSummary {
  critical_security_findings?: number;
  high_security_findings?: number;
  medium_security_findings?: number;
  low_security_findings?: number;
  large_files_count?: number;
  large_functions_count?: number;
  high_complexity_functions?: number;
  circular_dependency_cycles?: number;
  average_fan_out?: number;
  ksloc?: number;
}

interface AuditSummary {
  id: string;
  repository_id: string;
  version_id: string;
  status: string;
  current_step: string;
  progress_percentage: number;
  step_details?: string;
  error_log?: string;
  health_score?: number;
  security_score?: number;
  maintainability_score?: number;
  complexity_score?: number;
  coupling_score?: number;
  architecture_score?: number;
  dimensions_summary?: DimensionsSummary;
  total_security_findings: number;
  total_quality_findings: number;
  started_at?: string;
  completed_at?: string;
}

interface SecurityFinding {
  id: string;
  rule_id: string;
  category: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  confidence: number;
  detection_source: string;
  file_path: string;
  start_line: number;
  end_line: number;
  title: string;
  description: string;
  evidence: string;
  remediation: string;
  symbol_name?: string;
  graph_reachability_path?: string;
  is_ai_assisted: boolean;
  created_at: string;
}

interface QualityFinding {
  id: string;
  rule_id: string;
  metric_name: string;
  title: string;
  description: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  confidence: number;
  detection_source: string;
  value: number;
  threshold: number;
  file_path: string;
  start_line: number;
  end_line: number;
  recommendation: string;
  symbol_name?: string;
  is_ai_assisted: boolean;
  created_at: string;
}

interface SecurityAuditDashboardProps {
  repositoryId: string;
  onNavigateToFile?: (filePath: string, startLine: number) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SecurityAuditDashboard({
  repositoryId,
  onNavigateToFile,
}: SecurityAuditDashboardProps) {
  const [audit, setAudit] = useState<AuditSummary | null>(null);
  const [securityFindings, setSecurityFindings] = useState<SecurityFinding[]>([]);
  const [qualityFindings, setQualityFindings] = useState<QualityFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAuditing, setIsAuditing] = useState(false);
  const [auditProgress, setAuditProgress] = useState<{ step: string; progress: number; details: string } | null>(null);

  // Active view toggle: 'security' vs 'quality'
  const [activeSubView, setActiveSubView] = useState<"security" | "quality">("security");

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Finding Drawer
  const [selectedSecurityFinding, setSelectedSecurityFinding] = useState<SecurityFinding | null>(null);
  const [selectedQualityFinding, setSelectedQualityFinding] = useState<QualityFinding | null>(null);

  // Fetch Latest Audit
  const fetchAuditData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/audit/latest`);
      if (res.ok) {
        const auditData: AuditSummary = await res.json();
        setAudit(auditData);

        // Fetch findings
        const [secRes, qualRes] = await Promise.all([
          fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/security/findings?audit_id=${auditData.id}&limit=100`),
          fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/quality/findings?audit_id=${auditData.id}&limit=100`),
        ]);

        if (secRes.ok) {
          const secData = await secRes.json();
          setSecurityFindings(secData);
        }
        if (qualRes.ok) {
          const qualData = await qualRes.json();
          setQualityFindings(qualData);
        }
      } else {
        setAudit(null);
        setSecurityFindings([]);
        setQualityFindings([]);
      }
    } catch (err) {
      console.error("Failed to fetch audit data:", err);
    } finally {
      setLoading(false);
    }
  }, [repositoryId]);

  useEffect(() => {
    fetchAuditData();
  }, [fetchAuditData]);

  // Trigger Audit
  const handleTriggerAudit = async () => {
    try {
      setIsAuditing(true);
      setAuditProgress({ step: "QUEUED", progress: 5, details: "Dispatching audit job..." });

      const res = await fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable_ai_review: true }),
      });

      if (!res.ok) {
        throw new Error("Failed to trigger audit");
      }

      const data = await res.json();
      const auditRunId = data.audit_run_id;

      // Connect SSE
      const evtSource = new EventSource(`${API_BASE}/api/v1/repositories/audit/events/${auditRunId}`);
      evtSource.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          setAuditProgress({
            step: msg.step,
            progress: msg.progress,
            details: msg.details,
          });

          if (msg.step === "COMPLETED" || msg.step === "FAILED") {
            evtSource.close();
            setIsAuditing(false);
            fetchAuditData();
          }
        } catch {
          // ignore parsing error
        }
      };

      evtSource.onerror = () => {
        evtSource.close();
        setIsAuditing(false);
        fetchAuditData();
      };
    } catch (err) {
      console.error("Audit error:", err);
      setIsAuditing(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
        return "bg-rose-500/20 text-rose-400 border-rose-500/40";
      case "HIGH":
        return "bg-amber-500/20 text-amber-400 border-amber-500/40";
      case "MEDIUM":
        return "bg-yellow-500/20 text-yellow-400 border-yellow-500/40";
      case "LOW":
        return "bg-sky-500/20 text-sky-400 border-sky-500/40";
      default:
        return "bg-gray-500/20 text-gray-400 border-gray-500/40";
    }
  };

  const getScoreColor = (score?: number) => {
    if (score === undefined || score === null) return "text-gray-400";
    if (score >= 80) return "text-emerald-400";
    if (score >= 60) return "text-amber-400";
    return "text-rose-400";
  };

  // Filter Security Findings
  const filteredSecurityFindings = securityFindings.filter((f) => {
    if (severityFilter !== "ALL" && f.severity !== severityFilter) return false;
    if (sourceFilter !== "ALL" && f.detection_source !== sourceFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        f.title.toLowerCase().includes(q) ||
        f.rule_id.toLowerCase().includes(q) ||
        f.file_path.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Filter Quality Findings
  const filteredQualityFindings = qualityFindings.filter((f) => {
    if (severityFilter !== "ALL" && f.severity !== severityFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        f.title.toLowerCase().includes(q) ||
        f.metric_name.toLowerCase().includes(q) ||
        f.file_path.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Top Banner & Health Scorecard */}
      <div className="glass-card rounded-2xl p-5 border border-obsidian-border bg-gradient-to-r from-obsidian-surface via-obsidian-surface to-indigo-950/20">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2.5">
              <ShieldAlert className="w-5 h-5 text-electric-indigo" />
              <h2 className="text-base font-bold text-white font-mono tracking-tight">
                Security & Code Quality Intelligence
              </h2>
              {audit?.status === "COMPLETED" && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-electric-emerald/15 text-electric-emerald border border-electric-emerald/30">
                  Audit Verified
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Deterministic static analysis, AST complexity inspection, call-graph reachability, and grounded Gemini advisory.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={handleTriggerAudit}
              disabled={isAuditing}
              className="px-4 py-2 rounded-xl bg-electric-indigo hover:bg-electric-indigo/80 text-white text-xs font-mono font-medium flex items-center space-x-2 transition shadow-glow disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isAuditing ? "animate-spin" : ""}`} />
              <span>{isAuditing ? "Auditing Repository..." : "Run Security & Quality Audit"}</span>
            </button>
          </div>
        </div>

        {/* Live Audit Progress Bar */}
        {isAuditing && auditProgress && (
          <div className="mt-4 pt-4 border-t border-obsidian-border/80">
            <div className="flex items-center justify-between text-xs font-mono mb-1.5">
              <span className="text-electric-indigo font-bold flex items-center space-x-1.5">
                <Activity className="w-3.5 h-3.5 animate-pulse" />
                <span>Stage: {auditProgress.step}</span>
              </span>
              <span className="text-gray-400">{auditProgress.progress}%</span>
            </div>
            <div className="w-full bg-obsidian-base h-2 rounded-full overflow-hidden border border-obsidian-border">
              <div
                className="bg-electric-indigo h-full transition-all duration-300 shadow-glow"
                style={{ width: `${auditProgress.progress}%` }}
              />
            </div>
            <div className="text-[11px] font-mono text-gray-400 mt-1">
              {auditProgress.details}
            </div>
          </div>
        )}

        {/* 5-Dimension Health Metrics Cards */}
        {audit?.status === "COMPLETED" && (
          <div className="mt-5 grid grid-cols-2 md:grid-cols-6 gap-2.5 pt-4 border-t border-obsidian-border">
            {/* Overall Health Card */}
            <div className="col-span-2 md:col-span-1 glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/60 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 tracking-wider">Health Score</div>
              <div className={`text-2xl font-bold font-mono mt-1 ${getScoreColor(audit.health_score)}`}>
                {audit.health_score ?? "N/A"}<span className="text-xs text-gray-500 font-normal">/100</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">Composite Matrix</div>
            </div>

            {/* Security Score */}
            <div className="glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/40 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 flex items-center justify-center space-x-1">
                <Lock className="w-2.5 h-2.5 text-rose-400" />
                <span>Security</span>
              </div>
              <div className={`text-xl font-bold font-mono mt-1 ${getScoreColor(audit.security_score)}`}>
                {audit.security_score ?? "N/A"}
              </div>
              <div className="text-[9px] text-gray-400 mt-0.5">
                {audit.total_security_findings} findings
              </div>
            </div>

            {/* Maintainability */}
            <div className="glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/40 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 flex items-center justify-center space-x-1">
                <Code2 className="w-2.5 h-2.5 text-sky-400" />
                <span>Maintain</span>
              </div>
              <div className={`text-xl font-bold font-mono mt-1 ${getScoreColor(audit.maintainability_score)}`}>
                {audit.maintainability_score ?? "N/A"}
              </div>
              <div className="text-[9px] text-gray-400 mt-0.5">SLOC & Modules</div>
            </div>

            {/* Complexity */}
            <div className="glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/40 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 flex items-center justify-center space-x-1">
                <Flame className="w-2.5 h-2.5 text-amber-400" />
                <span>Complexity</span>
              </div>
              <div className={`text-xl font-bold font-mono mt-1 ${getScoreColor(audit.complexity_score)}`}>
                {audit.complexity_score ?? "N/A"}
              </div>
              <div className="text-[9px] text-gray-400 mt-0.5">McCabe V(G)</div>
            </div>

            {/* Coupling */}
            <div className="glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/40 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 flex items-center justify-center space-x-1">
                <Layers className="w-2.5 h-2.5 text-purple-400" />
                <span>Coupling</span>
              </div>
              <div className={`text-xl font-bold font-mono mt-1 ${getScoreColor(audit.coupling_score)}`}>
                {audit.coupling_score ?? "N/A"}
              </div>
              <div className="text-[9px] text-gray-400 mt-0.5">Fan-in / Fan-out</div>
            </div>

            {/* Architecture */}
            <div className="glass-card p-3 rounded-xl border border-obsidian-border bg-obsidian-base/40 text-center">
              <div className="text-[10px] uppercase font-mono text-gray-400 flex items-center justify-center space-x-1">
                <Activity className="w-2.5 h-2.5 text-emerald-400" />
                <span>Architecture</span>
              </div>
              <div className={`text-xl font-bold font-mono mt-1 ${getScoreColor(audit.architecture_score)}`}>
                {audit.architecture_score ?? "N/A"}
              </div>
              <div className="text-[9px] text-gray-400 mt-0.5">
                {audit.dimensions_summary?.circular_dependency_cycles || 0} cycles
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main Workspace: Controls & Findings */}
      <div className="glass-card rounded-2xl p-5 border border-obsidian-border space-y-4">
        {/* Sub-view Switcher & Filters */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* View Toggle */}
          <div className="flex items-center space-x-1 bg-obsidian-base p-1 rounded-xl border border-obsidian-border text-xs font-mono">
            <button
              onClick={() => setActiveSubView("security")}
              className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition ${
                activeSubView === "security"
                  ? "bg-electric-indigo text-white font-bold shadow-glow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              <span>Security Findings ({securityFindings.length})</span>
            </button>
            <button
              onClick={() => setActiveSubView("quality")}
              className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition ${
                activeSubView === "quality"
                  ? "bg-electric-indigo text-white font-bold shadow-glow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <Code2 className="w-3.5 h-3.5 text-sky-400" />
              <span>Code Quality ({qualityFindings.length})</span>
            </button>
          </div>

          {/* Search Bar */}
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-gray-400" />
            <input
              type="text"
              placeholder="Search findings, rule ID, path..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-obsidian-base rounded-xl border border-obsidian-border text-xs text-white placeholder-gray-500 font-mono focus:outline-none focus:border-electric-indigo"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center space-x-2 text-xs font-mono">
            <span className="text-gray-500 flex items-center space-x-1">
              <SlidersHorizontal className="w-3 h-3" />
              <span>Severity:</span>
            </span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-obsidian-base border border-obsidian-border rounded-lg px-2 py-1 text-xs text-gray-300 font-mono focus:outline-none"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
              <option value="INFO">Info</option>
            </select>

            {activeSubView === "security" && (
              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                className="bg-obsidian-base border border-obsidian-border rounded-lg px-2 py-1 text-xs text-gray-300 font-mono focus:outline-none"
              >
                <option value="ALL">All Sources</option>
                <option value="STATIC_RULE">Static Rule</option>
                <option value="AST_ANALYSIS">AST Analysis</option>
                <option value="GRAPH_ANALYSIS">Graph Analysis</option>
                <option value="AI_ANALYSIS">AI Analysis</option>
              </select>
            )}
          </div>
        </div>

        {/* Findings List View */}
        {loading ? (
          <div className="text-center py-12">
            <RefreshCw className="w-6 h-6 animate-spin text-electric-indigo mx-auto mb-2" />
            <p className="text-xs text-gray-400 font-mono">Loading codebase intelligence findings...</p>
          </div>
        ) : !audit ? (
          <div className="text-center py-12 border border-dashed border-obsidian-border rounded-xl">
            <ShieldCheck className="w-10 h-10 text-gray-600 mx-auto mb-2" />
            <p className="text-sm font-bold text-gray-300 font-mono">No Audit Runs Yet</p>
            <p className="text-xs text-gray-500 mt-1 max-w-md mx-auto">
              Click &quot;Run Security & Quality Audit&quot; above to initiate an automated deterministic and graph-aware analysis of this repository.
            </p>
          </div>
        ) : activeSubView === "security" ? (
          /* Security Findings Table */
          <div className="space-y-2">
            {filteredSecurityFindings.length === 0 ? (
              <div className="text-center py-8 text-xs text-gray-400 font-mono">
                No security findings matching current filters.
              </div>
            ) : (
              filteredSecurityFindings.map((finding) => (
                <div
                  key={finding.id}
                  onClick={() => setSelectedSecurityFinding(finding)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer flex items-start justify-between gap-4 ${
                    selectedSecurityFinding?.id === finding.id
                      ? "bg-electric-indigo/10 border-electric-indigo shadow-glow"
                      : "bg-obsidian-base/50 border-obsidian-border hover:border-gray-700"
                  }`}
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${getSeverityBadge(
                          finding.severity
                        )}`}
                      >
                        {finding.severity}
                      </span>
                      <span className="text-[10px] font-mono text-gray-400 bg-obsidian-border/50 px-1.5 py-0.5 rounded">
                        {finding.rule_id}
                      </span>
                      <span className="text-xs font-mono font-semibold text-white truncate">
                        {finding.title}
                      </span>
                      {finding.is_ai_assisted && (
                        <span className="flex items-center space-x-1 text-[10px] font-mono text-electric-indigo bg-electric-indigo/15 border border-electric-indigo/30 px-1.5 py-0.5 rounded">
                          <Sparkles className="w-2.5 h-2.5" />
                          <span>AI Assisted</span>
                        </span>
                      )}
                    </div>

                    <div className="text-xs text-gray-400 line-clamp-1">
                      {finding.description}
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-gray-400">
                      <span className="flex items-center space-x-1 text-gray-300">
                        <FileText className="w-3 h-3 text-gray-500" />
                        <span>
                          {finding.file_path}:{finding.start_line}
                        </span>
                      </span>
                      <span>Category: {finding.category}</span>
                      <span>Source: {finding.detection_source}</span>
                      <span>Confidence: {Math.round(finding.confidence * 100)}%</span>
                      {finding.graph_reachability_path && (
                        <span className="text-electric-amber flex items-center space-x-1">
                          <Activity className="w-3 h-3" />
                          <span>Reachable from Entrypoint</span>
                        </span>
                      )}
                    </div>
                  </div>

                  <ChevronRight className="w-4 h-4 text-gray-500 mt-2 flex-shrink-0" />
                </div>
              ))
            )}
          </div>
        ) : (
          /* Quality Findings Table */
          <div className="space-y-2">
            {filteredQualityFindings.length === 0 ? (
              <div className="text-center py-8 text-xs text-gray-400 font-mono">
                No quality findings matching current filters.
              </div>
            ) : (
              filteredQualityFindings.map((finding) => (
                <div
                  key={finding.id}
                  onClick={() => setSelectedQualityFinding(finding)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer flex items-start justify-between gap-4 ${
                    selectedQualityFinding?.id === finding.id
                      ? "bg-electric-indigo/10 border-electric-indigo shadow-glow"
                      : "bg-obsidian-base/50 border-obsidian-border hover:border-gray-700"
                  }`}
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${getSeverityBadge(
                          finding.severity
                        )}`}
                      >
                        {finding.severity}
                      </span>
                      <span className="text-[10px] font-mono text-gray-400 bg-obsidian-border/50 px-1.5 py-0.5 rounded">
                        {finding.rule_id}
                      </span>
                      <span className="text-xs font-mono font-semibold text-white truncate">
                        {finding.title}
                      </span>
                    </div>

                    <div className="text-xs text-gray-400 line-clamp-1">
                      {finding.description}
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-gray-400">
                      <span className="flex items-center space-x-1 text-gray-300">
                        <FileText className="w-3 h-3 text-gray-500" />
                        <span>
                          {finding.file_path}:{finding.start_line}
                        </span>
                      </span>
                      <span>Metric: {finding.metric_name}</span>
                      <span>Value: {finding.value}</span>
                      <span>Threshold: {finding.threshold}</span>
                    </div>
                  </div>

                  <ChevronRight className="w-4 h-4 text-gray-500 mt-2 flex-shrink-0" />
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Slide-out Finding Inspector Drawer for Security */}
      {selectedSecurityFinding && (
        <div className="glass-card rounded-2xl p-5 border border-electric-indigo/40 bg-obsidian-surface/95 space-y-4 shadow-2xl">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${getSeverityBadge(
                    selectedSecurityFinding.severity
                  )}`}
                >
                  {selectedSecurityFinding.severity}
                </span>
                <span className="text-xs font-mono text-gray-400">
                  {selectedSecurityFinding.rule_id}
                </span>
                <span className="text-sm font-bold text-white font-mono">
                  {selectedSecurityFinding.title}
                </span>
              </div>
              <div className="text-xs font-mono text-gray-400">
                Location: {selectedSecurityFinding.file_path} (Lines {selectedSecurityFinding.start_line}-
                {selectedSecurityFinding.end_line})
              </div>
            </div>

            <div className="flex items-center space-x-2">
              {onNavigateToFile && (
                <button
                  onClick={() =>
                    onNavigateToFile(selectedSecurityFinding.file_path, selectedSecurityFinding.start_line)
                  }
                  className="px-3 py-1.5 rounded-lg bg-electric-indigo hover:bg-electric-indigo/80 text-white text-xs font-mono font-medium flex items-center space-x-1.5 transition shadow-glow"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Jump to Code</span>
                </button>
              )}
              <button
                onClick={() => setSelectedSecurityFinding(null)}
                className="p-1 rounded-lg text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Description */}
          <div className="text-xs text-gray-300 leading-relaxed font-sans">
            {selectedSecurityFinding.description}
          </div>

          {/* Reachability Call Path */}
          {selectedSecurityFinding.graph_reachability_path && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 font-mono text-xs space-y-1">
              <div className="text-amber-400 font-bold flex items-center space-x-1.5">
                <Activity className="w-3.5 h-3.5" />
                <span>Call-Graph Reachability Trace</span>
              </div>
              <div className="text-gray-300 text-[11px] overflow-x-auto py-1">
                {selectedSecurityFinding.graph_reachability_path}
              </div>
            </div>
          )}

          {/* Redacted Code Evidence */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono text-gray-400 uppercase tracking-wider">
              Triggering Code Evidence (Redacted)
            </div>
            <pre className="p-3 rounded-xl bg-obsidian-base border border-obsidian-border text-xs font-mono text-gray-200 overflow-x-auto whitespace-pre-wrap">
              {selectedSecurityFinding.evidence}
            </pre>
          </div>

          {/* Remediation Guide */}
          <div className="p-4 rounded-xl bg-electric-indigo/10 border border-electric-indigo/30 space-y-1.5">
            <div className="text-xs font-mono font-bold text-electric-indigo flex items-center space-x-1.5">
              <ShieldCheck className="w-4 h-4" />
              <span>Recommended Remediation</span>
            </div>
            <div className="text-xs text-gray-200 font-sans leading-relaxed whitespace-pre-wrap">
              {selectedSecurityFinding.remediation}
            </div>
          </div>
        </div>
      )}

      {/* Slide-out Finding Inspector Drawer for Quality */}
      {selectedQualityFinding && (
        <div className="glass-card rounded-2xl p-5 border border-sky-500/40 bg-obsidian-surface/95 space-y-4 shadow-2xl">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${getSeverityBadge(
                    selectedQualityFinding.severity
                  )}`}
                >
                  {selectedQualityFinding.severity}
                </span>
                <span className="text-xs font-mono text-gray-400">
                  {selectedQualityFinding.rule_id}
                </span>
                <span className="text-sm font-bold text-white font-mono">
                  {selectedQualityFinding.title}
                </span>
              </div>
              <div className="text-xs font-mono text-gray-400">
                Location: {selectedQualityFinding.file_path} (Lines {selectedQualityFinding.start_line}-
                {selectedQualityFinding.end_line})
              </div>
            </div>

            <div className="flex items-center space-x-2">
              {onNavigateToFile && (
                <button
                  onClick={() =>
                    onNavigateToFile(selectedQualityFinding.file_path, selectedQualityFinding.start_line)
                  }
                  className="px-3 py-1.5 rounded-lg bg-electric-indigo hover:bg-electric-indigo/80 text-white text-xs font-mono font-medium flex items-center space-x-1.5 transition shadow-glow"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Jump to Code</span>
                </button>
              )}
              <button
                onClick={() => setSelectedQualityFinding(null)}
                className="p-1 rounded-lg text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="text-xs text-gray-300 leading-relaxed font-sans">
            {selectedQualityFinding.description}
          </div>

          <div className="grid grid-cols-2 gap-3 font-mono text-xs">
            <div className="p-3 rounded-xl bg-obsidian-base border border-obsidian-border">
              <span className="text-gray-400">Measured Value: </span>
              <span className="text-rose-400 font-bold">{selectedQualityFinding.value}</span>
            </div>
            <div className="p-3 rounded-xl bg-obsidian-base border border-obsidian-border">
              <span className="text-gray-400">Allowed Threshold: </span>
              <span className="text-emerald-400 font-bold">{selectedQualityFinding.threshold}</span>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-sky-500/10 border border-sky-500/30 space-y-1.5">
            <div className="text-xs font-mono font-bold text-sky-400 flex items-center space-x-1.5">
              <Sparkles className="w-4 h-4" />
              <span>Refactoring Recommendation</span>
            </div>
            <div className="text-xs text-gray-200 font-sans leading-relaxed">
              {selectedQualityFinding.recommendation}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
