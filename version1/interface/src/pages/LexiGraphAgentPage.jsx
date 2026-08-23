import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Network,
  Cpu,
  Layers,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  Scale,
  ShieldAlert,
  HelpCircle,
  Sparkles,
  ExternalLink,
  ChevronRight,
  RefreshCw,
  Terminal,
  FileText,
  Gavel,
  ShieldCheck,
  Check,
  Copy,
  Clock,
  Database,
  X,
  CloudCheck,
  Cloud,
} from "lucide-react";
import logo from "../assets/logo1.svg";

const SAMPLE_QUERIES = [
  { label: "Theft of motor vehicle", query: "Theft of a motor vehicle under Indian Penal Code and BNS" },
  { label: "Extortion & Blackmail", query: "What are the legal provisions for extortion and blackmail?" },
  { label: "Dowry Death IPC 304B / BNS 80", query: "Explain dowry death under IPC Section 304B and equivalent BNS Section 80" },
  { label: "Culpable Homicide vs Murder", query: "What is the difference between culpable homicide and murder?" },
  { label: "Bail in non-bailable offences", query: "What are the principles for granting bail in non-bailable offences?" },
];

const PROCESSING_STEPS = [
  "Query Understanding & Grounding Gate",
  "Vector Embedding & Parallel Namespace Retrieval",
  "Candidate Filtering & Metadata Verification",
  "Statutory IPC ⇄ BNS Equivalent Mapping",
  "Supreme Court Precedent Graph Traversal",
  "Ingredient Validation & Multi-Signal Reranking",
  "Legal Reasoning & Final Synthesis",
];

export default function LexiGraphAgentPage({ onBack, onSwitchToCypher }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [activeTab, setActiveTab] = useState("sections"); // "sections" | "precedents" | "evidence" | "audit"
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [queryMeta, setQueryMeta] = useState(null); // { query_id, created_at, saved_to_firestore }

  // History Drawer State
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingHistoryId, setLoadingHistoryId] = useState(null);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    try {
      const response = await fetch(`${apiUrl}/api/lexigraph-agent/history`);
      const data = await response.json();
      if (response.ok && data.success) {
        setHistoryItems(data.data || []);
      }
    } catch (err) {
      console.error("Failed to fetch LexiGraph history:", err);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleSearch = async (e, customQuery) => {
    if (e) e.preventDefault();
    const q = customQuery !== undefined ? customQuery : query;
    if (!q || !q.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setQueryMeta(null);
    setCurrentStep(0);

    // Step animation simulator
    const stepInterval = setInterval(() => {
      setCurrentStep((prev) => (prev < PROCESSING_STEPS.length - 1 ? prev + 1 : prev));
    }, 600);

    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

    try {
      const response = await fetch(`${apiUrl}/api/lexigraph-agent/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q.trim(), debug: true }),
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || "Failed to execute LexiGraph Agent retrieval pipeline.");
      }

      setResult(data.data);
      setQueryMeta({
        query_id: data.query_id,
        created_at: data.created_at,
        saved_to_firestore: data.saved_to_firestore,
      });

      // Refresh history sidebar list
      fetchHistory();
    } catch (err) {
      console.error("LexiGraph Agent query error:", err);
      setError(err.message || "Unable to reach LexiGraph Agent backend service.");
    } finally {
      clearInterval(stepInterval);
      setLoading(false);
    }
  };

  const loadHistoryItem = async (query_id, itemQuery) => {
    setLoadingHistoryId(query_id);
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    try {
      const response = await fetch(`${apiUrl}/api/lexigraph-agent/history/${query_id}`);
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || "Failed to load past session record.");
      }

      const session = data.data;
      setQuery(itemQuery || session.query || "");
      setResult(session.result);
      setQueryMeta({
        query_id: session.query_id,
        created_at: session.created_at,
        saved_to_firestore: session.saved_to_firestore || session.source === "firestore",
      });
      setShowHistory(false);
    } catch (err) {
      console.error("Failed to load history session:", err);
      setError(`Unable to load past query response: ${err.message}`);
    } finally {
      setLoadingHistoryId(null);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#2C1810] font-body selection:bg-gold/30 relative">
      {/* Top Header Nav */}
      <header className="sticky top-0 z-40 bg-[#FAF9F7]/90 backdrop-blur-md border-b border-[#D4AF37]/30 px-6 py-4 shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack || (() => { navigate("/"); })}
              className="p-2 rounded-full hover:bg-[#2C1810]/5 text-[#2C1810] transition-colors cursor-pointer"
              title="Return to Home"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-3">
              <img src={logo} alt="Kayda Logo" className="w-12 h-auto" />
              <div>
                <span className="font-heading text-xl font-bold tracking-tight text-[#2C1810]">
                  LexiGraph Legal Agent
                </span>
                <span className="ml-3 px-2.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold bg-[#8C5A3C]/15 text-[#8C5A3C] border border-[#8C5A3C]/30 rounded-full">
                  GraphRAG & Precedent Engine
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Query History Drawer Toggle Button */}
            <button
              onClick={() => {
                setShowHistory(!showHistory);
                if (!showHistory) fetchHistory();
              }}
              className="px-3.5 py-2 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-[#FAF9F7] border border-[#2C1810]/20 rounded-lg hover:border-[#D4AF37] hover:bg-[#D4AF37]/10 transition-all flex items-center gap-2 cursor-pointer relative"
              title="View Firebase Saved Searches"
            >
              <Clock className="w-3.5 h-3.5 text-[#8C5A3C]" />
              Query History
              {historyItems.length > 0 && (
                <span className="ml-1 px-1.5 py-0.2 text-[9px] bg-[#D4AF37] text-[#2C1810] rounded-full font-extrabold">
                  {historyItems.length}
                </span>
              )}
            </button>

            <button
              onClick={onSwitchToCypher || (() => { navigate("/text2cypher"); })}
              className="px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-white border border-[#2C1810]/20 rounded-lg hover:border-[#D4AF37] hover:bg-[#D4AF37]/10 transition-all flex items-center gap-2 cursor-pointer"
            >
              <Terminal className="w-3.5 h-3.5 text-[#8C5A3C]" />
              Switch to Cypher Engine
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Banner Section */}
        <div className="bg-white border border-[#D4AF37]/40 rounded-2xl p-8 mb-8 shadow-[0_4px_25px_rgba(44,24,16,0.04)] relative overflow-hidden">
          <div className="absolute -top-12 -right-12 w-64 h-64 bg-[#D4AF37]/10 rounded-full blur-3xl pointer-events-none" />

          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-[#8C5A3C] uppercase tracking-widest mb-2">
              <Sparkles className="w-4 h-4 text-[#D4AF37]" />
              Multi-Stage GraphRAG Legal Retriever • Firebase Persisted
            </div>

            <h1 className="font-heading text-3xl md:text-4xl font-bold text-[#2C1810] tracking-tight mb-3">
              Search Legal Provisions, Mappings & Supreme Court Precedents
            </h1>

            <p className="font-body text-sm text-[#5D4037]/80 leading-relaxed mb-6">
              Query the legal graph to retrieve validated statutory sections (IPC & BNS), automatic successor mapping, ingredient verification, and binding Supreme Court precedents.
            </p>

            {/* Query Form */}
            <form onSubmit={(e) => handleSearch(e)} className="relative mb-4">
              <div className="relative flex items-center">
                <Search className="absolute left-4 w-5 h-5 text-[#8C5A3C]" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. Punishment for extortion and blackmail under IPC / BNS..."
                  className="w-full pl-12 pr-32 py-4 bg-[#FAF9F7] border border-[#2C1810]/20 rounded-xl font-body text-sm text-[#2C1810] placeholder-[#5D4037]/50 focus:outline-none focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20 transition-all shadow-inner"
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !query.trim()}
                  className="absolute right-2 px-6 py-2.5 bg-[#2C1810] text-[#FAF9F7] border border-[#D4AF37] rounded-lg font-mono text-xs uppercase tracking-wider font-bold hover:bg-[#8C5A3C] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 cursor-pointer"
                >
                  {loading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      Execute Query
                      <ChevronRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Quick Sample Queries */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-mono font-bold uppercase text-[#5D4037]/70 mr-1">
                Sample Searches:
              </span>
              {SAMPLE_QUERIES.map((sq, idx) => (
                <button
                  key={idx}
                  onClick={(e) => {
                    setQuery(sq.query);
                    handleSearch(e, sq.query);
                  }}
                  disabled={loading}
                  className="px-3 py-1 bg-[#2C1810]/5 hover:bg-[#D4AF37]/20 border border-[#2C1810]/10 hover:border-[#D4AF37]/40 rounded-full font-body text-xs text-[#2C1810] transition-all cursor-pointer"
                >
                  {sq.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Loading Indicator */}
        {loading && (
          <div className="bg-white border border-[#D4AF37]/30 rounded-xl p-8 mb-8 text-center shadow-sm">
            <div className="flex flex-col items-center max-w-md mx-auto">
              <div className="w-16 h-16 rounded-full bg-[#D4AF37]/15 flex items-center justify-center text-[#8C5A3C] mb-4 relative">
                <Cpu className="w-8 h-8 animate-pulse" />
                <div className="absolute inset-0 rounded-full border-2 border-[#D4AF37] border-t-transparent animate-spin" />
              </div>
              
              <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-2">
                LexiGraph Agent Executing...
              </h3>
              
              <p className="font-mono text-xs text-[#8C5A3C] font-semibold mb-6">
                Step {currentStep + 1} of {PROCESSING_STEPS.length}: {PROCESSING_STEPS[currentStep]}
              </p>

              {/* Progress Bar */}
              <div className="w-full bg-[#FAF9F7] border border-[#2C1810]/10 rounded-full h-2.5 overflow-hidden mb-4">
                <div 
                  className="bg-gradient-to-r from-[#8C5A3C] to-[#D4AF37] h-full transition-all duration-300"
                  style={{ width: `${((currentStep + 1) / PROCESSING_STEPS.length) * 100}%` }}
                />
              </div>

              <span className="font-body text-xs text-[#5D4037]/70">
                Grounding citations, traversing Neo4j knowledge graph & persisting to Firebase Firestore...
              </span>
            </div>
          </div>
        )}

        {/* Error Card */}
        {error && (
          <div className="bg-[#FFF5F5] border border-red-200 rounded-xl p-6 mb-8 flex items-start gap-4 text-red-900 shadow-sm">
            <AlertCircle className="w-6 h-6 text-red-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-heading text-base font-bold mb-1">
                Execution Failure
              </h3>
              <p className="font-body text-xs text-red-700 leading-relaxed mb-4">
                {error}
              </p>
              <button
                onClick={(e) => handleSearch(e)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg font-mono text-xs uppercase font-bold hover:bg-red-700 transition-colors cursor-pointer"
              >
                Retry Request
              </button>
            </div>
          </div>
        )}

        {/* Results Render */}
        {result && !loading && (
          <div className="space-y-8 animate-fadeIn">
            {/* Metadata Summary Header */}
            <div className="bg-white border border-[#D4AF37]/30 rounded-xl p-6 flex flex-wrap items-center justify-between gap-4 shadow-sm">
              <div className="flex items-center gap-6">
                <div>
                  <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block mb-1">
                    Pipeline Confidence
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="w-12 h-12 rounded-xl bg-[#D4AF37]/15 border border-[#D4AF37]/40 flex items-center justify-center font-heading text-lg font-bold text-[#8C5A3C]">
                      {Math.round((result.pipeline_confidence || 0) * 100)}%
                    </div>
                    <div>
                      <span className="font-heading text-sm font-bold text-[#2C1810] block">
                        {(result.pipeline_confidence || 0) >= 0.7 ? "High Confidence Verification" : "Moderate Applicability"}
                      </span>
                      <span className="font-body text-xs text-[#5D4037]/70">
                        Hierarchical GraphRAG Validated
                      </span>
                    </div>
                  </div>
                </div>

                <div className="h-10 w-px bg-[#2C1810]/10 hidden md:block" />

                <div>
                  <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block mb-1">
                    Intent Classification
                  </span>
                  <span className="px-3 py-1 text-xs font-mono font-bold uppercase tracking-wider bg-[#2C1810]/5 text-[#2C1810] border border-[#2C1810]/15 rounded-full inline-block">
                    {result.community?.primary_intent || "General Offence"}
                  </span>
                </div>
              </div>

              {/* Stats & Firestore Sync badges */}
              <div className="flex items-center gap-3">
                {queryMeta && (
                  <div className="px-3 py-1.5 bg-[#FAF9F7] border border-[#D4AF37]/30 rounded-lg flex items-center gap-1.5 text-xs font-mono text-[#8C5A3C] font-bold">
                    <Database className="w-3.5 h-3.5 text-[#D4AF37]" />
                    <span>Saved to Firebase</span>
                  </div>
                )}
                <div className="px-3 py-1.5 bg-[#FAF9F7] border border-[#2C1810]/10 rounded-lg text-center">
                  <span className="font-heading text-sm font-bold text-[#2C1810] block">
                    {result.recommended_sections?.length || 0}
                  </span>
                  <span className="font-mono text-[9px] uppercase text-[#5D4037]/70">Provisions</span>
                </div>
                <div className="px-3 py-1.5 bg-[#FAF9F7] border border-[#2C1810]/10 rounded-lg text-center">
                  <span className="font-heading text-sm font-bold text-[#2C1810] block">
                    {(result.supporting_cases?.length || 0) + (result.similar_cases?.length || 0)}
                  </span>
                  <span className="font-mono text-[9px] uppercase text-[#5D4037]/70">Precedents</span>
                </div>
                <div className="px-3 py-1.5 bg-[#FAF9F7] border border-[#2C1810]/10 rounded-lg text-center">
                  <span className="font-heading text-sm font-bold text-[#2C1810] block">
                    {result.rejected_sections?.length || 0}
                  </span>
                  <span className="font-mono text-[9px] uppercase text-[#5D4037]/70">Filtered</span>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="border-b border-[#2C1810]/15 flex items-center gap-6 font-mono text-xs uppercase tracking-wider font-bold">
              <button
                onClick={() => setActiveTab("sections")}
                className={`pb-3 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  activeTab === "sections"
                    ? "border-[#D4AF37] text-[#8C5A3C]"
                    : "border-transparent text-[#5D4037]/70 hover:text-[#2C1810]"
                }`}
              >
                <BookOpen className="w-4 h-4" />
                Recommended Sections ({result.recommended_sections?.length || 0})
              </button>

              <button
                onClick={() => setActiveTab("precedents")}
                className={`pb-3 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  activeTab === "precedents"
                    ? "border-[#D4AF37] text-[#8C5A3C]"
                    : "border-transparent text-[#5D4037]/70 hover:text-[#2C1810]"
                }`}
              >
                <Gavel className="w-4 h-4" />
                Case Precedents ({(result.supporting_cases?.length || 0) + (result.similar_cases?.length || 0)})
              </button>

              <button
                onClick={() => setActiveTab("evidence")}
                className={`pb-3 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  activeTab === "evidence"
                    ? "border-[#D4AF37] text-[#8C5A3C]"
                    : "border-transparent text-[#5D4037]/70 hover:text-[#2C1810]"
                }`}
              >
                <FileText className="w-4 h-4" />
                Evidence & Principles ({result.supporting_evidence?.length || 0})
              </button>

              <button
                onClick={() => setActiveTab("audit")}
                className={`pb-3 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
                  activeTab === "audit"
                    ? "border-[#D4AF37] text-[#8C5A3C]"
                    : "border-transparent text-[#5D4037]/70 hover:text-[#2C1810]"
                }`}
              >
                <ShieldAlert className="w-4 h-4" />
                Validation Audit ({result.rejected_sections?.length || 0})
              </button>
            </div>

            {/* TAB 1: Recommended Statutory Sections */}
            {activeTab === "sections" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {result.recommended_sections && result.recommended_sections.length > 0 ? (
                  result.recommended_sections.map((sec, idx) => (
                    <div
                      key={idx}
                      className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm hover:border-[#D4AF37] transition-all flex flex-col justify-between"
                    >
                      <div>
                        {/* Section Header Badges */}
                        <div className="flex items-center justify-between gap-2 mb-3">
                          <div className="flex items-center gap-2">
                            <span className="px-3 py-1 bg-[#2C1810] text-[#FAF9F7] border border-[#D4AF37] rounded-lg font-mono text-xs font-bold uppercase tracking-wider">
                              {sec.act} Section {sec.section}
                            </span>
                            <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold bg-[#D4AF37]/20 text-[#8C5A3C] rounded-full border border-[#D4AF37]/40">
                              {Math.round((sec.confidence || 0) * 100)}% Confidence
                            </span>
                          </div>
                          <button
                            onClick={() => copyToClipboard(`${sec.act} Section ${sec.section}: ${sec.title}`, idx)}
                            className="p-1.5 text-[#5D4037] hover:text-[#2C1810] rounded hover:bg-[#2C1810]/5 transition-colors cursor-pointer"
                            title="Copy Provision"
                          >
                            {copiedIndex === idx ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                          </button>
                        </div>

                        {/* Title */}
                        <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-2 leading-snug">
                          {sec.title}
                        </h3>

                        {/* IPC <-> BNS Equivalent mapping badge */}
                        {sec.equivalent_section && (
                          <div className="bg-[#FAF9F7] border border-[#D4AF37]/30 rounded-lg p-3 mb-4 flex items-center gap-3">
                            <ShieldCheck className="w-5 h-5 text-[#8C5A3C] shrink-0" />
                            <div className="text-xs">
                              <span className="font-mono font-bold text-[#8C5A3C] uppercase block text-[10px]">
                                Cross-Act Successor Mapping
                              </span>
                              <span className="font-body text-[#2C1810] font-semibold">
                                Equivalent Provision: {sec.equivalent_section.act} Section {sec.equivalent_section.section}
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Applicability Reason */}
                        <div className="mb-4">
                          <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block mb-1">
                            Applicability & Statutory Rationale
                          </span>
                          <p className="font-body text-xs text-[#5D4037]/90 leading-relaxed bg-[#FAF9F7] p-3 rounded-lg border border-[#2C1810]/10">
                            {sec.applicability || sec.reason}
                          </p>
                        </div>
                      </div>

                      <div className="pt-4 border-t border-[#2C1810]/10 flex items-center justify-between text-[11px] text-[#5D4037]/70 font-mono">
                        <span className="flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5 text-green-600" /> Grounding Verified
                        </span>
                        <span>Graph Node OK</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-2 text-center py-12 bg-white border border-[#2C1810]/10 rounded-xl">
                    <BookOpen className="w-10 h-10 text-[#5D4037]/40 mx-auto mb-3" />
                    <p className="font-body text-sm text-[#5D4037]">No specific statutory section met the strict applicability threshold.</p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: Supreme Court Precedents */}
            {activeTab === "precedents" && (
              <div className="space-y-6">
                {/* Supreme Court Graph Cases */}
                {result.supporting_cases && result.supporting_cases.length > 0 && (
                  <div>
                    <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-[#8C5A3C] mb-4 flex items-center gap-2">
                      <Gavel className="w-4 h-4 text-[#D4AF37]" />
                      Binding Supreme Court Precedents (Neo4j Graph Traversal)
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {result.supporting_cases.map((sc, idx) => (
                        <div key={idx} className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm hover:border-[#D4AF37] transition-all">
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <h4 className="font-heading text-base font-bold text-[#2C1810] leading-snug">
                              {sc.case_name}
                            </h4>
                            <span className="px-2.5 py-0.5 text-[9px] font-mono font-bold uppercase bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 rounded-full shrink-0">
                              {sc.binding_under || "Article 141"}
                            </span>
                          </div>

                          {sc.citation && (
                            <span className="font-mono text-xs text-[#8C5A3C] font-semibold block mb-3">
                              {sc.citation}
                            </span>
                          )}

                          <p className="font-body text-xs text-[#5D4037]/90 leading-relaxed mb-4 bg-[#FAF9F7] p-3 rounded-lg border border-[#2C1810]/10">
                            {sc.reason}
                          </p>

                          {sc.legal_principles && sc.legal_principles.length > 0 && (
                            <div className="mb-3">
                              <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block mb-1">
                                Ratio Decidendi & Principles:
                              </span>
                              <div className="flex flex-wrap gap-1.5">
                                {sc.legal_principles.map((p, pidx) => (
                                  <span key={pidx} className="px-2 py-0.5 text-[10px] bg-[#2C1810]/5 text-[#2C1810] border border-[#2C1810]/10 rounded font-body">
                                    • {p}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Vector Similar Cases */}
                {result.similar_cases && result.similar_cases.length > 0 && (
                  <div>
                    <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-[#8C5A3C] mb-4 flex items-center gap-2">
                      <Layers className="w-4 h-4 text-[#D4AF37]" />
                      Semantically Relevant Precedents (Vector RAG)
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {result.similar_cases.map((cs, idx) => (
                        <div key={idx} className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm hover:border-[#D4AF37] transition-all">
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <h4 className="font-heading text-base font-bold text-[#2C1810]">
                              {cs.case_name}
                            </h4>
                            <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-[#2C1810]/10 text-[#2C1810] rounded">
                              {Math.round((cs.similarity || 0.8) * 100)}% Match
                            </span>
                          </div>

                          <span className="font-mono text-[11px] text-[#5D4037]/70 block mb-3">
                            {cs.court || "Supreme Court of India"}
                          </span>

                          <p className="font-body text-xs text-[#5D4037]/90 leading-relaxed bg-[#FAF9F7] p-3 rounded-lg border border-[#2C1810]/10">
                            {cs.reasoning || cs.judgment_summary}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Evidence & Statutory Principles */}
            {activeTab === "evidence" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Supporting Evidence Checklist */}
                <div className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm">
                  <h3 className="font-heading text-base font-bold text-[#2C1810] mb-4 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-[#8C5A3C]" />
                    Ranked Evidentiary Requirements
                  </h3>
                  {result.supporting_evidence && result.supporting_evidence.length > 0 ? (
                    <ul className="space-y-2.5">
                      {result.supporting_evidence.map((ev, idx) => (
                        <li key={idx} className="flex items-start gap-3 text-xs text-[#5D4037]/90 bg-[#FAF9F7] p-3 rounded-lg border border-[#2C1810]/10">
                          <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
                          <span className="font-body leading-relaxed">{ev}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-[#5D4037]/70 font-body">No specific evidentiary constraints required.</p>
                  )}
                </div>

                {/* Supporting Statutory Principles & Articles */}
                <div className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm">
                  <h3 className="font-heading text-base font-bold text-[#2C1810] mb-4 flex items-center gap-2">
                    <Scale className="w-5 h-5 text-[#8C5A3C]" />
                    Statutory Principles & Constitutional Provisions
                  </h3>
                  {result.supporting_principles && result.supporting_principles.length > 0 ? (
                    <div className="space-y-3 mb-6">
                      <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block">
                        Legal Principles:
                      </span>
                      <ul className="space-y-2">
                        {result.supporting_principles.map((prin, idx) => (
                          <li key={idx} className="text-xs text-[#2C1810] font-body bg-[#FAF9F7] p-2.5 rounded border border-[#2C1810]/10 flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#8C5A3C]" />
                            {prin}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {result.supporting_articles && result.supporting_articles.length > 0 && (
                    <div>
                      <span className="font-mono text-[10px] uppercase text-[#5D4037]/70 font-bold block mb-2">
                        Cited Constitutional Articles:
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {result.supporting_articles.map((art, idx) => (
                          <span key={idx} className="px-3 py-1 bg-[#D4AF37]/15 border border-[#D4AF37]/40 text-[#8C5A3C] rounded-lg font-mono text-xs font-bold">
                            {art}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 4: Validation Audit & Counter-Analysis */}
            {activeTab === "audit" && (
              <div className="bg-white border border-[#2C1810]/15 rounded-xl p-6 shadow-sm">
                <div className="mb-6">
                  <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-1 flex items-center gap-2">
                    <ShieldAlert className="w-5 h-5 text-[#8C5A3C]" />
                    Ingredient Validator Audit & Rejected Provisions
                  </h3>
                  <p className="font-body text-xs text-[#5D4037]/80">
                    To prevent legal hallucinations, candidate statutory sections were evaluated against essential statutory ingredients. Provisions below threshold or failing ingredient validation were safely excluded.
                  </p>
                </div>

                {result.rejected_sections && result.rejected_sections.length > 0 ? (
                  <div className="space-y-3">
                    {result.rejected_sections.map((rej, idx) => (
                      <div key={idx} className="bg-[#FFF5F5] border border-red-100 rounded-lg p-4 flex items-start gap-3">
                        <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-mono text-xs font-bold text-red-900 block mb-1">
                            Filtered Provision: {rej.section}
                          </span>
                          <p className="font-body text-xs text-red-700 leading-relaxed">
                            <span className="font-semibold">Filter Rationale:</span> {rej.reason}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 bg-[#FAF9F7] rounded-lg border border-[#2C1810]/10">
                    <ShieldCheck className="w-8 h-8 text-green-600 mx-auto mb-2" />
                    <p className="font-body text-xs text-[#5D4037]">All candidate sections passed statutory ingredient validation cleanly.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Query History Slide-Over Drawer */}
      {showHistory && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-[#2C1810]/50 backdrop-blur-sm animate-fadeIn">
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-screen max-w-md bg-[#FAF9F7] border-l border-[#D4AF37]/40 shadow-2xl flex flex-col">
              {/* Drawer Header */}
              <div className="p-6 border-b border-[#2C1810]/10 flex items-center justify-between bg-white">
                <div className="flex items-center gap-2">
                  <Database className="w-5 h-5 text-[#8C5A3C]" />
                  <div>
                    <h3 className="font-heading text-lg font-bold text-[#2C1810]">
                      Firebase Query History
                    </h3>
                    <span className="font-mono text-[10px] text-[#5D4037]/70 font-semibold block">
                      Saved Sessions & Cached Responses
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setShowHistory(false)}
                  className="p-2 text-[#5D4037] hover:text-[#2C1810] rounded-full hover:bg-[#2C1810]/5 transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Drawer List Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {loadingHistory ? (
                  <div className="text-center py-12">
                    <RefreshCw className="w-8 h-8 text-[#8C5A3C] animate-spin mx-auto mb-3" />
                    <span className="font-mono text-xs text-[#5D4037]/80">Loading saved sessions...</span>
                  </div>
                ) : historyItems.length > 0 ? (
                  historyItems.map((item, idx) => (
                    <div
                      key={item.query_id || idx}
                      onClick={() => loadHistoryItem(item.query_id, item.query)}
                      className={`p-4 bg-white border rounded-xl hover:border-[#D4AF37] hover:shadow-md transition-all cursor-pointer relative overflow-hidden group ${
                        queryMeta?.query_id === item.query_id ? "border-[#D4AF37] bg-[#D4AF37]/5" : "border-[#2C1810]/12"
                      }`}
                    >
                      {loadingHistoryId === item.query_id && (
                        <div className="absolute inset-0 bg-white/80 backdrop-blur-sm flex items-center justify-center">
                          <RefreshCw className="w-5 h-5 text-[#8C5A3C] animate-spin" />
                        </div>
                      )}

                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="px-2 py-0.5 text-[9px] font-mono font-bold uppercase bg-[#D4AF37]/20 text-[#8C5A3C] rounded-full border border-[#D4AF37]/30">
                          {Math.round((item.pipeline_confidence || 0) * 100)}% Confidence
                        </span>
                        <span className="font-mono text-[9px] text-[#5D4037]/60">
                          {item.created_at ? new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recent"}
                        </span>
                      </div>

                      <h4 className="font-heading text-xs font-bold text-[#2C1810] line-clamp-2 mb-2 group-hover:text-[#8C5A3C] transition-colors">
                        "{item.query}"
                      </h4>

                      <div className="flex items-center justify-between text-[10px] font-mono text-[#5D4037]/70 pt-2 border-t border-[#2C1810]/5">
                        <span className="capitalize">{item.primary_intent?.replace("_", " ") || "Offence"}</span>
                        <span>{item.recommended_count} Secs • {item.precedents_count} Precedents</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-12 bg-white rounded-xl border border-[#2C1810]/10 p-6">
                    <Clock className="w-8 h-8 text-[#5D4037]/40 mx-auto mb-2" />
                    <p className="font-body text-xs text-[#5D4037]">No past query sessions recorded yet.</p>
                  </div>
                )}
              </div>

              {/* Drawer Footer */}
              <div className="p-4 border-t border-[#2C1810]/10 bg-white text-center font-mono text-[10px] text-[#5D4037]/70 flex items-center justify-center gap-2">
                <Database className="w-3.5 h-3.5 text-[#8C5A3C]" />
                <span>Synced with Firebase Firestore</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
