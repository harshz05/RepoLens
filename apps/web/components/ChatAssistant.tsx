"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  Send,
  Bot,
  User,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Layers,
  Network,
  Code2,
  RefreshCw,
  HelpCircle,
  FileCode,
} from "lucide-react";

interface Citation {
  file_path: string;
  start_line: number;
  end_line: number;
  symbol_name?: string;
  snippet: string;
  confidence_score: number;
}

interface RetrievedChunk {
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
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  retrieved_chunks?: RetrievedChunk[];
}

interface ChatAssistantProps {
  repositoryId: string;
  repositoryName: string;
  embeddingModel?: string;
  onSelectFile?: (filePath: string, line?: number) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ChatAssistant({
  repositoryId,
  repositoryName,
  embeddingModel = "models/gemini-embedding-2",
  onSelectFile,
}: ChatAssistantProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hello! I am RepoLens AI, grounded in **${repositoryName}** AST symbol tables, call graphs, and dense vector embeddings.\n\nAsk me about architecture, function workflows, data models, or cross-file dependencies. Every claim is strictly grounded with verified code citations.`,
    },
  ]);
  const [inputQuery, setInputQuery] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedSourcesMsgId, setExpandedSourcesMsgId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSendMessage = async (queryText?: string) => {
    const textToSend = queryText || inputQuery;
    if (!textToSend.trim() || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: textToSend.trim(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!queryText) setInputQuery("");
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: textToSend.trim(),
          session_id: sessionId,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        const assistantMsg: ChatMessage = {
          id: data.message_id,
          role: "assistant",
          content: data.response,
          citations: data.citations,
          retrieved_chunks: data.retrieved_chunks,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        const errData = await res.json().catch(() => ({}));
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `⚠️ **Error generating grounded response:** ${errData.detail || res.statusText}`,
          },
        ]);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `⚠️ **Network error:** ${err.message || "Failed to reach API"}`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const samplePrompts = [
    "Explain the core authentication and user login flow",
    "What are the main API route endpoints and handlers?",
    "Show the database models and their relationships",
    "What functions depend on the primary business service?",
  ];

  return (
    <div className="flex flex-col h-full bg-[#0D1117] border border-white/5 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 bg-[#131822] border-b border-white/5">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white">Grounded Codebase Assistant</h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                RAG Active
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono">
              Model: {embeddingModel} &bull; 768-dim pgvector
            </p>
          </div>
        </div>
        <button
          onClick={() => {
            setSessionId(null);
            setMessages([
              {
                id: "welcome",
                role: "assistant",
                content: `Chat session reset. Ready to answer questions grounded in **${repositoryName}**.`,
              },
            ]);
          }}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 rounded-lg transition"
          title="Start New Session"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          New Session
        </button>
      </div>

      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 font-sans text-sm">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role !== "user" && (
              <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-[85%] rounded-xl p-4 ${
                msg.role === "user"
                  ? "bg-indigo-600/90 text-white rounded-tr-none shadow-md shadow-indigo-600/10"
                  : "bg-[#161B26] border border-white/5 text-slate-200 rounded-tl-none"
              }`}
            >
              <div className="whitespace-pre-wrap leading-relaxed space-y-2">
                {msg.content}
              </div>

              {/* Citations Badges */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3.5 pt-3 border-t border-white/5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
                    <FileCode className="w-3.5 h-3.5 text-indigo-400" />
                    Verified Citations & Sources:
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {msg.citations.map((cit, idx) => (
                      <button
                        key={idx}
                        onClick={() => onSelectFile?.(cit.file_path, cit.start_line)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 hover:text-white border border-indigo-500/20 text-xs font-mono transition"
                      >
                        <span>
                          {cit.file_path}:{cit.start_line}
                          {cit.end_line > cit.start_line ? `-${cit.end_line}` : ""}
                        </span>
                        <ExternalLink className="w-3 h-3 opacity-60" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Collapsible Retrieved Chunks & Graph Context Drawer */}
              {msg.retrieved_chunks && msg.retrieved_chunks.length > 0 && (
                <div className="mt-3">
                  <button
                    onClick={() =>
                      setExpandedSourcesMsgId(
                        expandedSourcesMsgId === msg.id ? null : msg.id
                      )
                    }
                    className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition font-mono"
                  >
                    <Layers className="w-3.5 h-3.5 text-indigo-400" />
                    <span>
                      {expandedSourcesMsgId === msg.id ? "Hide" : "Inspect"}{" "}
                      {msg.retrieved_chunks.length} Retrieved Graph & Chunk Sources
                    </span>
                    {expandedSourcesMsgId === msg.id ? (
                      <ChevronUp className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5" />
                    )}
                  </button>

                  {expandedSourcesMsgId === msg.id && (
                    <div className="mt-2.5 space-y-2 pt-2">
                      {msg.retrieved_chunks.map((rc, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-[#0E131C] border border-white/5 text-xs font-mono space-y-1.5"
                        >
                          <div className="flex items-center justify-between text-slate-300">
                            <span className="font-semibold text-indigo-300">
                              {rc.file_path} (lines {rc.start_line}-{rc.end_line})
                            </span>
                            <div className="flex items-center gap-2">
                              <span className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] text-slate-400 uppercase">
                                {rc.match_type}
                              </span>
                              <span className="text-emerald-400 font-semibold text-[11px]">
                                {Math.round(rc.score * 100)}% Match
                              </span>
                            </div>
                          </div>

                          {rc.graph_context && (
                            <div className="text-[11px] text-slate-400 bg-white/[0.02] p-1.5 rounded border border-white/5">
                              {rc.graph_context.callers.length > 0 && (
                                <div>
                                  <span className="text-amber-400 font-semibold">Callers:</span>{" "}
                                  {rc.graph_context.callers.join(", ")}
                                </div>
                              )}
                              {rc.graph_context.callees.length > 0 && (
                                <div>
                                  <span className="text-cyan-400 font-semibold">Callees:</span>{" "}
                                  {rc.graph_context.callees.join(", ")}
                                </div>
                              )}
                            </div>
                          )}

                          <pre className="p-2 rounded bg-black/40 text-slate-300 text-[11px] overflow-x-auto max-h-28">
                            <code>{rc.content}</code>
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="w-7 h-7 rounded-lg bg-slate-700/50 border border-white/10 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3 justify-start items-center text-slate-400 text-xs py-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 animate-pulse">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
              <span>Executing Hybrid RAG & Graph Context Expansion...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompt Chips */}
      {messages.length <= 2 && (
        <div className="px-5 py-2.5 bg-[#10141D] border-t border-white/5">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <HelpCircle className="w-3.5 h-3.5 text-indigo-400" />
            Suggested Architectural Questions:
          </div>
          <div className="flex flex-wrap gap-2">
            {samplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(prompt)}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-xs text-slate-300 hover:text-white border border-white/5 transition text-left"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Form */}
      <div className="p-4 bg-[#131822] border-t border-white/5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            placeholder="Ask about architecture, functions, call graphs, or data models..."
            className="flex-1 px-4 py-2.5 rounded-lg bg-[#0A0D14] border border-white/10 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-indigo-500 transition font-sans"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!inputQuery.trim() || isLoading}
            className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium text-sm flex items-center gap-1.5 transition shadow-lg shadow-indigo-600/20"
          >
            <Send className="w-4 h-4" />
            <span>Send</span>
          </button>
        </form>
      </div>
    </div>
  );
}
