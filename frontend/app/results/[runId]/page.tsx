"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { API_BASE, WS_BASE } from "../../../utils/api";

const ClaimGraph = dynamic(() => import("../../../components/ClaimGraph"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-zinc-950 text-zinc-500 text-sm font-semibold">
      Loading claim network canvas...
    </div>
  ),
});

// --- Types ---
export interface Entity {
  text: string;
  canonical_id?: string;
  entity_type: string;
}

export interface Claim {
  id: string;
  text: string;
  normalized_text?: string;
  paper_id: string;
  section: string;
  authors: string[];
  year: number;
  confidence_score: number;
  claim_type: string;
  polarity: string;
  entities: Entity[];
  population: string;
  context: string;
  quote_anchor: string;
  sample_size?: number;
  study_design: string;
  is_primary_finding: boolean;
}

export interface ContradictionPair {
  claim_a: Claim;
  claim_b: Claim;
  contradiction_score: number;
  contradiction_type: string;
  explanation: string;
  scope_note: string;
  temporal_resolution?: string;
  is_genuine: boolean;
}

export interface SynthesisReport {
  summary: string;
  contradictions: ContradictionPair[];
  consensus_scores: Record<string, number>;
  total_papers: number;
  total_claims: number;
  metadata?: any;
}

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params?.runId as string;

  // --- States ---
  const [status, setStatus] = useState<"LOADING" | "RUNNING" | "COMPLETED" | "FAILED">("LOADING");
  const [progress, setProgress] = useState<{
    papers_fetched: number;
    claims_extracted: number;
    contradictions_found: number;
    error_message?: string;
  }>({
    papers_fetched: 0,
    claims_extracted: 0,
    contradictions_found: 0,
  });

  const [report, setReport] = useState<SynthesisReport | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [graphData, setGraphData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Active Tab
  const [activeTab, setActiveTab] = useState<"contradictions" | "graph" | "consensus">("contradictions");

  // Filter & Sort States
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [genuineFilter, setGenuineFilter] = useState<string>("ALL");
  const [minScore, setMinScore] = useState<number>(0.0);
  const [sortBy, setSortBy] = useState<"score_desc" | "score_asc" | "year_desc">("score_desc");

  // Selection/Detail State
  const [selectedPaper, setSelectedPaper] = useState<any | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null);
  const [selectedContradiction, setSelectedContradiction] = useState<ContradictionPair | null>(null);

  // References list compiled from claims
  const papersMap = useMemo(() => {
    const map = new Map<string, { authors: string[]; year: number; title?: string; journal?: string; doi?: string }>();
    claims.forEach((c) => {
      if (!map.has(c.paper_id)) {
        map.set(c.paper_id, {
          authors: c.authors,
          year: c.year,
        });
      }
    });

    // If graph data contains paper nodes, enrich the map with title/journal/doi
    if (graphData?.elements?.nodes) {
      graphData.elements.nodes.forEach((node: any) => {
        if (node.data?.type === "paper") {
          const pmid = node.data.id;
          const existing = map.get(pmid) || { authors: node.data.authors || [], year: node.data.year || 0 };
          map.set(pmid, {
            ...existing,
            title: node.data.title,
            journal: node.data.journal,
            doi: node.data.doi,
          });
        }
      });
    }

    return map;
  }, [claims, graphData]);

  // Fetch results once completed
  const fetchFinalResults = async (targetId: string) => {
    try {
      // 1. Fetch Report
      const repRes = await fetch(`${API_BASE}/api/results/${targetId}`);
      if (!repRes.ok) throw new Error("Failed to load report synthesis.");
      const repData = await repRes.json();
      setReport(repData);

      // 2. Fetch Claims
      const claimsRes = await fetch(`${API_BASE}/api/claims/${targetId}`);
      if (claimsRes.ok) {
        const claimsData = await claimsRes.json();
        setClaims(claimsData);
      }

      // 3. Fetch Graph
      const graphRes = await fetch(`${API_BASE}/api/graph/${targetId}`);
      if (graphRes.ok) {
        const graphData = await graphRes.json();
        setGraphData(graphData);
      }

      setStatus("COMPLETED");
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to load run details.");
      setStatus("FAILED");
    }
  };

  // Status Check & WebSocket hook
  useEffect(() => {
    if (!runId) return;

    let ws: WebSocket | null = null;
    let pollInterval: NodeJS.Timeout | null = null;

    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/status/${runId}`);
        if (!res.ok) {
          throw new Error("Could not find this analysis run.");
        }
        const data = await res.json();
        
        setProgress({
          papers_fetched: data.papers_fetched || 0,
          claims_extracted: data.claims_extracted || 0,
          contradictions_found: data.contradictions_found || 0,
        });

        if (data.status === "COMPLETED") {
          await fetchFinalResults(runId);
        } else if (data.status === "FAILED") {
          setError(data.error_message || "The analysis run failed during processing.");
          setStatus("FAILED");
        } else {
          // RUNNING - Connect websocket for updates
          setStatus("RUNNING");
          connectWebSocket();
        }
      } catch (err: any) {
        console.error(err);
        setError(err.message || "Failed to poll run status.");
        setStatus("FAILED");
      }
    };

    const connectWebSocket = () => {
      if (ws) return;
      
      const wsUrl = `${WS_BASE}/api/ws/${runId}`;
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setProgress({
            papers_fetched: data.papers_fetched || 0,
            claims_extracted: data.claims_extracted || 0,
            contradictions_found: data.contradictions_found || 0,
            error_message: data.error_message,
          });

          if (data.status === "COMPLETED") {
            ws?.close();
            fetchFinalResults(runId);
          } else if (data.status === "FAILED") {
            ws?.close();
            setError(data.error_message || "The analysis run failed.");
            setStatus("FAILED");
          }
        } catch (e) {
          console.error("Error parsing WS message:", e);
        }
      };

      ws.onerror = (e) => {
        console.warn("WebSocket error, falling back to polling", e);
        startPolling();
      };

      ws.onclose = () => {
        // If still running and ws closed, fallback to polling
        if (status === "RUNNING") {
          startPolling();
        }
      };
    };

    const startPolling = () => {
      if (pollInterval) return;
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/status/${runId}`);
          if (res.ok) {
            const data = await res.json();
            setProgress({
              papers_fetched: data.papers_fetched || 0,
              claims_extracted: data.claims_extracted || 0,
              contradictions_found: data.contradictions_found || 0,
            });

            if (data.status === "COMPLETED") {
              if (pollInterval) clearInterval(pollInterval);
              await fetchFinalResults(runId);
            } else if (data.status === "FAILED") {
              if (pollInterval) clearInterval(pollInterval);
              setError(data.error_message || "Analysis failed.");
              setStatus("FAILED");
            }
          }
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 3000);
    };

    // Initial Trigger
    checkStatus();

    return () => {
      if (ws) ws.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [runId]);

  const handleNodeClick = (nodeData: any) => {
    if (!nodeData) {
      setSelectedClaim(null);
      return;
    }

    if (nodeData.type === "claim") {
      const fullClaim = claims.find((c) => String(c.id) === String(nodeData.id));
      if (fullClaim) {
        setSelectedClaim(fullClaim);
        setSelectedPaper(null);
        setSelectedContradiction(null);
      }
    } else if (nodeData.type === "paper") {
      const mappedMeta = papersMap.get(nodeData.id);
      setSelectedPaper({
        pmid: nodeData.id,
        title: nodeData.title || mappedMeta?.title,
        authors: nodeData.authors || mappedMeta?.authors || [],
        year: nodeData.year || mappedMeta?.year || 0,
        journal: nodeData.journal || mappedMeta?.journal,
        doi: nodeData.doi || mappedMeta?.doi,
      });
      setSelectedClaim(null);
      setSelectedContradiction(null);
    } else {
      setSelectedClaim(null);
      setSelectedContradiction(null);
    }
  };

  const handleEdgeClick = (edgeData: any) => {
    if (!edgeData) {
      if (activeTab === "graph") {
        setSelectedContradiction(null);
      }
      return;
    }
    if (edgeData.type === "CONTRADICTS" || edgeData.type === "SUPERSEDES") {
      const pair = report?.contradictions.find(
        (p) => 
          (String(p.claim_a.id) === String(edgeData.source) && String(p.claim_b.id) === String(edgeData.target)) ||
          (String(p.claim_b.id) === String(edgeData.source) && String(p.claim_a.id) === String(edgeData.target))
      );
      if (pair) {
        setSelectedContradiction(pair);
        setSelectedClaim(null);
      }
    }
  };

  // Click handler for inline citations
  const handleCitationClick = (citationText: string) => {
    // citationText is usually something like "Author, Year"
    const parts = citationText.split(",");
    const authorLast = parts[0]?.trim().toLowerCase();
    const year = parseInt(parts[1]?.trim() || "0");

    // Search papersMap for a match
    let matchedPmid: string | null = null;
    let matchedPaper: any = null;

    for (const [pmid, meta] of Array.from(papersMap.entries())) {
      const matchYear = meta.year === year;
      const matchAuthor = meta.authors.some(a => a.toLowerCase().includes(authorLast));
      
      if (matchYear && (matchAuthor || authorLast === "author")) {
        matchedPmid = pmid;
        matchedPaper = {
          pmid,
          ...meta,
        };
        break;
      }
    }

    if (matchedPaper) {
      setSelectedPaper(matchedPaper);
    } else {
      // Fallback: search just by year
      const yearMatches = Array.from(papersMap.entries()).filter(([_, meta]) => meta.year === year);
      if (yearMatches.length > 0) {
        setSelectedPaper({ pmid: yearMatches[0][0], ...yearMatches[0][1] });
      }
    }
  };

  // Render citation-clickable summary
  const renderSummaryWithCitations = (summaryText: string) => {
    if (!summaryText) return null;

    // Matches citations in formats like [Author, Year] or [Author et al., Year]
    const regex = /\[([A-Za-z\s\-\.\'\’]+,\s*\d{4})\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(summaryText)) !== null) {
      const matchIndex = match.index;
      const matchText = match[0];
      const citationContent = match[1];

      // Add preceding plain text
      if (matchIndex > lastIndex) {
        parts.push(summaryText.substring(lastIndex, matchIndex));
      }

      // Add citation button
      parts.push(
        <button
          key={matchIndex}
          onClick={() => handleCitationClick(citationContent)}
          className="inline-flex items-center px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs font-semibold hover:bg-purple-500/20 active:scale-95 transition-all mx-0.5 font-mono cursor-pointer"
        >
          {matchText}
        </button>
      );

      lastIndex = regex.lastIndex;
    }

    // Add trailing text
    if (lastIndex < summaryText.length) {
      parts.push(summaryText.substring(lastIndex));
    }

    return <p className="text-zinc-300 text-sm md:text-base leading-relaxed whitespace-pre-wrap">{parts}</p>;
  };

  // Filter and Sort Contradiction list
  const filteredContradictions = useMemo(() => {
    if (!report?.contradictions) return [];

    return report.contradictions
      .filter((p) => {
        // Type Filter
        if (typeFilter !== "ALL" && p.contradiction_type !== typeFilter) return false;
        
        // Genuineness Filter
        if (genuineFilter === "GENUINE" && !p.is_genuine) return false;
        if (genuineFilter === "MISMATCH" && p.is_genuine) return false;

        // Score Filter
        if (p.contradiction_score < minScore) return false;

        return true;
      })
      .sort((a, b) => {
        if (sortBy === "score_desc") return b.contradiction_score - a.contradiction_score;
        if (sortBy === "score_asc") return a.contradiction_score - b.contradiction_score;
        if (sortBy === "year_desc") return Math.max(b.claim_a.year, b.claim_b.year) - Math.max(a.claim_a.year, a.claim_b.year);
        return 0;
      });
  }, [report, typeFilter, genuineFilter, minScore, sortBy]);

  // Statistics summaries
  const stats = useMemo(() => {
    if (!report) return { papers: 0, claims: 0, contradictions: 0, avgConfidence: 0 };

    const totalConf = claims.reduce((acc, c) => acc + c.confidence_score, 0);
    const avgConf = claims.length > 0 ? (totalConf / claims.length) * 100 : 0;

    return {
      papers: report.total_papers || papersMap.size,
      claims: report.total_claims || claims.length,
      contradictions: report.contradictions?.length || 0,
      avgConfidence: avgConf,
    };
  }, [report, claims, papersMap]);

  // --- RENDER STATES ---

  // LOADING State
  if (status === "LOADING") {
    return (
      <div className="relative min-h-screen bg-zinc-950 text-zinc-100 font-sans overflow-x-hidden flex flex-col animate-pulse">
        {/* Background patterns */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f2e04_1px,transparent_1px),linear-gradient(to_bottom,#1f1f2e04_1px,transparent_1px)] bg-[size:3rem_3rem] pointer-events-none z-0 opacity-35" />

        {/* Header Skeleton */}
        <header className="sticky top-0 w-full bg-zinc-950/80 backdrop-blur-md border-b border-zinc-900 z-30 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-9 h-9 bg-zinc-900 border border-zinc-800 rounded-lg shrink-0" />
            <div className="space-y-2">
              <div className="h-5 w-48 bg-zinc-800 rounded-md" />
              <div className="h-3.5 w-32 bg-zinc-900 rounded-md" />
            </div>
          </div>
          <div className="flex items-center bg-zinc-900/60 border border-zinc-800 p-1 rounded-xl gap-2 w-72 h-10" />
        </header>

        {/* Main Grid Skeleton */}
        <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-8 z-10 flex flex-col gap-8">
          {/* Stats Bar Skeleton */}
          <section className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-zinc-900/30 border border-zinc-900 rounded-xl p-4 flex flex-col justify-between h-24">
                <div className="h-3 w-20 bg-zinc-800 rounded-md" />
                <div className="h-7 w-12 bg-zinc-800 rounded-md mt-2" />
              </div>
            ))}
          </section>

          {/* Split layout: Summary Panel (left) & Contradiction Cards (right) Skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
            {/* Summary Synthesis Panel Skeleton */}
            <section className="lg:col-span-1 space-y-6">
              <div className="relative bg-gradient-to-br from-indigo-950/5 to-purple-950/5 border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-4">
                <div className="flex items-center gap-2 pb-3 border-b border-zinc-800/80">
                  <div className="w-5 h-5 bg-zinc-800 rounded" />
                  <div className="h-4 w-32 bg-zinc-800 rounded" />
                </div>
                <div className="space-y-2">
                  <div className="h-4 w-full bg-zinc-800 rounded" />
                  <div className="h-4 w-5/6 bg-zinc-800 rounded" />
                  <div className="h-4 w-11/12 bg-zinc-800 rounded" />
                  <div className="h-4 w-4/5 bg-zinc-800 rounded" />
                  <div className="h-4 w-full bg-zinc-800 rounded" />
                </div>
              </div>
            </section>

            {/* Contradiction Cards Skeleton */}
            <section className="lg:col-span-2 space-y-6">
              {/* Filters Row Skeleton */}
              <div className="bg-zinc-900/20 border border-zinc-900 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 h-16" />

              {/* Cards List Skeleton */}
              <div className="space-y-4">
                {[...Array(3)].map((_, idx) => (
                  <div key={idx} className="bg-zinc-900/10 border border-zinc-900 rounded-2xl p-5 space-y-4">
                    <div className="flex justify-between items-center gap-4">
                      <div className="space-y-3 flex-1">
                        <div className="flex gap-2 items-center">
                          <div className="w-4 h-4 bg-zinc-800 rounded-full shrink-0" />
                          <div className="h-4 w-2/3 bg-zinc-800 rounded" />
                        </div>
                        <div className="flex gap-2 items-center">
                          <div className="w-4 h-4 bg-zinc-800 rounded-full shrink-0" />
                          <div className="h-4 w-3/4 bg-zinc-800 rounded" />
                        </div>
                      </div>
                      <div className="w-24 h-8 bg-zinc-800 rounded-lg shrink-0" />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </main>
      </div>
    );
  }

  // FAILED State
  if (status === "FAILED") {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6">
        <div className="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center shadow-2xl relative">
          <div className="absolute inset-0 bg-red-500/5 rounded-2xl pointer-events-none" />
          <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400 mx-auto mb-6">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Analysis Failed</h2>
          <p className="text-zinc-400 text-sm leading-relaxed mb-6">
            {error || "An unexpected error occurred during processing."}
          </p>
          <button
            onClick={() => router.push("/")}
            className="w-full py-3 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-200 rounded-lg text-sm font-semibold transition-colors shadow-lg cursor-pointer"
          >
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // RUNNING (Active Pipeline progress) State
  if (status === "RUNNING") {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6 relative overflow-hidden">
        {/* Background Gradients */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-purple-500/5 blur-[120px] rounded-full pointer-events-none" />
        
        <div className="max-w-lg w-full bg-zinc-900/40 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-8 shadow-2xl relative z-10">
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-semibold font-mono mb-4 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
              Pipeline Run in Progress
            </div>
            <h2 className="text-xl font-bold text-white mb-1">Synthesizing Literature</h2>
            <p className="text-zinc-500 text-xs font-mono truncate max-w-xs mx-auto">
              ID: {runId}
            </p>
          </div>

          {/* Stats Progress Bars */}
          <div className="space-y-6 mb-8">
            
            {/* Papers Ingested */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-zinc-400 uppercase tracking-wider">1. Ingesting Papers</span>
                <span className="text-purple-400 font-mono font-bold">{progress.papers_fetched} fetched</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-950 rounded-full overflow-hidden border border-zinc-800/50">
                <div 
                  className="h-full bg-gradient-to-r from-purple-600 to-indigo-600 rounded-full transition-all duration-500 ease-out" 
                  style={{ width: `${Math.min((progress.papers_fetched / 25) * 100, 100)}%` }}
                />
              </div>
            </div>

            {/* Claims Extracted */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-zinc-400 uppercase tracking-wider">2. Extracting & Grounding Claims</span>
                <span className="text-indigo-400 font-mono font-bold">{progress.claims_extracted} extracted</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-950 rounded-full overflow-hidden border border-zinc-800/50">
                <div 
                  className="h-full bg-gradient-to-r from-indigo-600 to-cyan-600 rounded-full transition-all duration-500 ease-out" 
                  style={{ width: `${Math.min((progress.claims_extracted / 125) * 100, 100)}%` }}
                />
              </div>
            </div>

            {/* Contradictions Found */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-zinc-400 uppercase tracking-wider">3. Analyzing Contradictions</span>
                <span className="text-cyan-400 font-mono font-bold">{progress.contradictions_found} flagged</span>
              </div>
              <div className="h-1.5 w-full bg-zinc-950 rounded-full overflow-hidden border border-zinc-800/50">
                <div 
                  className="h-full bg-gradient-to-r from-cyan-600 to-purple-600 rounded-full transition-all duration-500 ease-out animate-pulse" 
                  style={{ width: progress.claims_extracted > 0 ? "50%" : "0%" }}
                />
              </div>
            </div>

          </div>

          {/* Loader text */}
          <div className="p-4 bg-zinc-950/50 border border-zinc-800/50 rounded-xl flex items-center justify-center gap-3">
            <svg className="animate-spin h-4 w-4 text-purple-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-zinc-400 text-xs font-medium">
              Executing NLI contradiction analysis and LLM validation...
            </span>
          </div>
        </div>
      </div>
    );
  }

  // COMPLETED Dashboard Render
  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-100 font-sans selection:bg-purple-500/30 selection:text-purple-200 overflow-x-hidden flex flex-col">
      {/* Background patterns */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f2e04_1px,transparent_1px),linear-gradient(to_bottom,#1f1f2e04_1px,transparent_1px)] bg-[size:3rem_3rem] pointer-events-none z-0 opacity-35" />

      {/* Header */}
      <header className="sticky top-0 w-full bg-zinc-950/80 backdrop-blur-md border-b border-zinc-900 z-30 px-4 md:px-6 py-3.5 md:py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div className="flex items-center gap-3 md:gap-4 min-w-0 w-full sm:w-auto">
          <button
            onClick={() => router.push("/")}
            className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors cursor-pointer shrink-0"
            title="Back to search"
          >
            {/* Back arrow SVG */}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="font-semibold text-sm md:text-base lg:text-lg text-white truncate max-w-[180px] xs:max-w-[260px] sm:max-w-[320px] md:max-w-xl lg:max-w-2xl">
              {report?.metadata?.query || `Query: "${report?.summary ? report.summary.substring(0, 40) + "..." : runId}"`}
            </h1>
            <span className="text-zinc-500 text-[10px] block font-mono -mt-0.5 uppercase tracking-widest">
              Report Synthesis • {runId.startsWith("demo_") ? "PRE-LOADED DEMO" : "LIVE PIPELINE"}
            </span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center bg-zinc-900/60 border border-zinc-800 p-1 rounded-xl shrink-0 w-full sm:w-auto justify-between sm:justify-start">
          <button
            id="tab-contradictions"
            onClick={() => setActiveTab("contradictions")}
            className={`flex-1 sm:flex-initial text-center px-3 md:px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "contradictions" ? "bg-purple-600 text-white shadow" : "text-zinc-400 hover:text-white"
            }`}
          >
            Contradiction Report
          </button>
          <button
            id="tab-graph"
            onClick={() => setActiveTab("graph")}
            className={`flex-1 sm:flex-initial text-center px-3 md:px-4 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "graph" ? "bg-purple-600 text-white shadow" : "text-zinc-400 hover:text-white"
            }`}
          >
            Interactive Graph
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-8 z-10 flex flex-col gap-8">
        
        {/* TAB 1: CONTRADICTIONS REPORT */}
        {activeTab === "contradictions" && (
          <>
            {/* Stats Bar */}
            <section className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
              
              <div className="bg-zinc-900/30 border border-zinc-900 rounded-xl p-4 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Papers Ingested</span>
                <span className="text-2xl font-bold text-white font-mono mt-2">{stats.papers}</span>
              </div>

              <div className="bg-zinc-900/30 border border-zinc-900 rounded-xl p-4 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Claims Extracted</span>
                <span className="text-2xl font-bold text-white font-mono mt-2">{stats.claims}</span>
              </div>

              <div className="bg-zinc-900/30 border border-zinc-900 rounded-xl p-4 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Contradiction Pairs</span>
                <span className="text-2xl font-bold text-red-400 font-mono mt-2">{stats.contradictions}</span>
              </div>

              <div className="bg-zinc-900/30 border border-zinc-900 rounded-xl p-4 flex flex-col justify-between">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Average Confidence</span>
                <span className="text-2xl font-bold text-emerald-400 font-mono mt-2">{stats.avgConfidence.toFixed(1)}%</span>
              </div>

            </section>

            {/* Split layout: Summary Panel (left) & Contradiction Cards (right) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
              
              {/* Summary Synthesis Panel */}
              <section className="lg:col-span-1 space-y-6 lg:sticky lg:top-24">
                <div className="relative bg-gradient-to-br from-indigo-950/10 to-purple-950/10 border border-zinc-800 rounded-2xl p-6 shadow-xl overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-purple-500/5 rounded-full blur-2xl pointer-events-none" />
                  
                  <div className="flex items-center gap-2 mb-4 pb-3 border-b border-zinc-800/80">
                    <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <h3 className="font-semibold text-sm uppercase tracking-wider text-zinc-300">Narrative Synthesis</h3>
                  </div>

                  {report?.summary ? renderSummaryWithCitations(report.summary) : (
                    <p className="text-zinc-500 text-sm italic">No narrative synthesis available.</p>
                  )}
                  
                  <div className="mt-4 p-3 bg-zinc-950 border border-zinc-900 rounded-xl text-[10px] text-zinc-500 leading-relaxed">
                    <span className="font-semibold text-zinc-400 block mb-0.5">Interactive Grounding</span>
                    Click on any citation above to reveal the full source paper and its extracted clinical findings.
                  </div>
                </div>
              </section>

              {/* Contradiction Cards Section */}
              <section className="lg:col-span-2 space-y-6">
                
                {/* Filters Row */}
                <div className="bg-zinc-900/20 border border-zinc-900 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex flex-wrap items-center gap-4 text-xs">
                    
                    {/* Filter by Type */}
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Conflict Type</span>
                      <select
                        value={typeFilter}
                        onChange={(e) => setTypeFilter(e.target.value)}
                        className="bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 focus:outline-none focus:border-purple-500 font-medium text-zinc-300"
                      >
                        <option value="ALL">All Types</option>
                        <option value="DIRECT_NEGATION">Direct Negation</option>
                        <option value="QUANTITATIVE_CONFLICT">Quantitative Conflict</option>
                        <option value="DIRECTION_REVERSAL">Direction Reversal</option>
                        <option value="SCOPE_MISMATCH">Scope Mismatch</option>
                        <option value="TEMPORAL_SUPERSESSION">Temporal Supersession</option>
                        <option value="METHODOLOGICAL_CONFLICT">Methodological Conflict</option>
                      </select>
                    </div>

                    {/* Filter by Genuineness */}
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Genuineness</span>
                      <select
                        value={genuineFilter}
                        onChange={(e) => setGenuineFilter(e.target.value)}
                        className="bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 focus:outline-none focus:border-purple-500 font-medium text-zinc-300"
                      >
                        <option value="ALL">All Conflicts</option>
                        <option value="GENUINE">Genuine Contradictions</option>
                        <option value="MISMATCH">Scope Mismatches</option>
                      </select>
                    </div>

                    {/* Sort By */}
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Sort By</span>
                      <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value as any)}
                        className="bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 focus:outline-none focus:border-purple-500 font-medium text-zinc-300"
                      >
                        <option value="score_desc">Conflict Score (High → Low)</option>
                        <option value="score_asc">Conflict Score (Low → High)</option>
                        <option value="year_desc">Newest Findings</option>
                      </select>
                    </div>

                  </div>

                  {/* Score Filter slider */}
                  <div className="flex flex-col gap-1 justify-end">
                    <div className="flex justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      <span>Min Score Threshold</span>
                      <span className="text-purple-400 font-mono">{(minScore * 100).toFixed(0)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={minScore}
                      onChange={(e) => setMinScore(parseFloat(e.target.value))}
                      className="w-full md:w-36 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500"
                    />
                  </div>
                </div>

                {/* Cards List */}
                <div className="space-y-4">
                  {filteredContradictions.length > 0 ? (
                    filteredContradictions.map((pair, idx) => {
                      const isExpanded = selectedContradiction === pair;
                      return (
                        <div
                          key={idx}
                          className={`bg-zinc-900/30 border hover:border-zinc-800 rounded-2xl overflow-hidden transition-all duration-300 ${
                            isExpanded ? "border-purple-500/30 ring-1 ring-purple-500/10" : "border-zinc-900"
                          }`}
                        >
                          {/* Card Header (Claim vs Claim preview) */}
                          <div 
                            onClick={() => setSelectedContradiction(isExpanded ? null : pair)}
                            className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 cursor-pointer"
                          >
                            <div className="space-y-3 flex-1">
                              {/* Claim A preview */}
                              <div className="flex gap-2 items-start text-sm">
                                <span className="font-bold text-zinc-500 mt-0.5 text-xs shrink-0 select-none">A</span>
                                <p className="text-zinc-300 font-medium">{pair.claim_a.text}</p>
                              </div>
                              {/* Claim B preview */}
                              <div className="flex gap-2 items-start text-sm">
                                <span className="font-bold text-zinc-500 mt-0.5 text-xs shrink-0 select-none">B</span>
                                <p className="text-zinc-400 font-medium">{pair.claim_b.text}</p>
                              </div>
                            </div>

                            {/* Badge and expand trigger */}
                            <div className="flex md:flex-col items-center md:items-end justify-between w-full md:w-auto gap-4 md:gap-2 pt-3 md:pt-0 border-t border-zinc-800 md:border-t-0 shrink-0">
                              <span className="px-2.5 py-1 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono font-bold">
                                {(pair.contradiction_score * 100).toFixed(0)}% Conflict
                              </span>
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase ${
                                  pair.is_genuine 
                                    ? "bg-amber-500/10 border border-amber-500/20 text-amber-400"
                                    : "bg-zinc-800 border border-zinc-700 text-zinc-400"
                                }`}>
                                  {pair.is_genuine ? "Genuine" : "Scope Diff"}
                                </span>
                                <svg className={`w-4 h-4 text-zinc-500 transition-transform ${isExpanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                                </svg>
                              </div>
                            </div>
                          </div>

                          {/* Expanded Content Details */}
                          {isExpanded && (
                            <div className="border-t border-zinc-800/60 bg-zinc-950/40 p-5 space-y-5">
                              
                              {/* Type & metadata */}
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs border-b border-zinc-800/40 pb-4">
                                <div>
                                  <span className="text-zinc-500 block font-bold uppercase tracking-widest text-[9px] mb-1">Contradiction Type</span>
                                  <span className="px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 font-semibold font-mono uppercase">
                                    {pair.contradiction_type.replace("_", " ")}
                                  </span>
                                </div>
                                <div>
                                  <span className="text-zinc-500 block font-bold uppercase tracking-widest text-[9px] mb-1">Genuineness Verdict</span>
                                  <span className="text-zinc-300 font-medium">
                                    {pair.is_genuine 
                                      ? "Verified as a direct logical contradiction on identical topic scope."
                                      : "Flagged as a contradiction originating from differences in experimental scope (e.g. population, model, dosage)."}
                                  </span>
                                </div>
                              </div>

                              {/* Judge Explanation */}
                              <div>
                                <span className="text-zinc-500 block font-bold uppercase tracking-widest text-[9px] mb-1">LLM Evaluation Summary</span>
                                <p className="text-zinc-300 text-sm leading-relaxed">{pair.explanation}</p>
                              </div>

                              {/* Scope Notes */}
                              {pair.scope_note && (
                                <div className="p-3 bg-zinc-950 border border-zinc-900 rounded-xl">
                                  <span className="text-zinc-400 block font-semibold text-xs mb-1">Scope Analysis</span>
                                  <p className="text-zinc-400 text-xs leading-relaxed">{pair.scope_note}</p>
                                </div>
                              )}

                              {/* Temporal Resolution */}
                              {pair.temporal_resolution && (
                                <div className="p-3 bg-purple-950/10 border border-purple-500/10 rounded-xl">
                                  <span className="text-purple-400 block font-semibold text-xs mb-1">Temporal Resolution</span>
                                  <p className="text-zinc-400 text-xs leading-relaxed">{pair.temporal_resolution}</p>
                                </div>
                              )}

                              {/* Sources Side-by-Side */}
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-3 border-t border-zinc-800/40">
                                
                                {/* Source Paper A */}
                                <div className="space-y-2">
                                  <div className="flex justify-between items-center">
                                    <span className="text-zinc-500 font-bold uppercase tracking-widest text-[9px]">Source Claim A</span>
                                    <button
                                      onClick={() => handleCitationClick(`${pair.claim_a.authors[0] || "Author"}, ${pair.claim_a.year}`)}
                                      className="text-purple-400 hover:text-purple-300 text-[10px] font-semibold flex items-center gap-1 cursor-pointer"
                                    >
                                      View Paper
                                    </button>
                                  </div>
                                  <div className="p-3 bg-zinc-950/70 border border-zinc-900 rounded-xl text-xs space-y-2">
                                    <div className="font-mono text-zinc-500">
                                      {pair.claim_a.authors.join(", ")} ({pair.claim_a.year})
                                    </div>
                                    <div className="font-semibold text-zinc-300">
                                      "{pair.claim_a.text}"
                                    </div>
                                    {pair.claim_a.quote_anchor && (
                                      <div className="text-[11px] text-zinc-500 border-l border-zinc-800 pl-2">
                                        <span className="font-semibold text-zinc-600 block text-[9px] uppercase tracking-wider">Quote Anchor</span>
                                        "{pair.claim_a.quote_anchor}"
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* Source Paper B */}
                                <div className="space-y-2">
                                  <div className="flex justify-between items-center">
                                    <span className="text-zinc-500 font-bold uppercase tracking-widest text-[9px]">Source Claim B</span>
                                    <button
                                      onClick={() => handleCitationClick(`${pair.claim_b.authors[0] || "Author"}, ${pair.claim_b.year}`)}
                                      className="text-purple-400 hover:text-purple-300 text-[10px] font-semibold flex items-center gap-1 cursor-pointer"
                                    >
                                      View Paper
                                    </button>
                                  </div>
                                  <div className="p-3 bg-zinc-950/70 border border-zinc-900 rounded-xl text-xs space-y-2">
                                    <div className="font-mono text-zinc-500">
                                      {pair.claim_b.authors.join(", ")} ({pair.claim_b.year})
                                    </div>
                                    <div className="font-semibold text-zinc-300">
                                      "{pair.claim_b.text}"
                                    </div>
                                    {pair.claim_b.quote_anchor && (
                                      <div className="text-[11px] text-zinc-500 border-l border-zinc-800 pl-2">
                                        <span className="font-semibold text-zinc-600 block text-[9px] uppercase tracking-wider">Quote Anchor</span>
                                        "{pair.claim_b.quote_anchor}"
                                      </div>
                                    )}
                                  </div>
                                </div>

                              </div>

                            </div>
                          )}
                        </div>
                      );
                    })
                  ) : report?.contradictions && report.contradictions.length === 0 ? (
                    <div className="relative bg-gradient-to-br from-emerald-950/10 to-zinc-950/20 border border-emerald-500/25 rounded-2xl p-8 text-center shadow-xl overflow-hidden animate-fadeIn">
                      <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
                      
                      <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mx-auto mb-5 shadow-lg shadow-emerald-500/10 animate-pulse">
                        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      
                      <h3 className="text-lg font-bold text-white mb-2">Scientific Consensus Achieved</h3>
                      <p className="text-zinc-400 text-sm leading-relaxed max-w-lg mx-auto mb-4">
                        Our NLI models and LLM verification stage detected no contradictory findings across the ingested literature on this topic. The analyzed papers represent an aligned consensus.
                      </p>
                      <div className="inline-flex gap-4 items-center justify-center p-3 bg-zinc-950 border border-zinc-900 rounded-xl text-xs font-mono text-zinc-500">
                        <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> {claims.length} Claims Aligned</span>
                        <span className="text-zinc-800">|</span>
                        <span>0 Contradictions</span>
                      </div>
                    </div>
                  ) : (
                    <div className="p-12 border border-zinc-900 rounded-2xl text-center text-zinc-500 text-sm">
                      No contradictions match the active filter criteria. Try lowering the score threshold.
                    </div>
                  )}
                </div>

              </section>

            </div>
          </>
        )}

        {/* TAB 2: INTERACTIVE GRAPH (CYTOSCAPE GRAPH) */}
        {activeTab === "graph" && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-stretch h-[650px] w-full">
            <div className={`${selectedClaim || selectedContradiction ? "lg:col-span-3" : "lg:col-span-4"} h-full relative transition-all duration-300`}>
              {graphData ? (
                <ClaimGraph 
                  graphData={graphData} 
                  onNodeClick={handleNodeClick} 
                  onEdgeClick={handleEdgeClick} 
                />
              ) : (
                <div className="w-full h-full border border-zinc-800 rounded-2xl bg-zinc-900/20 flex items-center justify-center text-zinc-500 font-semibold text-sm">
                  No graph elements available.
                </div>
              )}
            </div>

            {/* Mobile backdrop for Selected Claim */}
            {selectedClaim && (
              <div 
                className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 lg:hidden animate-fadeIn"
                onClick={() => setSelectedClaim(null)}
              />
            )}

            {/* Sidebar Claim Details Panel */}
            {selectedClaim && (
              <div className="fixed bottom-0 left-0 right-0 max-h-[80vh] bg-zinc-900 border-t border-zinc-800 rounded-t-3xl p-6 z-50 overflow-y-auto flex flex-col justify-between shadow-2xl animate-slideUp lg:relative lg:bottom-auto lg:left-auto lg:right-auto lg:max-h-none lg:bg-zinc-900/40 lg:border lg:border-zinc-800 lg:rounded-2xl lg:p-5 lg:z-auto lg:shadow-xl lg:col-span-1 lg:flex lg:flex-col lg:overflow-y-auto lg:animate-slideIn">
                <div className="space-y-4">
                  <div className="flex justify-between items-start border-b border-zinc-850 pb-3">
                    <div>
                      <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest font-mono">
                        Claim Node Details
                      </span>
                      <h4 className="font-semibold text-xs text-zinc-500 font-mono mt-0.5">
                        UUID: {selectedClaim.id.toString().substring(0, 8)}...
                      </h4>
                    </div>
                    <button
                      onClick={() => setSelectedClaim(null)}
                      className="p-1 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-md transition-colors cursor-pointer"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  {/* Claim Text */}
                  <div className="space-y-1">
                    <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block">Extracted Assertion</span>
                    <p className="text-zinc-200 text-xs font-medium leading-relaxed bg-zinc-950/40 p-3 border border-zinc-900 rounded-xl">
                      "{selectedClaim.text}"
                    </p>
                  </div>

                  {/* Badges / Metrics */}
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="p-2 bg-zinc-950/40 border border-zinc-900 rounded-xl text-center">
                      <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest block mb-0.5">Polarity</span>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase inline-block ${
                        selectedClaim.polarity === "POSITIVE"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : selectedClaim.polarity === "NEGATIVE"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                      }`}>
                        {selectedClaim.polarity}
                      </span>
                    </div>

                    <div className="p-2 bg-zinc-950/40 border border-zinc-900 rounded-xl text-center">
                      <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest block mb-0.5">NLI Conf</span>
                      <span className="text-zinc-200 text-xs font-mono font-bold">
                        {(selectedClaim.confidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Study Design / Sample Size */}
                  <div className="text-xs space-y-2 border-y border-zinc-850 py-3 text-zinc-400">
                    <div className="flex justify-between">
                      <span className="text-zinc-500 font-semibold">Study Design:</span>
                      <span className="font-mono text-zinc-300 font-bold">{selectedClaim.study_design}</span>
                    </div>
                    {selectedClaim.sample_size && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500 font-semibold">Sample Size:</span>
                        <span className="font-mono text-zinc-300 font-bold">{selectedClaim.sample_size} subjects</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-zinc-500 font-semibold">Population:</span>
                      <span className="text-zinc-300 font-medium truncate max-w-[10rem]">{selectedClaim.population}</span>
                    </div>
                  </div>

                  {/* Quote Anchor (Highlighted) */}
                  {selectedClaim.quote_anchor && (
                    <div className="space-y-1">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block">Verbatim Quote Grounding</span>
                      <div className="bg-yellow-500/5 border border-yellow-500/20 text-yellow-300/90 text-xs p-3 rounded-xl leading-relaxed italic relative">
                        <div className="absolute top-1 right-2 font-serif text-yellow-500/20 text-xl leading-none select-none">”</div>
                        "{selectedClaim.quote_anchor}"
                      </div>
                    </div>
                  )}

                  {/* Entity Mentions */}
                  {selectedClaim.entities && selectedClaim.entities.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block">Linked Entities</span>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedClaim.entities.map((ent, idx) => (
                          <span
                            key={idx}
                            title={ent.canonical_id ? `MeSH ID: ${ent.canonical_id}` : undefined}
                            className="px-2 py-0.5 bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/20 text-purple-300 text-[10px] rounded font-medium cursor-help"
                          >
                            {ent.text}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Source Paper Details */}
                  {(() => {
                    const paperMeta = papersMap.get(selectedClaim.paper_id);
                    if (!paperMeta) return null;
                    return (
                      <div className="space-y-2 border-t border-zinc-850 pt-4">
                        <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block">Source Publication</span>
                        <div className="text-xs space-y-1 bg-zinc-950/40 p-3 border border-zinc-900 rounded-xl">
                          <h5 className="font-semibold text-zinc-200 leading-snug">{paperMeta.title || "Title not loaded"}</h5>
                          <p className="text-[11px] text-zinc-400 font-mono truncate">{paperMeta.authors?.join(", ")}</p>
                          <p className="text-[10px] text-zinc-500 italic">{paperMeta.journal ? `${paperMeta.journal}, ` : ""}{paperMeta.year}</p>
                          
                          <div className="flex gap-2.5 pt-2 border-t border-zinc-900/60 mt-1">
                            <a
                              href={`https://pubmed.ncbi.nlm.nih.gov/${selectedClaim.paper_id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[10px] text-purple-400 hover:text-purple-300 font-semibold flex items-center gap-1"
                            >
                              PMID: {selectedClaim.paper_id}
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                            </a>
                            {paperMeta.doi && (
                              <a
                                href={`https://doi.org/${paperMeta.doi}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[10px] text-purple-400 hover:text-purple-300 font-semibold flex items-center gap-1 border-l border-zinc-800 pl-2.5"
                              >
                                DOI Link
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                </div>

                <div className="pt-4 border-t border-zinc-850 mt-4">
                  <button
                    onClick={() => {
                      const paperMeta = papersMap.get(selectedClaim.paper_id);
                      if (paperMeta) {
                        setSelectedPaper({ pmid: selectedClaim.paper_id, ...paperMeta });
                      }
                    }}
                    className="w-full py-2 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                    </svg>
                    <span>Inspect Paper Findings</span>
                  </button>
                </div>
              </div>
            )}

            {/* Mobile backdrop for Selected Contradiction */}
            {selectedContradiction && !selectedClaim && (
              <div 
                className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 lg:hidden animate-fadeIn"
                onClick={() => setSelectedContradiction(null)}
              />
            )}

            {/* Sidebar Contradiction Details Panel */}
            {selectedContradiction && !selectedClaim && (
              <div className="fixed bottom-0 left-0 right-0 max-h-[80vh] bg-zinc-900 border-t border-zinc-800 rounded-t-3xl p-6 z-50 overflow-y-auto flex flex-col justify-between shadow-2xl animate-slideUp lg:relative lg:bottom-auto lg:left-auto lg:right-auto lg:max-h-none lg:bg-zinc-900/40 lg:border lg:border-zinc-800 lg:rounded-2xl lg:p-5 lg:z-auto lg:shadow-xl lg:col-span-1 lg:flex lg:flex-col lg:overflow-y-auto lg:animate-slideIn">
                <div className="space-y-4">
                  <div className="flex justify-between items-start border-b border-zinc-850 pb-3">
                    <div>
                      <span className="text-[10px] font-bold text-red-400 uppercase tracking-widest font-mono">
                        Conflict Edge Details
                      </span>
                      <h4 className="font-semibold text-xs text-zinc-500 font-mono mt-0.5">
                        Score: {(selectedContradiction.contradiction_score * 100).toFixed(0)}%
                      </h4>
                    </div>
                    <button
                      onClick={() => setSelectedContradiction(null)}
                      className="p-1 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-md transition-colors cursor-pointer"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  {/* Verdicts */}
                  <div className="flex gap-2">
                    <span className="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold uppercase font-mono">
                      {selectedContradiction.contradiction_type.replace("_", " ")}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono ${
                      selectedContradiction.is_genuine 
                        ? "bg-amber-500/10 border border-amber-500/20 text-amber-400"
                        : "bg-zinc-800 border border-zinc-700 text-zinc-400"
                    }`}>
                      {selectedContradiction.is_genuine ? "Genuine" : "Scope Mismatch"}
                    </span>
                  </div>

                  {/* Side-by-side assertions */}
                  <div className="space-y-3 border-y border-zinc-850 py-3 text-xs">
                    <div className="space-y-1">
                      <span className="font-bold text-zinc-500 block">Claim A ({selectedContradiction.claim_a.polarity})</span>
                      <p className="text-zinc-200 leading-relaxed bg-zinc-950/40 p-2.5 border border-zinc-900 rounded-lg">
                        "{selectedContradiction.claim_a.text}"
                        <span className="text-[10px] text-zinc-500 font-mono block mt-1">
                          — {selectedContradiction.claim_a.authors[0] || "Author"} et al. ({selectedContradiction.claim_a.year})
                        </span>
                      </p>
                    </div>

                    <div className="space-y-1">
                      <span className="font-bold text-zinc-500 block">Claim B ({selectedContradiction.claim_b.polarity})</span>
                      <p className="text-zinc-400 leading-relaxed bg-zinc-950/40 p-2.5 border border-zinc-900 rounded-lg">
                        "{selectedContradiction.claim_b.text}"
                        <span className="text-[10px] text-zinc-500 font-mono block mt-1">
                          — {selectedContradiction.claim_b.authors[0] || "Author"} et al. ({selectedContradiction.claim_b.year})
                        </span>
                      </p>
                    </div>
                  </div>

                  {/* Explanation */}
                  <div className="space-y-1">
                    <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block">Conflict Explanation</span>
                    <p className="text-zinc-300 text-xs leading-relaxed">
                      {selectedContradiction.explanation}
                    </p>
                  </div>

                  {/* Scope note */}
                  {selectedContradiction.scope_note && (
                    <div className="p-3 bg-zinc-950/50 border border-zinc-900 rounded-xl text-xs space-y-1">
                      <span className="font-semibold text-zinc-400 block text-[10px]">Scope Mismatch Analysis</span>
                      <p className="text-zinc-500 leading-relaxed text-[11px]">{selectedContradiction.scope_note}</p>
                    </div>
                  )}

                  {/* Temporal resolution */}
                  {selectedContradiction.temporal_resolution && (
                    <div className="p-3 bg-purple-950/15 border border-purple-500/10 rounded-xl text-xs space-y-1">
                      <span className="font-semibold text-purple-400 block text-[10px]">Temporal Resolution</span>
                      <p className="text-zinc-500 leading-relaxed text-[11px]">{selectedContradiction.temporal_resolution}</p>
                    </div>
                  )}

                </div>

                <div className="pt-4 border-t border-zinc-850 mt-4">
                  <button
                    onClick={() => {
                      setActiveTab("contradictions");
                    }}
                    className="w-full py-2 bg-red-600/10 hover:bg-red-600/20 border border-red-500/20 text-red-400 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1 cursor-pointer"
                  >
                    <span>View in Contradiction Cards</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

      </main>

      {/* MODAL: Paper metadata / clickable citations details */}
      {selectedPaper && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-6 animate-fadeIn">
          <div className="bg-zinc-900 border border-zinc-850 max-w-2xl w-full rounded-2xl p-6 shadow-2xl relative">
            
            {/* Close Button */}
            <button
              onClick={() => setSelectedPaper(null)}
              className="absolute top-4 right-4 p-1.5 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-400 hover:text-white transition-colors cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* Modal Body */}
            <div className="space-y-4">
              <span className="text-[10px] font-bold text-purple-400 uppercase tracking-widest font-mono">
                Cited Document Information
              </span>
              
              <h3 className="text-xl font-bold text-white leading-snug">
                {selectedPaper.title || "Paper Title Loading..."}
              </h3>

              <div className="grid grid-cols-2 gap-4 text-xs border-y border-zinc-800/60 py-3 text-zinc-400">
                <div>
                  <span className="font-semibold block text-zinc-500 mb-0.5">Authors</span>
                  {selectedPaper.authors?.join(", ") || "Unknown Authors"}
                </div>
                <div>
                  <span className="font-semibold block text-zinc-500 mb-0.5">Journal & Year</span>
                  {selectedPaper.journal ? `${selectedPaper.journal}, ` : ""}{selectedPaper.year}
                </div>
              </div>

              {/* Claims extracted from this paper */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                  Extracted Findings from this Paper
                </span>
                
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {claims.filter(c => c.paper_id === selectedPaper.pmid).length > 0 ? (
                    claims.filter(c => c.paper_id === selectedPaper.pmid).map((c, i) => (
                      <div key={i} className="p-3 bg-zinc-950 border border-zinc-900 rounded-xl space-y-1.5">
                        <div className="text-xs text-zinc-300 font-medium">"{c.text}"</div>
                        <div className="flex justify-between items-center text-[10px] text-zinc-500 font-mono">
                          <span className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 font-semibold uppercase">
                            {c.claim_type}
                          </span>
                          <span className="flex items-center gap-1">
                            Confidence: 
                            <span className={c.confidence_score >= 0.85 ? "text-emerald-400" : "text-amber-400"}>
                              {(c.confidence_score * 100).toFixed(0)}%
                            </span>
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 bg-zinc-950 border border-zinc-900 rounded-xl text-center text-zinc-500 text-xs italic">
                      No claims currently cached in local session.
                    </div>
                  )}
                </div>
              </div>

              {/* Action Link */}
              <div className="flex justify-end pt-3 border-t border-zinc-800/60 gap-3">
                <a
                  href={`https://pubmed.ncbi.nlm.nih.gov/${selectedPaper.pmid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2.5 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
                >
                  View on PubMed
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
                
                <button
                  onClick={() => setSelectedPaper(null)}
                  className="px-4 py-2.5 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-lg transition-colors cursor-pointer"
                >
                  Close Reference
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
