import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Database,
  Code,
  Zap,
  CheckCircle2,
  Clock,
  ArrowLeft,
  BookOpen,
  Layers,
  Sparkles,
  ChevronRight,
  Terminal,
  Activity,
  AlertCircle,
  Copy,
  Check,
  ShieldCheck,
  Network,
} from "lucide-react";
import logo from "../assets/logo1.svg";

const SAMPLE_QUERIES = [
  { label: "Punishment for Murder", query: "What is the punishment for murder?" },
  { label: "IPC 302 → BNS Conversion", query: "What is the BNS equivalent of IPC Section 302?" },
  { label: "Compare Murder vs Culpable Homicide", query: "Compare murder and culpable homicide under Indian law." },
  { label: "Section 376 Details", query: "What does IPC Section 376 cover?" },
  { label: "Dowry Death Explanation", query: "Explain the legal provisions related to dowry death." },
  { label: "Kidnapping & Ransom", query: "A child was kidnapped for ransom and murdered. What sections apply?" },
];

export default function LexiGraphCypherPage({ onBack }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("answer"); // "answer" | "cypher" | "records" | "timings"
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);

  const handleSearch = async (e, customQuery) => {
    if (e) e.preventDefault();
    const q = customQuery || query;
    if (!q || !q.strip ? !q.trim() : false) return;

    setLoading(true);
    setError(null);
    setResult(null);

    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

    try {
      const response = await fetch(`${apiUrl}/api/cypher/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || "Failed to execute Cypher query pipeline.");
      }

      setResult(data.data);
    } catch (err) {
      console.error("Cypher query error:", err);
      setError(err.message || "Unable to reach LexiGraph Cypher backend service.");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#2C1810] font-body selection:bg-gold/30">
      {/* Top Header Nav */}
      <header className="sticky top-0 z-40 bg-[#FAF9F7]/90 backdrop-blur-md border-b border-[#D4AF37]/30 px-6 py-4 shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack || (() => { navigate("/"); })}
              className="p-2 rounded-full hover:bg-[#2C1810]/5 text-[#2C1810] transition-colors"
              title="Return to Home"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-3">
              <img src={logo} alt="Kayda Logo" className="w-14 h-auto" />
              <div>
                <span className="font-heading text-xl font-bold tracking-tight text-[#2C1810]">
                  LexiGraph Cypher Engine
                </span>
                <span className="ml-3 px-2.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 rounded-full">
                  Text-to-Cypher AI
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => { navigate("/lexigraph-agent"); }}
              className="px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-white border border-[#2C1810]/20 rounded-lg hover:border-[#D4AF37] hover:bg-[#D4AF37]/10 transition-all flex items-center gap-2 cursor-pointer"
            >
              <Network className="w-3.5 h-3.5 text-[#8C5A3C]" />
              Switch to Legal Agent
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Banner Section */}
        <div className="mb-8 p-8 rounded-3xl bg-gradient-to-br from-[#2C1810] via-[#3D2217] to-[#1A0E0A] text-[#FAF9F7] shadow-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-[#D4AF37]/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 max-w-3xl">
            <div className="flex items-center gap-2 text-[#D4AF37] text-xs font-semibold uppercase tracking-widest mb-3">
              <Sparkles className="w-4 h-4" /> Indian Penal Code & Bharatiya Nyaya Sanhita Graph AI
            </div>
            <h1 className="font-heading text-3xl md:text-4xl font-bold mb-3 tracking-tight text-[#FAF9F7]">
              Ask Legal Questions in Natural Language
            </h1>
            <p className="text-[#FAF9F7]/80 text-sm md:text-base leading-relaxed mb-6">
              Our multi-stage pipeline translates natural language questions into deterministic Neo4j Cypher queries,
              queries the legal graph database, and returns verified legal answers with precise IPC/BNS mappings.
            </p>

            {/* Query Input Bar */}
            <form onSubmit={(e) => handleSearch(e)} className="relative flex items-center">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#2C1810]/40" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. What is the punishment for murder under IPC Section 302?"
                  className="w-full pl-12 pr-4 py-4 rounded-2xl bg-white text-[#2C1810] placeholder-[#2C1810]/40 border border-[#D4AF37]/40 focus:outline-none focus:ring-2 focus:ring-[#D4AF37] text-sm shadow-inner"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="ml-3 px-6 py-4 rounded-2xl bg-[#D4AF37] text-[#2C1810] font-semibold text-sm hover:bg-[#c49f27] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md shrink-0"
              >
                {loading ? (
                  <>
                    <Zap className="w-4 h-4 animate-spin" /> Querying...
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" /> Run Text2Cypher
                  </>
                )}
              </button>
            </form>

            {/* Quick Sample Queries */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-xs text-[#FAF9F7]/60 font-medium">Try:</span>
              {SAMPLE_QUERIES.map((sq, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setQuery(sq.query);
                    handleSearch(null, sq.query);
                  }}
                  className="px-3 py-1 text-xs rounded-full bg-white/10 hover:bg-white/20 text-[#FAF9F7]/90 border border-white/10 transition-all text-left"
                >
                  {sq.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="mb-8 p-4 rounded-2xl bg-red-50 border border-red-200 text-red-800 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
            <div>
              <h4 className="font-semibold text-sm">Execution Error</h4>
              <p className="text-xs text-red-700 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Loading Spinner Skeleton */}
        {loading && (
          <div className="p-12 rounded-3xl bg-white border border-[#D4AF37]/20 shadow-md text-center">
            <div className="inline-flex p-4 rounded-full bg-[#D4AF37]/10 text-[#8C5A3C] mb-4 animate-bounce">
              <Database className="w-8 h-8" />
            </div>
            <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-1">
              Executing Multi-Stage Text-to-Cypher Pipeline...
            </h3>
            <p className="text-xs text-[#2C1810]/60 max-w-md mx-auto mb-6">
              Intent Classification → Entity Linking → Cypher Generation → Neo4j Graph Query → Legal Synthesis
            </p>
            <div className="w-48 h-1.5 bg-[#2C1810]/10 rounded-full mx-auto overflow-hidden">
              <div className="w-full h-full bg-[#D4AF37] animate-pulse" />
            </div>
          </div>
        )}

        {/* Results Area */}
        {result && !loading && (
          <div className="space-y-8">
            {/* Pipeline Stage Indicators */}
            <div className="p-6 rounded-3xl bg-white border border-[#D4AF37]/30 shadow-md">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-heading text-base font-bold text-[#2C1810] flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#D4AF37]" /> Pipeline Stage Results
                </h3>
                <span className="text-xs text-[#8C5A3C] font-semibold bg-[#FAF9F7] px-3 py-1 rounded-full border border-[#D4AF37]/30 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Total Time: {result.total_time_ms} ms
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">1. Intent</div>
                  <div className="text-xs font-semibold text-[#2C1810] truncate capitalize">
                    {result.intent ? result.intent.replace(/_/g, " ") : "Unknown"}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">2. Entities</div>
                  <div className="text-xs font-semibold text-[#2C1810] truncate">
                    {result.extracted_entities?.crimes?.length || result.extracted_entities?.ipc_sections?.length
                      ? `${result.extracted_entities?.crimes?.length || 0} crimes, ${result.extracted_entities?.ipc_sections?.length || 0} IPC`
                      : "Extracted"}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">3. Linked Nodes</div>
                  <div className="text-xs font-semibold text-[#2C1810] truncate">
                    {(result.linked_entities?.section_nodes?.length || 0) + (result.linked_entities?.crime_nodes?.length || 0)} Graph Nodes
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">4. Cypher Built</div>
                  <div className="text-xs font-semibold text-[#2C1810] truncate">
                    {result.cypher_queries?.length || 0} Validated
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">5. Neo4j Records</div>
                  <div className="text-xs font-semibold text-[#2C1810] truncate">
                    {result.execution_results?.reduce((acc, curr) => acc + (curr.records?.length || 0), 0) || 0} Records
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                  <div className="text-[10px] uppercase font-bold text-[#8C5A3C] mb-1">6. Synthesis</div>
                  <div className="text-xs font-semibold text-emerald-700 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Complete
                  </div>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex border-b border-[#2C1810]/10 gap-4">
              <button
                onClick={() => setActiveTab("answer")}
                className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
                  activeTab === "answer"
                    ? "border-[#D4AF37] text-[#2C1810]"
                    : "border-transparent text-[#2C1810]/50 hover:text-[#2C1810]"
                }`}
              >
                <BookOpen className="w-4 h-4" /> Synthesized Answer
              </button>
              <button
                onClick={() => setActiveTab("cypher")}
                className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
                  activeTab === "cypher"
                    ? "border-[#D4AF37] text-[#2C1810]"
                    : "border-transparent text-[#2C1810]/50 hover:text-[#2C1810]"
                }`}
              >
                <Code className="w-4 h-4" /> Generated Cypher ({result.cypher_queries?.length || 0})
              </button>
              <button
                onClick={() => setActiveTab("records")}
                className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
                  activeTab === "records"
                    ? "border-[#D4AF37] text-[#2C1810]"
                    : "border-transparent text-[#2C1810]/50 hover:text-[#2C1810]"
                }`}
              >
                <Database className="w-4 h-4" /> Neo4j Graph Data
              </button>
              <button
                onClick={() => setActiveTab("timings")}
                className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-all ${
                  activeTab === "timings"
                    ? "border-[#D4AF37] text-[#2C1810]"
                    : "border-transparent text-[#2C1810]/50 hover:text-[#2C1810]"
                }`}
              >
                <Clock className="w-4 h-4" /> Stage Timings
              </button>
            </div>

            {/* TAB 1: SYNTHESIZED ANSWER */}
            {activeTab === "answer" && (
              <div className="p-8 rounded-3xl bg-white border border-[#D4AF37]/30 shadow-md">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-[#2C1810]/10">
                  <div className="flex items-center gap-2 text-[#8C5A3C] font-semibold text-sm">
                    <ShieldCheck className="w-5 h-5 text-[#D4AF37]" /> Verified Legal Synthesis
                  </div>
                  <span className="text-xs px-3 py-1 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#2C1810]">
                    Intent: <strong className="capitalize">{result.intent?.replace(/_/g, " ")}</strong>
                  </span>
                </div>

                <div className="prose max-w-none text-[#2C1810] leading-relaxed text-sm md:text-base whitespace-pre-wrap">
                  {result.answer || "No synthesis returned."}
                </div>

                {/* Extracted Entities Chips */}
                {result.extracted_entities && (
                  <div className="mt-8 pt-6 border-t border-[#2C1810]/10">
                    <h4 className="text-xs uppercase font-bold text-[#8C5A3C] tracking-wider mb-3">
                      Extracted Legal Concepts & Sections
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {result.extracted_entities.ipc_sections?.map((sec, i) => (
                        <span key={i} className="px-3 py-1 text-xs rounded-lg bg-amber-50 text-amber-900 border border-amber-200 font-mono">
                          IPC {sec}
                        </span>
                      ))}
                      {result.extracted_entities.bns_sections?.map((sec, i) => (
                        <span key={i} className="px-3 py-1 text-xs rounded-lg bg-blue-50 text-blue-900 border border-blue-200 font-mono">
                          BNS {sec}
                        </span>
                      ))}
                      {result.extracted_entities.crimes?.map((crime, i) => (
                        <span key={i} className="px-3 py-1 text-xs rounded-lg bg-stone-100 text-stone-800 border border-stone-300 capitalize">
                          {crime}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: CYPHER QUERIES */}
            {activeTab === "cypher" && (
              <div className="space-y-6">
                {result.cypher_queries && result.cypher_queries.length > 0 ? (
                  result.cypher_queries.map((cq, idx) => (
                    <div key={idx} className="rounded-3xl bg-[#1E1E1E] text-[#D4D4D4] border border-stone-800 overflow-hidden shadow-xl">
                      <div className="px-6 py-4 bg-[#252526] border-b border-stone-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Terminal className="w-4 h-4 text-[#D4AF37]" />
                          <span className="text-xs font-semibold text-[#D4AF37]">
                            Cypher Query #{idx + 1} &mdash; {cq.description || "Generated Query"}
                          </span>
                        </div>
                        <button
                          onClick={() => copyToClipboard(cq.cypher, idx)}
                          className="px-3 py-1 text-xs rounded bg-white/10 hover:bg-white/20 text-[#D4D4D4] transition-colors flex items-center gap-1"
                        >
                          {copiedIndex === idx ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                          {copiedIndex === idx ? "Copied" : "Copy"}
                        </button>
                      </div>
                      <div className="p-6 overflow-x-auto font-mono text-xs text-[#9CDCFE] leading-relaxed">
                        <pre>{cq.cypher}</pre>
                      </div>
                      {cq.parameters && Object.keys(cq.parameters).length > 0 && (
                        <div className="px-6 py-3 bg-[#181818] border-t border-stone-800 text-xs font-mono text-stone-400">
                          <strong className="text-stone-300">Parameters: </strong>
                          {JSON.stringify(cq.parameters)}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-3xl border border-[#2C1810]/10 text-stone-500">
                    No Cypher queries generated for this request.
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: NEO4J GRAPH RECORDS */}
            {activeTab === "records" && (
              <div className="space-y-6">
                {result.execution_results && result.execution_results.length > 0 ? (
                  result.execution_results.map((res, idx) => (
                    <div key={idx} className="p-6 rounded-3xl bg-white border border-[#D4AF37]/30 shadow-md">
                      <div className="flex items-center justify-between mb-4 pb-2 border-b border-[#2C1810]/10">
                        <h4 className="text-sm font-bold text-[#2C1810] flex items-center gap-2">
                          <Database className="w-4 h-4 text-[#8C5A3C]" /> Query Execution Result #{idx + 1}
                        </h4>
                        <span className="text-xs text-stone-500 font-mono">
                          {res.records?.length || 0} records returned ({res.execution_time_ms} ms)
                        </span>
                      </div>

                      {res.records && res.records.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-[#2C1810]/20 text-[#8C5A3C] uppercase text-[10px]">
                                {Object.keys(res.records[0] || {}).map((col, i) => (
                                  <th key={i} className="py-2 px-3 font-bold">{col}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {res.records.map((rec, rIdx) => (
                                <tr key={rIdx} className="border-b border-stone-100 hover:bg-stone-50">
                                  {Object.values(rec).map((val, cIdx) => (
                                    <td key={cIdx} className="py-2.5 px-3 font-mono text-stone-800 max-w-xs truncate">
                                      {typeof val === "object" ? JSON.stringify(val) : String(val)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="text-xs text-stone-500 italic">No records returned from Neo4j.</div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="p-8 text-center bg-white rounded-3xl border border-[#2C1810]/10 text-stone-500">
                    No graph records available.
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: STAGE TIMINGS */}
            {activeTab === "timings" && (
              <div className="p-8 rounded-3xl bg-white border border-[#D4AF37]/30 shadow-md">
                <h4 className="text-sm font-bold text-[#2C1810] mb-4 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-[#D4AF37]" /> Stage Execution Timings (ms)
                </h4>
                <div className="space-y-3 max-w-xl">
                  {result.stages_log && Object.entries(result.stages_log).map(([stage, ms], idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs py-2 px-4 rounded-xl bg-[#FAF8F5] border border-[#2C1810]/10">
                      <span className="font-semibold text-[#2C1810] capitalize">{stage.replace(/_/g, " ")}</span>
                      <span className="font-mono text-[#8C5A3C] font-bold">{ms} ms</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
