"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
  Node,
  Edge,
  NodeProps,
} from "@xyflow/react";
import {
  Layers,
  Code,
  Cpu,
  Zap,
  Search,
  Filter,
  ArrowRight,
  Maximize2,
  FileCode,
  Compass,
  CornerDownRight,
  Sparkles,
} from "lucide-react";

type GraphNodeData = {
  id: string;
  label: string;
  fqn: string;
  kind: string;
  filePath: string;
  lineRange: [number, number];
  signature?: string;
  docstring?: string;
  isSelected?: boolean;
  [key: string]: unknown;
};

type SymbolNodeType = Node<GraphNodeData, "symbolNode">;

// Custom Themed Symbol Node
const SymbolNode = ({ data, selected }: NodeProps<SymbolNodeType>) => {
  const getBadgeStyle = (kind: string) => {
    switch (kind) {
      case "api_endpoint":
        return "bg-electric-emerald/20 text-electric-emerald border-electric-emerald/40";
      case "db_model":
        return "bg-electric-violet/20 text-electric-violet border-electric-violet/40";
      case "class":
        return "bg-electric-violet/15 text-electric-violet border-electric-violet/30";
      case "component":
        return "bg-electric-cyan/20 text-electric-cyan border-electric-cyan/40";
      case "hook":
        return "bg-electric-cyan/15 text-electric-cyan border-electric-cyan/30";
      case "interface":
        return "bg-electric-amber/20 text-electric-amber border-electric-amber/40";
      case "method":
        return "bg-electric-indigo/15 text-electric-indigo border-electric-indigo/30";
      default:
        return "bg-electric-indigo/20 text-electric-indigo border-electric-indigo/40";
    }
  };

  return (
    <div
      className={`px-4 py-3 rounded-xl bg-obsidian-surface/95 border backdrop-blur-md transition-all duration-200 min-w-[220px] max-w-[320px] shadow-lg ${
        selected
          ? "border-electric-indigo shadow-glow ring-1 ring-electric-indigo"
          : "border-obsidian-border hover:border-gray-600 hover:shadow-glow"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2.5 h-2.5 !bg-electric-indigo border border-obsidian-base"
      />

      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span
          className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${getBadgeStyle(
            data.kind
          )}`}
        >
          {data.kind.replace("_", " ")}
        </span>
        <span className="text-[10px] font-mono text-gray-400">
          L{data.lineRange?.[0]}
        </span>
      </div>

      <div className="font-mono text-xs font-bold text-white truncate">
        {data.label}
      </div>

      {data.filePath && (
        <div className="text-[10px] font-mono text-gray-400 truncate mt-1 flex items-center gap-1">
          <FileCode className="w-3 h-3 text-gray-400 shrink-0" />
          <span className="truncate">{data.filePath}</span>
        </div>
      )}

      {data.signature && (
        <div className="mt-2 text-[10px] font-mono text-gray-300 bg-obsidian-base/80 px-2 py-1 rounded border border-obsidian-border/50 truncate">
          {data.signature}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2.5 h-2.5 !bg-electric-violet border border-obsidian-base"
      />
    </div>
  );
};

const nodeTypes = {
  symbolNode: SymbolNode,
};

interface DependencyGraphProps {
  repositoryId: string;
  onSelectSymbol?: (symbolId: string) => void;
}

export default function DependencyGraph({
  repositoryId,
  onSelectSymbol,
}: DependencyGraphProps) {
  const [graphData, setGraphData] = useState<{
    total_nodes: number;
    total_edges: number;
    nodes: any[];
    edges: any[];
    files_count: number;
  } | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedKind, setSelectedKind] = useState<string>("ALL");
  const [selectedFileFilter, setSelectedFileFilter] = useState<string>("ALL");

  // Selected Node in Graph
  const [selectedNodeData, setSelectedNodeData] = useState<GraphNodeData | null>(null);
  const [selectedSymbolDetail, setSelectedSymbolDetail] = useState<{
    symbol: any;
    callers: any[];
    callees: any[];
  } | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Fetch Graph Data
  const fetchGraph = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/repositories/${repositoryId}/graph`);
      if (!res.ok) {
        throw new Error("Failed to fetch repository dependency graph");
      }
      const data = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load dependency graph");
    } finally {
      setIsLoading(false);
    }
  }, [API_BASE, repositoryId]);

  useEffect(() => {
    if (repositoryId) {
      fetchGraph();
    }
  }, [repositoryId, fetchGraph]);

  // Unique files list for filter
  const fileOptions = useMemo(() => {
    if (!graphData) return [];
    const files = new Set<string>();
    graphData.nodes.forEach((n) => {
      if (n.filePath) files.add(n.filePath);
    });
    return Array.from(files).sort();
  }, [graphData]);

  // Layout & Transform Graph Data for React Flow
  useEffect(() => {
    if (!graphData) return;

    // Filter nodes
    const filteredRawNodes = graphData.nodes.filter((n) => {
      const matchesSearch =
        !searchQuery ||
        n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        n.filePath.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesKind =
        selectedKind === "ALL" ||
        (selectedKind === "ENDPOINTS" && n.kind === "api_endpoint") ||
        (selectedKind === "CLASSES" && ["class", "db_model"].includes(n.kind)) ||
        (selectedKind === "FUNCTIONS" && ["function", "method"].includes(n.kind)) ||
        (selectedKind === "COMPONENTS" && ["component", "hook"].includes(n.kind)) ||
        (selectedKind === "INTERFACES" && n.kind === "interface");

      const matchesFile =
        selectedFileFilter === "ALL" || n.filePath === selectedFileFilter;

      return matchesSearch && matchesKind && matchesFile;
    });

    const activeNodeIds = new Set(filteredRawNodes.map((n) => n.id));

    // Layout computation: Organize nodes by file clusters
    const fileGroups: { [file: string]: any[] } = {};
    filteredRawNodes.forEach((n) => {
      const f = n.filePath || "root";
      if (!fileGroups[f]) fileGroups[f] = [];
      fileGroups[f].push(n);
    });

    const flowNodes: Node[] = [];
    let fileCol = 0;

    Object.entries(fileGroups).forEach(([file, syms]) => {
      syms.forEach((sym, rowIdx) => {
        flowNodes.push({
          id: sym.id,
          type: "symbolNode",
          position: {
            x: fileCol * 360 + 50,
            y: rowIdx * 160 + 50,
          },
          data: {
            id: sym.id,
            label: sym.label,
            fqn: sym.fqn,
            kind: sym.kind,
            filePath: sym.filePath,
            lineRange: sym.lineRange,
            signature: sym.signature,
            docstring: sym.docstring,
          },
        });
      });
      fileCol++;
    });

    // Edges
    const flowEdges: Edge[] = [];
    graphData.edges.forEach((e) => {
      if (activeNodeIds.has(e.source) && activeNodeIds.has(e.target)) {
        const isSelectedEdge =
          selectedNodeData &&
          (e.source === selectedNodeData.id || e.target === selectedNodeData.id);

        flowEdges.push({
          id: e.id,
          source: e.source,
          target: e.target,
          type: "smoothstep",
          animated: isSelectedEdge || false,
          label: e.label,
          labelStyle: { fill: "#9CA3AF", fontSize: 10, fontFamily: "monospace" },
          labelBgStyle: { fill: "#131620", fillOpacity: 0.8 },
          labelBgPadding: [4, 2],
          labelBgBorderRadius: 4,
          style: {
            stroke: isSelectedEdge ? "#8B5CF6" : "rgba(99, 102, 241, 0.4)",
            strokeWidth: isSelectedEdge ? 2.5 : 1.5,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: isSelectedEdge ? "#8B5CF6" : "rgba(99, 102, 241, 0.6)",
          },
        });
      }
    });

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [graphData, searchQuery, selectedKind, selectedFileFilter, selectedNodeData, setNodes, setEdges]);

  // On Node Click -> Load callers & callees
  const handleNodeClick = async (_: any, node: Node) => {
    const nodeData = node.data as unknown as GraphNodeData;
    setSelectedNodeData(nodeData);
    if (onSelectSymbol) {
      onSelectSymbol(node.id);
    }

    try {
      const res = await fetch(
        `${API_BASE}/api/v1/repositories/${repositoryId}/symbols/${node.id}/dependencies`
      );
      if (res.ok) {
        const detail = await res.json();
        setSelectedSymbolDetail(detail);
      }
    } catch {
      // Keep existing data
    }
  };

  return (
    <div className="flex flex-col h-[700px] glass-panel rounded-2xl overflow-hidden border border-obsidian-border relative">
      {/* Top Filter & Command Toolbar */}
      <div className="p-4 border-b border-obsidian-border bg-obsidian-surface/90 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 z-10">
        <div className="flex items-center space-x-3 flex-1 min-w-[280px]">
          {/* Search Box */}
          <div className="relative flex-1 max-w-xs">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500">
              <Search className="w-3.5 h-3.5" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search symbols or files..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-obsidian-base border border-obsidian-border text-white text-xs font-mono focus:outline-none focus:border-electric-indigo transition"
            />
          </div>

          {/* Kind Filter */}
          <div className="flex items-center space-x-1 bg-obsidian-base p-1 rounded-lg border border-obsidian-border text-xs font-mono">
            {[
              { id: "ALL", label: "All" },
              { id: "ENDPOINTS", label: "APIs" },
              { id: "CLASSES", label: "Classes" },
              { id: "FUNCTIONS", label: "Functions" },
              { id: "COMPONENTS", label: "React" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSelectedKind(tab.id)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                  selectedKind === tab.id
                    ? "bg-electric-indigo text-white shadow-sm"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* File Filter Dropdown */}
          {fileOptions.length > 0 && (
            <select
              value={selectedFileFilter}
              onChange={(e) => setSelectedFileFilter(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-obsidian-base border border-obsidian-border text-gray-300 text-xs font-mono focus:outline-none focus:border-electric-indigo"
            >
              <option value="ALL">All Files ({fileOptions.length})</option>
              {fileOptions.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Quick Stats */}
        <div className="flex items-center space-x-4 text-xs font-mono text-gray-400">
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-electric-indigo"></span>
            <span>{nodes.length} Nodes</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-electric-violet"></span>
            <span>{edges.length} Edges</span>
          </div>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 relative flex">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center space-y-3 flex-col bg-obsidian-base">
            <div className="w-8 h-8 rounded-full border-2 border-electric-indigo border-t-transparent animate-spin"></div>
            <p className="text-xs font-mono text-gray-400">Loading dependency graph...</p>
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center flex-col bg-obsidian-base p-6 text-center">
            <p className="text-xs font-mono text-electric-rose mb-3">{error}</p>
            <button
              onClick={fetchGraph}
              className="px-3 py-1.5 rounded-lg bg-obsidian-elevated text-xs font-mono text-white border border-obsidian-border"
            >
              Retry
            </button>
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex-1 flex items-center justify-center flex-col bg-obsidian-base p-6 text-center space-y-2">
            <Compass className="w-10 h-10 text-gray-600 mx-auto" />
            <p className="text-sm font-bold text-gray-300">No matching graph nodes</p>
            <p className="text-xs text-gray-500">Try adjusting your search query or filters.</p>
          </div>
        ) : (
          <div className="flex-1 h-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              onNodeClick={handleNodeClick}
              fitView
              minZoom={0.2}
              maxZoom={1.8}
            >
              <Background color="#1F2937" gap={20} size={1} />
              <Controls />
              <MiniMap
                nodeColor={(node: any) => {
                  switch (node.data?.kind) {
                    case "api_endpoint":
                      return "#10B981";
                    case "db_model":
                    case "class":
                      return "#8B5CF6";
                    case "component":
                      return "#06B6D4";
                    default:
                      return "#6366F1";
                  }
                }}
                maskColor="rgba(11, 13, 19, 0.7)"
              />
            </ReactFlow>
          </div>
        )}

        {/* Selected Node Relationship Detail Inspector Sidebar */}
        {selectedNodeData && (
          <div className="w-80 border-l border-obsidian-border bg-obsidian-surface/95 backdrop-blur-md p-5 overflow-y-auto space-y-5 z-20">
            <div className="flex items-start justify-between border-b border-obsidian-border pb-3">
              <div>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-electric-indigo/20 text-electric-indigo font-bold">
                  {selectedNodeData.kind}
                </span>
                <h3 className="font-bold text-white font-mono text-sm mt-2">
                  {selectedNodeData.label}
                </h3>
                <div className="text-[11px] font-mono text-gray-400 mt-1">
                  {selectedNodeData.filePath}:{selectedNodeData.lineRange?.[0]}
                </div>
              </div>
              <button
                onClick={() => setSelectedNodeData(null)}
                className="text-gray-500 hover:text-white text-xs font-mono"
              >
                ✕
              </button>
            </div>

            {selectedNodeData.signature && (
              <div className="space-y-1">
                <div className="text-[10px] font-mono uppercase text-gray-500 font-bold">
                  Signature
                </div>
                <pre className="text-[11px] font-mono text-gray-300 bg-obsidian-base p-2.5 rounded-lg border border-obsidian-border overflow-x-auto">
                  {selectedNodeData.signature}
                </pre>
              </div>
            )}

            {selectedNodeData.docstring && (
              <div className="space-y-1">
                <div className="text-[10px] font-mono uppercase text-gray-500 font-bold">
                  Documentation
                </div>
                <p className="text-xs text-gray-400 italic bg-obsidian-base/50 p-2.5 rounded-lg border border-obsidian-border/50">
                  {selectedNodeData.docstring}
                </p>
              </div>
            )}

            {/* Callers (Incoming Dependencies) */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-gray-400 font-bold flex items-center justify-between">
                <span>Callers / Upstream ({selectedSymbolDetail?.callers.length || 0})</span>
              </div>
              {!selectedSymbolDetail || selectedSymbolDetail.callers.length === 0 ? (
                <p className="text-[11px] text-gray-500 italic">No incoming calls detected.</p>
              ) : (
                <div className="space-y-1.5 max-h-36 overflow-y-auto">
                  {selectedSymbolDetail.callers.map((c) => (
                    <div
                      key={c.id}
                      className="p-2 rounded-lg bg-obsidian-base border border-obsidian-border text-xs font-mono text-gray-300 flex items-center space-x-1.5"
                    >
                      <CornerDownRight className="w-3 h-3 text-electric-indigo shrink-0" />
                      <span className="truncate font-bold text-white">{c.name}</span>
                      <span className="text-[10px] text-gray-500 shrink-0">({c.kind})</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Callees (Outgoing Dependencies) */}
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase text-gray-400 font-bold flex items-center justify-between">
                <span>Callees / Downstream ({selectedSymbolDetail?.callees.length || 0})</span>
              </div>
              {!selectedSymbolDetail || selectedSymbolDetail.callees.length === 0 ? (
                <p className="text-[11px] text-gray-500 italic">No outgoing calls detected.</p>
              ) : (
                <div className="space-y-1.5 max-h-36 overflow-y-auto">
                  {selectedSymbolDetail.callees.map((c) => (
                    <div
                      key={c.id}
                      className="p-2 rounded-lg bg-obsidian-base border border-obsidian-border text-xs font-mono text-gray-300 flex items-center space-x-1.5"
                    >
                      <ArrowRight className="w-3 h-3 text-electric-violet shrink-0" />
                      <span className="truncate font-bold text-white">{c.name}</span>
                      <span className="text-[10px] text-gray-500 shrink-0">({c.kind})</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
