"use client";

import React, { useState } from "react";
import {
  Search,
  SlidersHorizontal,
  Code2,
  ExternalLink,
  Layers,
  Sparkles,
  Zap,
  Filter,
  CheckCircle2,
  FileCode,
} from "lucide-react";

interface SearchResultItem {
  chunk_id: string;
  file_path: string;
  symbol_fqn?: string;
  kind?: string;
  start_line: number;
  end_line: number;
  content: string;
  score: number;
  match_type: string;
  graph_context?: {
    symbol_fqn: string;
    kind: string;
    callers: string[];
    callees: string[];
  };
  embedding_model?: string;
}

interface CodeSearchProps {
  repositoryId: string;
  languages?: string[];
  onSelectFile?: (filePath: string, line?: number) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CodeSearch({
  repositoryId,
  languages = ["python", "typescript", "javascript"],
  onSelectFile,
}: CodeSearchProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"hybrid" | "semantic" | "exact">("hybrid");
  const [selectedLanguage, setSelectedLanguage] = useState<string>("");
  const [selectedKind, setSelectedKind] = useState<string>("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setHasSearched(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          mode: mode,
          language: selectedLanguage || null,
          kind: selectedKind || null,
          limit: 15,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setResults(data.results || []);
      } else {
        setResults([]);
      }
    } catch (err) {
      console.error("Search failed:", err);
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const sampleQueries = [
    { text: "AuthService", mode: "exact" as const },
    { text: "user authentication and token verification", mode: "semantic" as const },
    { text: "login_endpoint", mode: "exact" as const },
    { text: "database model entity relations", mode: "hybrid" as const },
  ];

  return (
    <div className="flex flex-col h-full bg-[#0D1117] border border-white/5 rounded-xl overflow-hidden">
      {/* Search Header & Controls */}
      <div className="p-5 bg-[#131822] border-b border-white/5 space-y-3.5">
        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search code by exact symbol, natural language concept, or file path..."
              className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-[#0A0D14] border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-indigo-500 transition font-sans"
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || isSearching}
            className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium text-sm flex items-center gap-1.5 transition shadow-lg shadow-indigo-600/20"
          >
            <Search className="w-4 h-4" />
            <span>{isSearching ? "Searching..." : "Search"}</span>
          </button>
        </form>

        {/* Filters & Mode Pills */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Mode Selector */}
          <div className="flex items-center gap-1.5 bg-black/40 p-1 rounded-lg border border-white/5">
            <span className="text-slate-400 px-2 font-mono text-[11px]">Mode:</span>
            {(["hybrid", "semantic", "exact"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`px-2.5 py-1 rounded-md transition font-medium capitalize ${
                  mode === m
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {m === "hybrid" ? "⚡ Hybrid (RRF)" : m === "semantic" ? "🧠 Semantic Vector" : "🎯 Exact Symbol"}
              </button>
            ))}
          </div>

          {/* Metadata Filters */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-black/40 px-2.5 py-1 rounded-lg border border-white/5 text-slate-300">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                className="bg-transparent text-xs text-slate-300 focus:outline-none cursor-pointer"
              >
                <option value="" className="bg-[#131822]">All Languages</option>
                {languages.map((l) => (
                  <option key={l} value={l} className="bg-[#131822]">
                    {l}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-1 bg-black/40 px-2.5 py-1 rounded-lg border border-white/5 text-slate-300">
              <select
                value={selectedKind}
                onChange={(e) => setSelectedKind(e.target.value)}
                className="bg-transparent text-xs text-slate-300 focus:outline-none cursor-pointer"
              >
                <option value="" className="bg-[#131822]">All Kinds</option>
                <option value="function" className="bg-[#131822]">Functions</option>
                <option value="class" className="bg-[#131822]">Classes</option>
                <option value="method" className="bg-[#131822]">Methods</option>
                <option value="api_endpoint" className="bg-[#131822]">API Endpoints</option>
                <option value="db_model" className="bg-[#131822]">DB Models</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Results Container */}
      <div className="flex-1 overflow-y-auto p-5 space-y-3 font-sans">
        {results.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-slate-400 px-1 font-mono">
              <span>Found {results.length} ranked code chunks</span>
              <span>Sorted by RRF relevance</span>
            </div>

            {results.map((item) => (
              <div
                key={item.chunk_id}
                className="p-4 rounded-xl bg-[#131822] border border-white/5 hover:border-indigo-500/30 transition space-y-2.5"
              >
                {/* Result Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-indigo-400" />
                    <span className="font-mono text-xs font-semibold text-white">
                      {item.file_path}
                    </span>
                    <span className="text-slate-400 text-xs font-mono">
                      (lines {item.start_line}-{item.end_line})
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-white/5 text-[10px] uppercase font-mono text-slate-300 border border-white/10">
                      {item.match_type}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-mono font-semibold">
                      {Math.round(item.score * 100)}% match
                    </span>
                    <button
                      onClick={() => onSelectFile?.(item.file_path, item.start_line)}
                      className="p-1 rounded-md bg-white/5 hover:bg-indigo-600/30 text-slate-400 hover:text-white transition"
                      title="Inspect in Editor"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Symbol FQN & Graph Tags */}
                {item.symbol_fqn && (
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span className="text-indigo-300 font-semibold">{item.symbol_fqn}</span>
                    {item.kind && (
                      <span className="px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-400 text-[10px]">
                        {item.kind}
                      </span>
                    )}
                  </div>
                )}

                {/* Graph Context (Callers/Callees) */}
                {item.graph_context && (
                  <div className="p-2 rounded bg-black/40 border border-white/5 text-[11px] font-mono space-y-1">
                    {item.graph_context.callers.length > 0 && (
                      <div className="text-slate-300">
                        <span className="text-amber-400 font-semibold">Callers:</span>{" "}
                        {item.graph_context.callers.join(", ")}
                      </div>
                    )}
                    {item.graph_context.callees.length > 0 && (
                      <div className="text-slate-300">
                        <span className="text-cyan-400 font-semibold">Callees:</span>{" "}
                        {item.graph_context.callees.join(", ")}
                      </div>
                    )}
                  </div>
                )}

                {/* Code Snippet */}
                <pre className="p-3 rounded-lg bg-black/50 text-slate-200 text-xs font-mono overflow-x-auto border border-white/5 max-h-40">
                  <code>{item.content}</code>
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 py-12 space-y-4">
            <div className="p-4 rounded-full bg-white/5 border border-white/5 text-slate-400">
              <Search className="w-8 h-8" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium text-slate-300">
                {hasSearched ? "No matching code chunks found" : "Ready to search codebase"}
              </p>
              <p className="text-xs text-slate-500 max-w-sm">
                Try searching for specific symbols or natural language queries.
              </p>
            </div>

            {/* Quick Starter Chips */}
            <div className="flex flex-wrap justify-center gap-2 max-w-md pt-2">
              {sampleQueries.map((sq, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setQuery(sq.text);
                    setMode(sq.mode);
                  }}
                  className="px-3 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-slate-400 hover:text-white border border-white/5 transition"
                >
                  {sq.text}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
