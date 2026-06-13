"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";

// Register fcose layout with cytoscape
if (typeof window !== "undefined") {
  cytoscape.use(fcose);
}

interface ClaimGraphProps {
  graphData: any;
  onNodeClick: (nodeData: any) => void;
  onEdgeClick: (edgeData: any) => void;
}

export default function ClaimGraph({ graphData, onNodeClick, onEdgeClick }: ClaimGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  // Filter States
  const [showContradictionsOnly, setShowContradictionsOnly] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string>("ALL");

  // Get unique entities from graphData for the filter dropdown
  const entitiesList = useMemo(() => {
    if (!graphData?.elements?.nodes) return [];
    return graphData.elements.nodes
      .filter((n: any) => n.data?.type === "entity")
      .map((n: any) => ({
        id: n.data.id,
        text: n.data.text,
        entityType: n.data.entity_type,
      }))
      .sort((a: any, b: any) => a.text.localeCompare(b.text));
  }, [graphData]);

  // Transform and Filter Elements
  const filteredElements = useMemo(() => {
    if (!graphData?.elements) return [];

    const rawNodes = graphData.elements.nodes || [];
    const rawEdges = graphData.elements.edges || [];

    // Step 1: Pre-process nodes (add labels, labels truncation, etc.)
    const processedNodes = rawNodes.map((node: any) => {
      const data = { ...node.data };
      if (data.type === "paper") {
        let firstAuthor = "Unknown";
        if (Array.isArray(data.authors) && data.authors.length > 0) {
          const parts = data.authors[0].split(" ");
          firstAuthor = parts[parts.length - 1] || "Unknown";
          if (data.authors.length > 1) {
            firstAuthor += " et al.";
          }
        }
        data.authors_short = `${firstAuthor} (${data.year})`;
        data.label = data.authors_short;
      } else if (data.type === "claim") {
        data.label = data.text.length > 18 ? `${data.text.substring(0, 15)}...` : data.text;
      } else if (data.type === "entity") {
        data.label = data.text;
      }
      return { ...node, data };
    });

    // Step 2: Apply Filters
    let finalNodes = [...processedNodes];
    let finalEdges = [...rawEdges];

    // Filter A: Show Contradictions Only
    if (showContradictionsOnly) {
      // Find all claim nodes involved in CONTRADICTS or SUPERSEDES edges
      const contradictionClaims = new Set<string>();
      finalEdges.forEach((edge: any) => {
        if (edge.data?.type === "CONTRADICTS" || edge.data?.type === "SUPERSEDES") {
          contradictionClaims.add(edge.data.source);
          contradictionClaims.add(edge.data.target);
        }
      });

      // Keep only contradiction claims, and nodes directly connected to them (papers and entities)
      const nodesToKeep = new Set<string>(contradictionClaims);
      
      // We also want to keep the papers these claims belong to, and entities they mention
      finalEdges.forEach((edge: any) => {
        if (edge.data?.type === "EXTRACTED_FROM" && nodesToKeep.has(edge.data.target)) {
          nodesToKeep.add(edge.data.source); // Keep paper
        }
        if (edge.data?.type === "MENTIONS" && nodesToKeep.has(edge.data.source)) {
          nodesToKeep.add(edge.data.target); // Keep entity
        }
      });

      finalNodes = finalNodes.filter((n: any) => nodesToKeep.has(n.data.id));
      finalEdges = finalEdges.filter((e: any) => {
        // Keep edge only if both source and target exist in finalNodes
        const hasSource = nodesToKeep.has(e.data.source);
        const hasTarget = nodesToKeep.has(e.data.target);
        return hasSource && hasTarget;
      });
    }

    // Filter B: Focus Specific Entity Subgraph
    if (selectedEntityId !== "ALL") {
      const subgraphNodes = new Set<string>([selectedEntityId]);

      // Find all claims that mention this entity
      finalEdges.forEach((edge: any) => {
        if (edge.data?.type === "MENTIONS" && edge.data.target === selectedEntityId) {
          subgraphNodes.add(edge.data.source); // Keep claim
        }
      });

      // Find all papers that contain these claims, and other entities mentioned by these claims
      finalEdges.forEach((edge: any) => {
        if (edge.data?.type === "EXTRACTED_FROM" && subgraphNodes.has(edge.data.target)) {
          subgraphNodes.add(edge.data.source); // Keep paper
        }
        if (edge.data?.type === "MENTIONS" && subgraphNodes.has(edge.data.source)) {
          subgraphNodes.add(edge.data.target); // Keep neighboring entity
        }
        if ((edge.data?.type === "CONTRADICTS" || edge.data?.type === "SUPERSEDES") && (subgraphNodes.has(edge.data.source) || subgraphNodes.has(edge.data.target))) {
          subgraphNodes.add(edge.data.source); // Keep contradiction claim A
          subgraphNodes.add(edge.data.target); // Keep contradiction claim B
        }
      });

      finalNodes = finalNodes.filter((n: any) => subgraphNodes.has(n.data.id));
      finalEdges = finalEdges.filter((e: any) => {
        const hasSource = subgraphNodes.has(e.data.source);
        const hasTarget = subgraphNodes.has(e.data.target);
        return hasSource && hasTarget;
      });
    }

    return [...finalNodes, ...finalEdges];
  }, [graphData, showContradictionsOnly, selectedEntityId]);

  // Trigger Layout recalculation
  const runLayout = () => {
    if (!cyRef.current) return;
    const layout = cyRef.current.layout({
      name: "fcose",
      quality: "proof",
      randomize: true,
      animate: true,
      animationDuration: 800,
      fit: true,
      padding: 40,
      nodeDimensionsIncludeLabels: true,
      uniformNodeDimensions: false,
      packComponents: true,
    } as any);
    layout.run();
  };

  // Cytoscape Core Initialization
  useEffect(() => {
    if (!containerRef.current || filteredElements.length === 0) return;

    // Destroy existing instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: filteredElements,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: [
        {
          selector: "node",
          style: {
            "content": "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "color": "#fff",
            "font-size": 9,
            "background-color": "#52525b",
            "width": 35,
            "height": 35,
            "overlay-padding": 4,
            "z-index": 10,
          },
        },
        {
          selector: 'node[type="paper"]',
          style: {
            "shape": "ellipse",
            "background-color": "#18181b", // zinc-900
            "border-width": 2,
            "border-color": "#71717a", // zinc-400
            "label": "data(authors_short)",
            "color": "#d4d4d8", // zinc-300
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 5,
            "width": 45,
            "height": 45,
          },
        },
        {
          selector: 'node[type="claim"]',
          style: {
            "shape": "round-rectangle",
            "border-width": 2,
            "width": 75,
            "height": 36,
            "text-wrap": "wrap",
            "text-max-width": "65px",
            "font-size": 9,
            "color": "#ffffff",
          },
        },
        {
          selector: 'node[type="claim"][polarity="POSITIVE"]',
          style: {
            "background-color": "#064e3b", // emerald-900
            "border-color": "#10b981", // emerald-500
          },
        },
        {
          selector: 'node[type="claim"][polarity="NEGATIVE"]',
          style: {
            "background-color": "#7f1d1d", // red-900
            "border-color": "#f43f5e", // rose-500
          },
        },
        {
          selector: 'node[type="claim"][polarity="NEUTRAL"]',
          style: {
            "background-color": "#27272a", // zinc-800
            "border-color": "#a1a1aa", // zinc-400
          },
        },
        {
          selector: 'node[type="entity"]',
          style: {
            "shape": "diamond",
            "background-color": "#2e1065", // purple-950
            "border-width": 2,
            "border-color": "#c084fc", // purple-400
            "label": "data(text)",
            "color": "#e9d5ff", // purple-200
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 5,
            "width": 30,
            "height": 30,
          },
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": "#27272a",
            "target-arrow-color": "#27272a",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "control-point-step-size": 30,
            "overlay-padding": 3,
          },
        },
        {
          selector: 'edge[type="EXTRACTED_FROM"]',
          style: {
            "line-color": "#3f3f46", // zinc-700
            "target-arrow-color": "#3f3f46",
            "line-style": "solid",
            "width": 1.2,
          },
        },
        {
          selector: 'edge[type="MENTIONS"]',
          style: {
            "line-color": "#4338ca", // indigo-700
            "target-arrow-color": "#4338ca",
            "line-style": "dashed",
            "width": 1.2,
            "target-arrow-shape": "chevron",
          },
        },
        {
          selector: 'edge[type="CONTRADICTS"]',
          style: {
            "line-color": "#ef4444", // red-500
            "target-arrow-color": "#ef4444",
            "line-style": "solid",
            "width": 3,
            "target-arrow-shape": "tee",
            "source-arrow-shape": "tee",
            "source-arrow-color": "#ef4444",
          },
        },
        {
          selector: 'edge[type="SUPERSEDES"]',
          style: {
            "line-color": "#a855f7", // purple-500
            "target-arrow-color": "#a855f7",
            "line-style": "dashed",
            "width": 2,
            "target-arrow-shape": "triangle",
          },
        },
        // Interactive Highlights
        {
          selector: "node:selected",
          style: {
            "border-width": 3.5,
            "border-color": "#a855f7", // purple-500
            "overlay-color": "#a855f7",
            "overlay-opacity": 0.15,
          },
        },
        {
          selector: "node.highlighted",
          style: {
            "border-width": 3.5,
            "border-color": "#06b6d4", // cyan-500
          },
        },
        {
          selector: "node.dimmed",
          style: {
            "opacity": 0.15,
          },
        },
        {
          selector: "edge.dimmed",
          style: {
            "opacity": 0.08,
          },
        },
        {
          selector: "edge.highlighted",
          style: {
            "line-color": "#06b6d4",
            "target-arrow-color": "#06b6d4",
            "width": 2.5,
          },
        },
      ],
    });

    cyRef.current = cy;

    // Set layout
    const layout = cy.layout({
      name: "fcose",
      quality: "proof",
      randomize: true,
      animate: false,
      fit: true,
      padding: 40,
      nodeDimensionsIncludeLabels: true,
      uniformNodeDimensions: false,
      packComponents: true,
    } as any);
    layout.run();

    // Node Click Handlers with beautiful neighborhood highlights
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      
      // Apply highlights
      const neighborhood = node.neighborhood();
      cy.elements().addClass("dimmed").removeClass("highlighted");
      
      node.removeClass("dimmed").addClass("highlighted");
      neighborhood.removeClass("dimmed").addClass("highlighted");
      node.connectedEdges().removeClass("dimmed").addClass("highlighted");

      onNodeClick(node.data());
    });

    // Edge Tap Handlers (for contradiction edges tooltip/reasoning)
    cy.on("tap", "edge", (evt) => {
      const edge = evt.target;
      onEdgeClick(edge.data());
    });

    // Tap background to clear selection
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass("dimmed").removeClass("highlighted");
        onNodeClick(null);
        onEdgeClick(null);
      }
    });

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [filteredElements]);

  return (
    <div className="w-full h-full flex flex-col relative bg-zinc-950 rounded-2xl border border-zinc-900 overflow-hidden shadow-inner">
      
      {/* Graph Filter & Control Bar */}
      <div className="absolute top-4 left-4 z-20 flex flex-wrap items-center gap-3 bg-zinc-900/80 backdrop-blur border border-zinc-800 p-2.5 rounded-xl shadow-lg max-w-[calc(100%-2rem)]">
        
        {/* Toggle Contradictions Only */}
        <label className="flex items-center gap-2 cursor-pointer select-none text-xs font-semibold text-zinc-300 px-2.5 py-1.5 hover:bg-zinc-800 rounded-lg transition-colors border border-zinc-800/50">
          <input
            type="checkbox"
            checked={showContradictionsOnly}
            onChange={(e) => {
              setShowContradictionsOnly(e.target.checked);
              onNodeClick(null);
            }}
            className="rounded border-zinc-700 bg-zinc-950 text-purple-600 focus:ring-purple-500/20"
          />
          <span>Conflicts Only</span>
        </label>

        {/* Focus Entity Select */}
        <div className="flex items-center gap-2 border-l border-zinc-800/80 pl-3">
          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Focus Entity</span>
          <select
            value={selectedEntityId}
            onChange={(e) => {
              setSelectedEntityId(e.target.value);
              onNodeClick(null);
            }}
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-purple-500 font-medium max-w-[10rem] truncate"
          >
            <option value="ALL">All Entities</option>
            {entitiesList.map((ent: any) => (
              <option key={ent.id} value={ent.id}>
                {ent.text} ({ent.entityType})
              </option>
            ))}
          </select>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1 border-l border-zinc-800/80 pl-3">
          <button
            onClick={runLayout}
            className="p-1.5 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer flex items-center gap-1"
            title="Reset layout layout using fcose force-directed"
          >
            {/* Refresh layout icon */}
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18.5" />
            </svg>
            <span>Reset</span>
          </button>
        </div>

      </div>

      {/* Graph Canvas Div */}
      <div ref={containerRef} className="flex-1 w-full h-full relative" />
      
      {/* Legend overlay */}
      <div className="absolute bottom-4 left-4 z-20 bg-zinc-900/60 backdrop-blur border border-zinc-800/50 p-3 rounded-xl shadow text-[9px] text-zinc-400 space-y-1.5 pointer-events-none select-none max-w-xs">
        <span className="font-bold text-zinc-500 uppercase tracking-widest text-[8px] block mb-1">Graph Legend</span>
        <div className="flex items-center gap-2">
          <span className="w-4 h-2.5 bg-zinc-950 border border-zinc-400 rounded-sm inline-block" />
          <span>Paper Node</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-2 bg-emerald-900 border border-emerald-500 rounded-sm inline-block" />
          <span>Claim (Supports Relationship)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-2 bg-red-900 border border-rose-500 rounded-sm inline-block" />
          <span>Claim (Contradicts/Refutes)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-0.5 h-0.5 border-4 border-transparent border-t-purple-400 border-r-purple-400 inline-block transform rotate-45" />
          <span>Canonical Entity Node (MeSH mapped)</span>
        </div>
        <div className="flex items-center gap-2 border-t border-zinc-800/50 pt-1.5 mt-1">
          <span className="w-4 h-0.5 bg-red-500 inline-block" />
          <span>Red Line: Contradicts / Conflicts Edge</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-indigo-500 border-t border-dashed inline-block" />
          <span>Indigo Dash: Mentions Entity</span>
        </div>
      </div>

    </div>
  );
}
