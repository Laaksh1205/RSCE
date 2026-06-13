"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startAnalysis } from "../utils/api";

export default function Home() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [maxPapers, setMaxPapers] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await startAnalysis(query.trim(), maxPapers);
      router.push(`/results/${response.run_id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to initiate analysis. Please check that the backend is running.");
      setLoading(false);
    }
  };

  const handleDemoClick = (topicId: string) => {
    router.push(`/results/${topicId}`);
  };

  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-100 font-sans selection:bg-purple-500/30 selection:text-purple-200 overflow-x-hidden">
      {/* Background Decorative Gradients */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-[600px] pointer-events-none overflow-hidden opacity-50 z-0">
        <div className="absolute top-[-10%] left-[20%] w-[60%] h-[80%] rounded-full bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-transparent blur-[120px]" />
        <div className="absolute top-[-5%] right-[10%] w-[40%] h-[60%] rounded-full bg-gradient-to-br from-cyan-500/10 via-purple-500/10 to-transparent blur-[100px]" />
      </div>

      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f2e08_1px,transparent_1px),linear-gradient(to_bottom,#1f1f2e08_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none z-0 opacity-40" />

      {/* Main Container */}
      <div className="relative max-w-6xl mx-auto px-6 py-12 md:py-20 flex flex-col items-center z-10">
        
        {/* Navigation / Header */}
        <header className="w-full flex items-center justify-between mb-16 md:mb-24">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 shadow-lg shadow-indigo-500/20">
              {/* Logo icon (two overlapping connected nodes) */}
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94-3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
              </svg>
              <div className="absolute inset-0 rounded-xl bg-purple-400 opacity-0 hover:opacity-20 animate-ping pointer-events-none" />
            </div>
            <div>
              <span className="font-semibold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-zinc-50 to-zinc-300">RSCE</span>
              <span className="text-zinc-500 text-xs block -mt-1 font-mono">v1.0.0</span>
            </div>
          </div>
          
          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-zinc-400">
            <a href="#about" className="hover:text-zinc-100 transition-colors">How it works</a>
            <a href="#benchmarks" className="hover:text-zinc-100 transition-colors">Benchmarks</a>
            <span className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-500 text-xs font-mono">API Active</span>
          </nav>
        </header>

        {/* Hero Headline Section */}
        <section className="text-center max-w-3xl mb-12 flex flex-col items-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-medium font-mono mb-6 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
            AI-Powered Meta-Research Engine
          </div>
          
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-white mb-6 leading-[1.15]">
            Synthesize Scientific Consensus.<br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-purple-400 via-indigo-300 to-cyan-300">
              Detect Contradictions.
            </span>
          </h1>
          
          <p className="text-zinc-400 text-base md:text-lg leading-relaxed max-w-2xl">
            RSCE crawls PubMed Central, extracts verified scientific claims with quote-level grounding,
            and maps conflicting clinical findings into an interactive evidence graph.
          </p>
        </section>

        {/* Search Panel Card */}
        <section className="w-full max-w-3xl mb-16 relative">
          <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-indigo-500/10 rounded-2xl blur-xl opacity-30 pointer-events-none" />
          
          <div className="relative bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 md:p-8 shadow-2xl">
            <form onSubmit={handleSubmit} className="flex flex-col gap-6">
              
              {/* Search Bar Input Container */}
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <svg className="h-5 w-5 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                
                <input
                  type="text"
                  id="query-input"
                  className="block w-full pl-11 pr-24 py-4 bg-zinc-950 border border-zinc-800 rounded-xl text-zinc-100 placeholder-zinc-500 text-base focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all shadow-inner font-medium"
                  placeholder="Enter your clinical or biological query..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={loading}
                />
                
                {/* Search Action Button */}
                <div className="absolute inset-y-2 right-2 flex items-center">
                  <button
                    type="submit"
                    id="submit-analysis"
                    disabled={loading || !query.trim()}
                    className="h-full px-5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg text-sm font-semibold transition-all shadow-lg hover:shadow-purple-500/20 active:scale-98 disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2"
                  >
                    {loading ? (
                      <>
                        <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        <span>Analyzing</span>
                      </>
                    ) : (
                      <>
                        <span>Analyze</span>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Extra Parameters */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 px-1 py-1 border-t border-zinc-800/60 pt-5">
                <div className="flex flex-col gap-1 w-full sm:w-auto">
                  <label htmlFor="max-papers-slider" className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                    Scope: Max PubMed Papers
                  </label>
                  <span className="text-zinc-500 text-xs">
                    More papers lead to richer claim graphs but longer fetch cycles.
                  </span>
                </div>
                
                <div className="flex items-center gap-4 w-full sm:w-auto justify-between sm:justify-start">
                  <input
                    type="range"
                    id="max-papers-slider"
                    min="5"
                    max="50"
                    step="5"
                    className="w-32 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-purple-500"
                    value={maxPapers}
                    onChange={(e) => setMaxPapers(parseInt(e.target.value))}
                    disabled={loading}
                  />
                  <span className="px-3 py-1 bg-zinc-950 border border-zinc-800 rounded-md font-mono text-sm text-purple-400 font-bold min-w-[3.5rem] text-center">
                    {maxPapers}
                  </span>
                </div>
              </div>

              {/* Error Display */}
              {error && (
                <div className="p-4 bg-red-950/30 border border-red-500/20 text-red-300 rounded-xl text-sm flex gap-3 items-start animate-shake">
                  <svg className="w-5 h-5 text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <span className="font-semibold block mb-0.5">Pipeline Request Failed</span>
                    {error}
                  </div>
                </div>
              )}

            </form>
          </div>
        </section>

        {/* Demo Topics Panel */}
        <section className="w-full max-w-4xl mb-24">
          <div className="text-center mb-8">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-widest mb-2">
              Pre-loaded Datasets
            </h2>
            <p className="text-zinc-500 text-xs sm:text-sm">
              Instantly explore fully processed claims, graphs, and reports without consuming Gemini API tokens.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* Metformin Demo */}
            <button
              id="demo-metformin-btn"
              onClick={() => handleDemoClick("demo_metformin")}
              className="group text-left bg-zinc-900/30 hover:bg-zinc-900/60 border border-zinc-800 hover:border-purple-500/30 rounded-xl p-5 transition-all duration-300 active:scale-98 relative hover:shadow-lg hover:shadow-purple-500/5 cursor-pointer"
            >
              <div className="absolute top-4 right-4 w-7 h-7 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 font-mono text-[10px] font-bold">
                15P
              </div>
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 mb-4 group-hover:scale-110 transition-transform">
                {/* Pill SVG */}
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                </svg>
              </div>
              <h3 className="font-semibold text-zinc-100 group-hover:text-purple-400 transition-colors mb-2">
                Metformin & Cancer
              </h3>
              <p className="text-zinc-400 text-xs leading-relaxed mb-4">
                "Does metformin reduce cancer risk?"
              </p>
              <div className="flex flex-wrap gap-1.5 mt-auto">
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">RCTs Included</span>
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">4 Contradictions</span>
              </div>
            </button>

            {/* Intermittent Fasting Demo */}
            <button
              id="demo-fasting-btn"
              onClick={() => handleDemoClick("demo_fasting")}
              className="group text-left bg-zinc-900/30 hover:bg-zinc-900/60 border border-zinc-800 hover:border-indigo-500/30 rounded-xl p-5 transition-all duration-300 active:scale-98 relative hover:shadow-lg hover:shadow-indigo-500/5 cursor-pointer"
            >
              <div className="absolute top-4 right-4 w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-mono text-[10px] font-bold">
                12P
              </div>
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-4 group-hover:scale-110 transition-transform">
                {/* Clock / Circadian SVG */}
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="font-semibold text-zinc-100 group-hover:text-indigo-400 transition-colors mb-2">
                Intermittent Fasting
              </h3>
              <p className="text-zinc-400 text-xs leading-relaxed mb-4">
                "Does fasting improve insulin sensitivity?"
              </p>
              <div className="flex flex-wrap gap-1.5 mt-auto">
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">Clinical Trials</span>
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">3 Contradictions</span>
              </div>
            </button>

            {/* SSRIs in Adolescents Demo */}
            <button
              id="demo-ssri-btn"
              onClick={() => handleDemoClick("demo_ssri")}
              className="group text-left bg-zinc-900/30 hover:bg-zinc-900/60 border border-zinc-800 hover:border-cyan-500/30 rounded-xl p-5 transition-all duration-300 active:scale-98 relative hover:shadow-lg hover:shadow-cyan-500/5 cursor-pointer"
            >
              <div className="absolute top-4 right-4 w-7 h-7 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 font-mono text-[10px] font-bold">
                10P
              </div>
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 mb-4 group-hover:scale-110 transition-transform">
                {/* Brain SVG */}
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364.364l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <h3 className="font-semibold text-zinc-100 group-hover:text-cyan-400 transition-colors mb-2">
                SSRIs & Suicidality
              </h3>
              <p className="text-zinc-400 text-xs leading-relaxed mb-4">
                "Do SSRIs increase suicide risk in adolescents?"
              </p>
              <div className="flex flex-wrap gap-1.5 mt-auto">
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">Meta-Analyses</span>
                <span className="px-2 py-0.5 bg-zinc-950 border border-zinc-800 text-zinc-500 text-[10px] rounded font-mono">2 Contradictions</span>
              </div>
            </button>

          </div>
        </section>

        {/* Explainer Section */}
        <section id="about" className="w-full max-w-4xl border-t border-zinc-900 pt-16 mb-24">
          <div className="text-center max-w-xl mx-auto mb-16">
            <h2 className="text-2xl font-bold tracking-tight text-white mb-4">
              Behind the Pipeline
            </h2>
            <p className="text-zinc-400 text-sm">
              RSCE operates a multi-stage validation system designed to bypass superficial semantic matches and extract actual logical contradiction.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Phase 1 & 2 */}
            <div className="space-y-8">
              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 font-mono text-sm text-zinc-300 font-bold">
                  01
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-100 mb-2">Ingestion & Fuzzy Verification</h3>
                  <p className="text-zinc-400 text-sm leading-relaxed">
                    Crawls PubMed abstracts or PMC full-text XML. LLM extracts claims which are checked via fuzzy quote-anchor matching against the source text to prevent hallucinations.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 font-mono text-sm text-zinc-300 font-bold">
                  02
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-100 mb-2">Vector Search & NLI Cross-Encoder</h3>
                  <p className="text-zinc-400 text-sm leading-relaxed">
                    Claims are embedded via Sentence Transformers and indexed in FAISS. High-similarity pairs are evaluated with a DeBERTa NLI cross-encoder model to identify conflicting assertions.
                  </p>
                </div>
              </div>
            </div>

            {/* Phase 3 & 4 */}
            <div className="space-y-8">
              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 font-mono text-sm text-zinc-300 font-bold">
                  03
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-100 mb-2">LLM Genuineness Judge</h3>
                  <p className="text-zinc-400 text-sm leading-relaxed">
                    Pairs flagged by the NLI model are evaluated by Gemini-2.5-Pro to filter out false positives caused by differing experimental scopes (e.g. human trials vs. in-vitro animal studies).
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 font-mono text-sm text-zinc-300 font-bold">
                  04
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-100 mb-2">Graph Synthesis & Citation RAG</h3>
                  <p className="text-zinc-400 text-sm leading-relaxed">
                    Entities are normalized to MeSH IDs. A NetworkX claim-evidence graph is built. A final summary report is drafted by the LLM, referencing citations that are validated back to original papers.
                  </p>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* Stats / Benchmark Section */}
        <section id="benchmarks" className="w-full max-w-4xl border-t border-zinc-900 pt-16 mb-16">
          <div className="bg-gradient-to-r from-zinc-900/40 to-zinc-900/10 border border-zinc-900 rounded-2xl p-6 md:p-8 flex flex-col md:flex-row items-center justify-around gap-8 text-center md:text-left">
            <div>
              <div className="text-3xl md:text-4xl font-extrabold text-white font-mono bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-indigo-400">
                70%+
              </div>
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mt-1">
                SciFact Precision
              </div>
              <div className="text-zinc-500 text-xs mt-1 max-w-[12rem] mx-auto md:mx-0">
                Validated on scientific claim-evidence benchmark
              </div>
            </div>

            <div className="h-px md:h-12 w-12 md:w-px bg-zinc-800" />

            <div>
              <div className="text-3xl md:text-4xl font-extrabold text-white font-mono bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-400">
                100%
              </div>
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mt-1">
                Citation Grounding
              </div>
              <div className="text-zinc-500 text-xs mt-1 max-w-[12rem] mx-auto md:mx-0">
                Zero hallucinated references in narrative reports
              </div>
            </div>

            <div className="h-px md:h-12 w-12 md:w-px bg-zinc-800" />

            <div>
              <div className="text-3xl md:text-4xl font-extrabold text-white font-mono bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-purple-400">
                &lt; 2 min
              </div>
              <div className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mt-1">
                Processing Latency
              </div>
              <div className="text-zinc-500 text-xs mt-1 max-w-[12rem] mx-auto md:mx-0">
                For a full 25-paper live ingestion pipeline run
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
