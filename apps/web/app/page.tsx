"use client";

import React, { useState, useEffect } from "react";
import {
  GitBranch,
  Terminal,
  Cpu,
  Layers,
  FileCode,
  Code,
  ShieldCheck,
  Zap,
  RefreshCw,
  Search,
  ChevronRight,
  Folder,
  FileText,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  Sparkles,
  Network,
  Share2,
  Bot,
  Database,
  ShieldAlert,
} from "lucide-react";
import DependencyGraph from "@/components/DependencyGraph";
import ChatAssistant from "@/components/ChatAssistant";
import CodeSearch from "@/components/CodeSearch";
import SecurityAuditDashboard from "@/components/SecurityAuditDashboard";

interface SymbolData {
  id: string;
  name: string;
  fully_qualified_name: string;
  kind: string;
  start_line: number;
  end_line: number;
  signature?: string;
  docstring?: string;
}

interface FileData {
  id: string;
  path: string;
  language: string;
  line_count: number;
  byte_size: number;
  symbol_count: number;
  symbols: SymbolData[];
}

interface AnalysisRunData {
  id: string;
  status: string;
  current_step: string;
  progress_percentage: number;
  step_details?: string;
  error_log?: string;
}

interface RepoSummary {
  id: string;
  github_url: string;
  owner: string;
  name: string;
  default_branch: string;
  created_at: string;
  latest_status: string;
  total_files: number;
  total_loc: number;
  total_symbols: number;
  total_dependencies: number;
  total_chunks: number;
  embedding_model?: string;
  embedding_dimension?: number;
  language_breakdown: Record<string, number>;
}

interface RepoDetail extends RepoSummary {
  files: FileData[];
  latest_analysis_run?: AnalysisRunData;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CommandCenter() {
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<RepoDetail | null>(null);
  const [selectedFile, setSelectedFile] = useState<FileData | null>(null);
  const [activeTab, setActiveTab] = useState<"graph" | "chat" | "search" | "inspector" | "audit">("graph");

  // Ingestion form state
  const [githubUrl, setGithubUrl] = useState("https://github.com/pallets/flask");
  const [branch, setBranch] = useState("main");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // SSE Live Progress State
  const [activeAnalysisRunId, setActiveAnalysisRunId] = useState<string | null>(null);
  const [progressData, setProgressData] = useState<{
    step: string;
    progress: number;
    details: string;
    logs: string[];
  } | null>(null);

  // Fetch all repositories
  const fetchRepositories = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories`);
      if (res.ok) {
        const data = await res.json();
        setRepos(data);
        if (data.length > 0 && !selectedRepo) {
          fetchRepoDetail(data[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch repositories:", err);
    }
  };

  useEffect(() => {
    fetchRepositories();
  }, []);

  // Fetch repository details
  const fetchRepoDetail = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedRepo(data);
        if (data.files && data.files.length > 0) {
          setSelectedFile(data.files[0]);
        }
      }
    } catch (err) {
      console.error("Failed to fetch repository detail:", err);
    }
  };

  // Submit GitHub Repository
  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setIsSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: githubUrl, branch }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to start repository ingestion");
      }

      setActiveAnalysisRunId(data.analysis_run_id);
      setProgressData({
        step: "QUEUED",
        progress: 5,
        details: "Ingestion task queued in worker pool...",
        logs: ["Task queued in asynchronous background broker..."],
      });

      // Connect to SSE stream
      const eventSource = new EventSource(`${API_BASE}/api/v1/repositories/events/${data.analysis_run_id}`);

      eventSource.onmessage = (event) => {
        const eventData = JSON.parse(event.data);
        setProgressData((prev) => ({
          step: eventData.step,
          progress: eventData.progress,
          details: eventData.details,
          logs: prev ? [...prev.logs, `[${new Date().toLocaleTimeString()}] ${eventData.details}`] : [eventData.details],
        }));

        if (eventData.step === "COMPLETED" || eventData.step === "FAILED") {
          eventSource.close();
          setIsSubmitting(false);
          fetchRepositories();
          if (eventData.step === "COMPLETED") {
            fetchRepoDetail(data.repository_id);
          }
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        setIsSubmitting(false);
      };
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred");
      setIsSubmitting(false);
    }
  };

  const handleSelectFileFromCitation = (filePath: string, line?: number) => {
    if (!selectedRepo) return;
    const matchedFile = selectedRepo.files.find((f) => f.path === filePath || f.path.endsWith(filePath));
    if (matchedFile) {
      setSelectedFile(matchedFile);
      setActiveTab("inspector");
    }
  };

  // Aggregated platform stats
  const totalRepos = repos.length;
  const totalFiles = repos.reduce((acc, r) => acc + (r.total_files || 0), 0);
  const totalLoc = repos.reduce((acc, r) => acc + (r.total_loc || 0), 0);
  const totalSymbols = repos.reduce((acc, r) => acc + (r.total_symbols || 0), 0);
  const totalDependencies = repos.reduce((acc, r) => acc + (r.total_dependencies || 0), 0);
  const totalChunks = repos.reduce((acc, r) => acc + (r.total_chunks || 0), 0);

  return (
    <div className="min-h-screen bg-obsidian-base text-gray-100 flex flex-col font-sans selection:bg-electric-indigo/30 selection:text-white">
      {/* Top Navigation Bar */}
      <header className="border-b border-obsidian-border bg-obsidian-surface/80 backdrop-blur-md sticky top-0 z-40 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-gradient-to-tr from-electric-indigo to-electric-violet shadow-glow text-white font-bold flex items-center justify-center">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-mono text-base font-bold tracking-tight text-white">RepoLens</h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-electric-indigo/10 text-electric-indigo border border-electric-indigo/20 font-mono font-bold">
                M4 &bull; Security &amp; Code Quality Intelligence
              </span>
            </div>
            <p className="text-xs text-gray-400">Enterprise Code Intelligence & Architectural Command Center</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="hidden sm:flex items-center space-x-2 text-xs font-mono text-gray-400 bg-obsidian-base px-3 py-1.5 rounded-lg border border-obsidian-border">
            <Database className="w-3.5 h-3.5 text-electric-indigo" />
            <span>pgvector HNSW</span>
            <span className="text-gray-600">|</span>
            <Sparkles className="w-3.5 h-3.5 text-electric-emerald" />
            <span>gemini-embedding-2</span>
          </div>
          <button
            onClick={fetchRepositories}
            className="p-2 rounded-lg bg-obsidian-border hover:bg-gray-800 text-gray-300 hover:text-white transition"
            title="Refresh Ingested Repositories"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 p-6 max-w-[1700px] w-full mx-auto space-y-6">
        {/* Ingestion Command Bar */}
        <div className="glass-panel rounded-2xl p-5 border border-obsidian-border space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-sm font-semibold text-gray-200">
              <Terminal className="w-4 h-4 text-electric-indigo" />
              <span>Ingest Public Git Repository</span>
            </div>
            <div className="text-xs text-gray-400 font-mono flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-electric-emerald animate-pulse"></span>
              <span>Worker Engine Ready</span>
            </div>
          </div>

          <form onSubmit={handleIngest} className="flex flex-col md:flex-row items-center gap-3">
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="url"
                required
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/pallets/flask"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-obsidian-base border border-obsidian-border text-white placeholder-gray-500 text-sm focus:outline-none focus:border-electric-indigo transition font-mono"
              />
            </div>

            <div className="relative w-full md:w-44">
              <GitBranch className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-obsidian-base border border-obsidian-border text-white placeholder-gray-500 text-sm focus:outline-none focus:border-electric-indigo transition font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full md:w-auto px-6 py-2.5 rounded-xl bg-gradient-to-r from-electric-indigo to-electric-violet hover:from-electric-indigo/90 hover:to-electric-violet/90 text-white font-medium text-sm flex items-center justify-center space-x-2 shadow-glow transition disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Ingesting Pipeline...</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  <span>Run AST & Vector Pipeline</span>
                </>
              )}
            </button>

            {errorMsg && (
              <div className="p-3 rounded-xl bg-electric-rose/10 border border-electric-rose/30 text-electric-rose text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}
          </form>

          {/* Real-time Progress Drawer / Event Stream Modal */}
          {progressData && (
            <div className="p-5 rounded-xl bg-obsidian-base border border-electric-indigo/40 space-y-4">
              <div className="flex items-center justify-between text-xs font-mono">
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded bg-electric-indigo/20 text-electric-indigo font-bold">
                    STEP: {progressData.step}
                  </span>
                  <span className="text-gray-300">{progressData.details}</span>
                </div>
                <span className="text-electric-indigo font-bold">{progressData.progress}%</span>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-obsidian-surface rounded-full h-2 overflow-hidden border border-obsidian-border">
                <div
                  className="bg-gradient-to-r from-electric-indigo via-electric-violet to-electric-emerald h-full transition-all duration-300"
                  style={{ width: `${progressData.progress}%` }}
                ></div>
              </div>

              {/* Console Output Log Stream */}
              <div className="bg-obsidian-surface/90 rounded-lg p-3 max-h-32 overflow-y-auto font-mono text-[11px] text-gray-400 space-y-1">
                {progressData.logs.map((log, idx) => (
                  <div key={idx} className="flex items-start space-x-2">
                    <span className="text-electric-indigo select-none">&gt;</span>
                    <span>{log}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Global Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3.5">
          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-electric-indigo/10 border border-electric-indigo/20 text-electric-indigo">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalRepos}</div>
              <div className="text-[11px] text-gray-400">Repositories</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-electric-emerald/10 border border-electric-emerald/20 text-electric-emerald">
              <FileCode className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalFiles.toLocaleString()}</div>
              <div className="text-[11px] text-gray-400">Source Files</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-electric-cyan/10 border border-electric-cyan/20 text-electric-cyan">
              <Code className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalLoc.toLocaleString()}</div>
              <div className="text-[11px] text-gray-400">Lines of Code</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-electric-violet/10 border border-electric-violet/20 text-electric-violet">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalSymbols.toLocaleString()}</div>
              <div className="text-[11px] text-gray-400">AST Symbols</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-electric-amber/10 border border-electric-amber/20 text-electric-amber">
              <Share2 className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalDependencies.toLocaleString()}</div>
              <div className="text-[11px] text-gray-400">Call Edges</div>
            </div>
          </div>

          <div className="glass-card rounded-xl p-3.5 flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-pink-500/10 border border-pink-500/20 text-pink-400">
              <Database className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xl font-bold text-white font-mono">{totalChunks.toLocaleString()}</div>
              <div className="text-[11px] text-gray-400">Vector Chunks</div>
            </div>
          </div>
        </div>

        {/* Repositories Selector & Main Workspace Split View */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left Column: Repository Cards List */}
          <div className="lg:col-span-1 space-y-4">
            <h2 className="text-base font-semibold text-gray-200 flex items-center justify-between">
              <span>Ingested Repositories</span>
              <span className="text-xs font-mono text-gray-500">{repos.length} Total</span>
            </h2>

            {repos.length === 0 ? (
              <div className="glass-card rounded-xl p-8 text-center space-y-3">
                <Folder className="w-10 h-10 text-gray-600 mx-auto" />
                <p className="text-xs text-gray-400">No repositories ingested yet. Enter a GitHub URL above to analyze your first codebase.</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[750px] overflow-y-auto pr-1">
                {repos.map((repo) => (
                  <div
                    key={repo.id}
                    onClick={() => fetchRepoDetail(repo.id)}
                    className={`glass-card rounded-xl p-4 cursor-pointer transition ${
                      selectedRepo?.id === repo.id
                        ? "border-electric-indigo bg-electric-indigo/5 shadow-glow"
                        : "hover:border-gray-700"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-bold text-sm text-white font-mono flex items-center space-x-1.5">
                          <span>{repo.owner}/{repo.name}</span>
                        </h3>
                        <div className="text-xs text-gray-400 mt-1 flex items-center space-x-2">
                          <span className="px-1.5 py-0.5 rounded bg-obsidian-border font-mono text-[10px]">
                            {repo.default_branch}
                          </span>
                          <span>{new Date(repo.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
                        repo.latest_status === "COMPLETED"
                          ? "bg-electric-emerald/20 text-electric-emerald border border-electric-emerald/30"
                          : "bg-electric-amber/20 text-electric-amber border border-electric-amber/30"
                      }`}>
                        {repo.latest_status}
                      </span>
                    </div>

                    <div className="mt-3 pt-3 border-t border-obsidian-border grid grid-cols-4 gap-1 text-center text-xs font-mono">
                      <div>
                        <div className="text-gray-400 text-[10px]">Files</div>
                        <div className="font-bold text-gray-200">{repo.total_files}</div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-[10px]">Symbols</div>
                        <div className="font-bold text-electric-indigo">{repo.total_symbols.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-[10px]">Edges</div>
                        <div className="font-bold text-electric-amber">{(repo.total_dependencies || 0).toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-gray-400 text-[10px]">Vectors</div>
                        <div className="font-bold text-pink-400">{(repo.total_chunks || 0).toLocaleString()}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Area: Interactive Workspace (Tabs: Graph vs. AI Assistant vs. Search vs. Inspector) */}
          <div className="lg:col-span-3 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              {/* Tab Switcher */}
              <div className="flex items-center space-x-1.5 bg-obsidian-surface p-1 rounded-xl border border-obsidian-border text-xs font-mono">
                <button
                  onClick={() => setActiveTab("graph")}
                  className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 font-medium transition ${
                    activeTab === "graph"
                      ? "bg-electric-indigo text-white shadow-glow"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  <Network className="w-3.5 h-3.5" />
                  <span>Dependency Graph</span>
                </button>
                <button
                  onClick={() => setActiveTab("chat")}
                  className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 font-medium transition ${
                    activeTab === "chat"
                      ? "bg-electric-indigo text-white shadow-glow"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  <Bot className="w-3.5 h-3.5 text-indigo-300" />
                  <span>AI Assistant (RAG)</span>
                </button>
                <button
                  onClick={() => setActiveTab("search")}
                  className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 font-medium transition ${
                    activeTab === "search"
                      ? "bg-electric-indigo text-white shadow-glow"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  <Search className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Code Search</span>
                </button>
                <button
                  onClick={() => setActiveTab("inspector")}
                  className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 font-medium transition ${
                    activeTab === "inspector"
                      ? "bg-electric-indigo text-white shadow-glow"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                  <span>AST Inspector</span>
                </button>
                <button
                  onClick={() => setActiveTab("audit")}
                  className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 font-medium transition ${
                    activeTab === "audit"
                      ? "bg-electric-indigo text-white shadow-glow"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                  <span>Security &amp; Quality</span>
                </button>
              </div>

              {selectedRepo && (
                <div className="text-xs font-mono text-gray-400 hidden sm:block">
                  Active: <strong className="text-white">{selectedRepo.owner}/{selectedRepo.name}</strong>
                </div>
              )}
            </div>

            {!selectedRepo ? (
              <div className="glass-card rounded-xl p-16 text-center space-y-3">
                <Network className="w-12 h-12 text-gray-600 mx-auto" />
                <p className="text-sm text-gray-400">Select a repository from the left panel to inspect dependencies, search code, or query AI assistant.</p>
              </div>
            ) : activeTab === "graph" ? (
              /* TAB 1: React Flow Dependency Graph */
              <DependencyGraph
                repositoryId={selectedRepo.id}
                onSelectSymbol={(symId) => {
                  // Optional symbol selection callback
                }}
              />
            ) : activeTab === "chat" ? (
              /* TAB 2: Grounded Gemini RAG Chat Cockpit */
              <div className="h-[750px]">
                <ChatAssistant
                  repositoryId={selectedRepo.id}
                  repositoryName={`${selectedRepo.owner}/${selectedRepo.name}`}
                  embeddingModel={selectedRepo.embedding_model || "models/gemini-embedding-2"}
                  onSelectFile={handleSelectFileFromCitation}
                />
              </div>
            ) : activeTab === "search" ? (
              /* TAB 3: Hybrid & Vector Code Search */
              <div className="h-[750px]">
                <CodeSearch
                  repositoryId={selectedRepo.id}
                  languages={Object.keys(selectedRepo.language_breakdown || {})}
                  onSelectFile={handleSelectFileFromCitation}
                />
              </div>
            ) : activeTab === "audit" ? (
              /* TAB 4: Security & Code Quality Intelligence Console */
              <SecurityAuditDashboard
                repositoryId={selectedRepo.id}
                onNavigateToFile={handleSelectFileFromCitation}
              />
            ) : (
              /* TAB 5: Source Code & AST Inspector */
              <div className="glass-panel rounded-xl overflow-hidden border border-obsidian-border flex flex-col md:flex-row h-[750px]">
                {/* File Hierarchy Selector */}
                <div className="w-full md:w-1/3 border-b md:border-b-0 md:border-r border-obsidian-border bg-obsidian-surface/60 overflow-y-auto p-3 space-y-1">
                  <div className="text-xs font-mono text-gray-400 px-2 py-1 uppercase font-bold border-b border-obsidian-border mb-2">
                    Source Files ({selectedRepo.files.length})
                  </div>
                  {selectedRepo.files.map((file) => (
                    <div
                      key={file.id}
                      onClick={() => setSelectedFile(file)}
                      className={`px-2.5 py-2 rounded-lg text-xs font-mono cursor-pointer transition flex items-center justify-between ${
                        selectedFile?.id === file.id
                          ? "bg-electric-indigo/20 text-white font-bold border border-electric-indigo/40"
                          : "text-gray-400 hover:bg-obsidian-hover hover:text-gray-200"
                      }`}
                    >
                      <div className="flex items-center space-x-2 truncate">
                        <FileText className="w-3.5 h-3.5 shrink-0 text-electric-indigo" />
                        <span className="truncate">{file.path}</span>
                      </div>
                      <span className="text-[10px] text-gray-500 shrink-0 font-normal">{file.line_count}L</span>
                    </div>
                  ))}
                </div>

                {/* File Symbol Detail Viewer */}
                <div className="flex-1 p-5 overflow-y-auto space-y-5 bg-obsidian-base">
                  {selectedFile ? (
                    <>
                      <div className="flex items-start justify-between border-b border-obsidian-border pb-3">
                        <div>
                          <div className="font-mono text-sm font-bold text-white flex items-center space-x-2">
                            <span>{selectedFile.path}</span>
                          </div>
                          <div className="text-xs text-gray-400 mt-1 flex items-center space-x-3 font-mono">
                            <span>Language: <strong className="text-electric-cyan">{selectedFile.language}</strong></span>
                            <span>Lines: {selectedFile.line_count}</span>
                            <span>Size: {(selectedFile.byte_size / 1024).toFixed(1)} KB</span>
                          </div>
                        </div>
                        <span className="px-2.5 py-1 rounded bg-electric-indigo/10 border border-electric-indigo/30 text-electric-indigo text-xs font-mono">
                          {selectedFile.symbols.length} AST Symbols
                        </span>
                      </div>

                      {/* Symbols List */}
                      <div className="space-y-3">
                        <h4 className="text-xs font-mono text-gray-400 uppercase font-bold">Extracted AST Symbols</h4>
                        {selectedFile.symbols.length === 0 ? (
                          <p className="text-xs text-gray-500 italic">No top-level functions or classes detected in this file.</p>
                        ) : (
                          <div className="space-y-2">
                            {selectedFile.symbols.map((sym) => (
                              <div key={sym.id} className="p-3 rounded-lg bg-obsidian-surface border border-obsidian-border space-y-1.5">
                                <div className="flex items-center justify-between font-mono text-xs">
                                  <div className="flex items-center space-x-2">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                                      sym.kind === "function" ? "bg-electric-indigo/20 text-electric-indigo" :
                                      sym.kind === "class" ? "bg-electric-violet/20 text-electric-violet" :
                                      sym.kind === "db_model" ? "bg-electric-violet/20 text-electric-violet" :
                                      sym.kind === "api_endpoint" ? "bg-electric-emerald/20 text-electric-emerald" :
                                      sym.kind === "component" ? "bg-electric-cyan/20 text-electric-cyan" :
                                      "bg-electric-cyan/20 text-electric-cyan"
                                    }`}>
                                      {sym.kind}
                                    </span>
                                    <span className="font-bold text-white">{sym.name}</span>
                                  </div>
                                  <span className="text-gray-500 text-[10px]">
                                    Lines {sym.start_line} - {sym.end_line}
                                  </span>
                                </div>
                                {sym.signature && (
                                  <div className="font-mono text-[11px] text-gray-300 bg-obsidian-base px-2.5 py-1 rounded border border-obsidian-border overflow-x-auto">
                                    {sym.signature}
                                  </div>
                                )}
                                {sym.docstring && (
                                  <p className="text-xs text-gray-400 italic line-clamp-2 pl-2 border-l-2 border-electric-indigo/40">
                                    {sym.docstring}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="text-center text-xs text-gray-500 py-20">
                      Select a file from the list to view AST symbols.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
