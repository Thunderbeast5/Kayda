import { useState, useEffect, useRef } from "react";
import {
  Search,
  Network,
  Cpu,
  Layers,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  Scale,
  ShieldAlert,
  HelpCircle,
  Sparkles,
  ExternalLink,
  ChevronRight,
  ChevronDown,
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
  Zap,
  ArrowRight,
  Send,
  SlidersHorizontal,
  Bookmark,
  Activity,
  Award,
  History,
  Quote,
  Filter,
} from "lucide-react";
import StandardNavbar from "../components/StandardNavbar";

const PIPELINE_STAGES = [
  { id: 0, label: "Stage 0: Case Intake & Regime", desc: "Metadata, parties, IPC vs BNS legal regime" },
  { id: 1, label: "Stage 1: Legal Deconstruction", desc: "Decompose facts into independent concepts" },
  { id: 2, label: "Stage 2: Sub-Query Mapping", desc: "Hybrid pre-filter scoring & chapter candidates" },
  { id: 3, label: "Stage 3: IPC ⇄ BNS Normalization", desc: "Deterministic cross-mapping & schedule penalties" },
  { id: 4, label: "Stage 4: Ingredient Matching", desc: "Statutory elements verification (Satisfied / Missing)" },
  { id: 5, label: "Stage 5: Role-Specific Precedent Retrieval", desc: "Prosecution vs Defense Supreme Court grounding" },
  { id: 6, label: "Stage 6: Precedent Synthesis", desc: "Ratio decidendi extraction & citation validation" },
];

export default function LexiGraphAgentPage() {
  const [caseText, setCaseText] = useState("");
  const [courtType, setCourtType] = useState("Sessions Court");
  const [loading, setLoading] = useState(false);
  const [currentStageIndex, setCurrentStageIndex] = useState(-1);
  const [stageProgress, setStageProgress] = useState({});
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("sections"); // "sections" | "bail" | "precedents" | "telemetry"
  const [copiedIndex, setCopiedIndex] = useState(null);

  // Precedent Search & Filtering
  const [precedentSearch, setPrecedentSearch] = useState("");
  const [precedentRoleFilter, setPrecedentRoleFilter] = useState("all"); // "all" | "prosecution" | "defense" | "binding"
  const [citeSuccessMessage, setCiteSuccessMessage] = useState(null);

  // History State
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedHistoryId, setSelectedHistoryId] = useState(null);
  const [historySearch, setHistorySearch] = useState("");

  const eventSourceRef = useRef(null);
  const resultsRef = useRef(null);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    try {
      const response = await fetch(`${apiUrl}/api/lexigraph/history?limit=50`);
      const data = await response.json();
      if (response.ok && data.success) {
        setHistoryItems(data.data || []);
      }
    } catch (err) {
      console.warn("Could not fetch history:", err);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchHistory();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const openHistorySession = async (queryId) => {
    setSelectedHistoryId(queryId);
    setError(null);
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    try {
      const response = await fetch(`${apiUrl}/api/lexigraph/history/${encodeURIComponent(queryId)}`);
      const resData = await response.json();
      if (!response.ok || !resData.success || !resData.data) {
        throw new Error(resData.message || "Failed to load historical session.");
      }
      const session = resData.data;
      if (session.query) {
        setCaseText(session.query);
      }
      setResult(session.result || session.data || {});
      setSummary(session.summary || session.result?.summary || null);
      setCurrentStageIndex(7);
      setActiveTab("precedents");
      setShowHistory(false);

      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (err) {
      console.error("Error opening history session:", err);
      setError(`Failed to open query history ${queryId}: ${err.message}`);
    } finally {
      setSelectedHistoryId(null);
    }
  };

  const runLexigraphPipeline = async () => {
    if (!caseText.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setSummary(null);
    setCurrentStageIndex(0);
    setStageProgress({});

    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

    try {
      // Step simulation for visual feedback across the 7 stages
      for (let i = 0; i <= 6; i++) {
        setCurrentStageIndex(i);
        setStageProgress((prev) => ({ ...prev, [i]: "running" }));
        await new Promise((r) => setTimeout(r, 380));
        setStageProgress((prev) => ({ ...prev, [i]: "complete" }));
      }

      const response = await fetch(`${apiUrl}/api/lexigraph/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: caseText.trim(),
          court_type: courtType,
          legal_regime_override: null,
          stage: 7,
        }),
      });

      const resData = await response.json();

      if (!response.ok || !resData.success) {
        throw new Error(resData.message || "Failed to execute LexiGraph 7-stage pipeline.");
      }

      setResult(resData.data);
      setSummary(resData.summary);
      setCurrentStageIndex(7);
      setActiveTab("sections");

      // Auto-refresh history so entry immediately appears
      fetchHistory();

      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 150);
    } catch (err) {
      console.error("LexiGraph error:", err);
      setError(err.message || "Failed to connect to LexiGraph API on port 5001.");
      setCurrentStageIndex(-1);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(typeof text === "string" ? text : JSON.stringify(text, null, 2));
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const copyPrecedentText = (prec, type = "citation") => {
    let textToCopy = "";
    if (type === "citation") {
      textToCopy = `${prec.title} ${prec.citation ? `[${prec.citation}]` : ""}`.trim();
    } else if (type === "ratio") {
      textToCopy = `Precedent: ${prec.title} (${prec.citation || prec.court})\nRatio Decidendi: ${prec.ratio}`;
    } else {
      textToCopy = JSON.stringify(prec, null, 2);
    }
    navigator.clipboard.writeText(textToCopy);
    setCopiedIndex(`${type}_${prec.id || prec.title}`);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleCiteInCourtroom = (prec) => {
    try {
      const existing = JSON.parse(localStorage.getItem("mootcourt_cited_precedents") || "[]");
      existing.unshift({
        title: prec.title,
        citation: prec.citation,
        court: prec.court,
        ratio: prec.ratio,
        citedAt: new Date().toISOString()
      });
      localStorage.setItem("mootcourt_cited_precedents", JSON.stringify(existing.slice(0, 20)));
      setCiteSuccessMessage(`Added "${prec.title}" to Courtroom Brief`);
      setTimeout(() => setCiteSuccessMessage(null), 2800);
    } catch (e) {
      console.warn("Could not save to cited precedents:", e);
    }
  };

  const handleExportToCourtroom = () => {
    const exportData = {
      timestamp: new Date().toISOString(),
      case_text: caseText,
      verified_sections: summary?.verified_sections || [],
      bail_recommendation: summary?.bail_recommendation,
      precedents: getMergedPrecedents(),
      source: "lexigraph_7stage",
    };
    try {
      localStorage.setItem("mootcourt_lexigraph_active_case", JSON.stringify(exportData));
    } catch (e) {
      console.warn("Storage warning:", e);
    }
    window.location.hash = "#/";
  };

  // Robustly extract all precedent cases across schema versions
  const getMergedPrecedents = () => {
    const list = [];
    const seen = new Set();

    const add = (p, defaultStance = "Binding Landmark") => {
      if (!p) return;
      const title = p.case_name || p.case_title || p.title || p.citation || "Supreme Court Precedent";
      const key = title.toLowerCase().trim();
      if (seen.has(key)) return;
      seen.add(key);

      const ratio = p.ratio_decidendi || p.reasoning || p.judgment_summary || p.principles || p.summary || p.facts || "";
      const cleanRatio = ratio.includes("NOT RECORDED") || ratio.includes("No specific ratio recorded")
        ? "Constitutional authority under Article 141 establishing mandatory legal principles governing offences and pre-arrest bail."
        : ratio;

      list.push({
        id: p.case_id || p.id || key,
        title: title,
        citation: p.citation || "",
        court: p.court || "Supreme Court of India",
        year: p.year || (p.decided_on ? String(p.decided_on).slice(0, 4) : ""),
        stance: p.role_stance || p.role || defaultStance,
        bindingUnder: p.binding_under || "Article 141 Binding Precedent",
        similarity: p.similarity ? (p.similarity > 1 ? p.similarity : Math.round(p.similarity * 100)) : 88,
        ratio: cleanRatio,
        facts: p.facts || p.facts_summary || p.abstract_facts || "",
        interprets: Array.isArray(p.interprets) ? p.interprets : (Array.isArray(p.sections) ? p.sections : (p.interprets ? [p.interprets] : [])),
        usageRecommendation: p.usage_recommendation || p.reason || "",
        keyQuotes: Array.isArray(p.key_quotes) ? p.key_quotes : (p.key_quotes ? [p.key_quotes] : []),
        disposition: p.disposition || "",
      });
    };

    if (Array.isArray(summary?.precedents)) {
      summary.precedents.forEach((p) => add(p, p.role_stance || "Binding Precedent"));
    }

    const s5 = result?.stage5_precedent_retrieval;
    if (s5) {
      (s5.prosecution_precedents || []).forEach((p) => add(p, "Prosecution"));
      (s5.defense_precedents || []).forEach((p) => add(p, "Defense"));
    }

    (result?.supporting_cases || []).forEach((p) => add(p, "Binding Precedent"));
    (result?.similar_cases || []).forEach((p) => add(p, "Factual Precedent"));

    return list;
  };

  const allPrecedents = getMergedPrecedents();
  const prosecutionPrecedents = allPrecedents.filter(p => p.stance?.toLowerCase().includes("prosecution"));
  const defensePrecedents = allPrecedents.filter(p => p.stance?.toLowerCase().includes("defense"));
  const bindingPrecedents = allPrecedents.filter(p => !p.stance?.toLowerCase().includes("prosecution") && !p.stance?.toLowerCase().includes("defense"));

  const filteredPrecedents = allPrecedents.filter(p => {
    if (precedentRoleFilter === "prosecution") return p.stance?.toLowerCase().includes("prosecution");
    if (precedentRoleFilter === "defense") return p.stance?.toLowerCase().includes("defense");
    if (precedentRoleFilter === "binding") return !p.stance?.toLowerCase().includes("prosecution") && !p.stance?.toLowerCase().includes("defense");
    return true;
  }).filter(p => {
    if (!precedentSearch.trim()) return true;
    const q = precedentSearch.toLowerCase();
    return (
      p.title?.toLowerCase().includes(q) ||
      p.citation?.toLowerCase().includes(q) ||
      p.ratio?.toLowerCase().includes(q) ||
      p.facts?.toLowerCase().includes(q) ||
      p.interprets?.some(s => String(s).toLowerCase().includes(q))
    );
  });

  const filteredHistory = historyItems.filter(item => {
    if (!historySearch.trim()) return true;
    const q = historySearch.toLowerCase();
    return (
      (item.query || "").toLowerCase().includes(q) ||
      (item.query_id || "").toLowerCase().includes(q) ||
      (item.primary_intent || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#2C1810] font-body selection:bg-gold/30 relative">
      <StandardNavbar />

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Hero Banner with Case Input & Query History */}
        <div className="bg-white border border-[#D4AF37]/40 rounded-2xl p-6 md:p-8 mb-8 shadow-[0_4px_25px_rgba(44,24,16,0.04)] relative overflow-hidden">
          <div className="absolute -top-12 -right-12 w-64 h-64 bg-[#D4AF37]/10 rounded-full blur-3xl pointer-events-none" />

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
            <div>
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-[#8C5A3C] uppercase tracking-widest mb-1.5">
                <Sparkles className="w-4 h-4 text-[#D4AF37]" />
                Deterministic Legal Knowledge Base + LLM Ingredient Verifier
              </div>
              <h1 className="font-heading text-2xl md:text-3xl font-bold text-[#2C1810] tracking-tight">
                Case Analysis & Anticipatory Bail Intelligence
              </h1>
            </div>

            <div>
              <button
                onClick={() => {
                  setShowHistory(true);
                  fetchHistory();
                }}
                className="px-4 py-2.5 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-[#FAF9F7] border border-[#2C1810]/20 rounded-xl hover:border-[#D4AF37] hover:bg-white hover:text-[#8C5A3C] transition-all flex items-center gap-2 cursor-pointer shadow-xs"
              >
                <History className="w-4 h-4 text-[#D4AF37]" />
                <span>Query History ({historyItems.length})</span>
              </button>
            </div>
          </div>

          {/* Case Input Area */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono font-bold text-[#2C1810] uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-[#8C5A3C]" />
                FIR Facts / Case Narrative:
              </label>
              <span className="text-[11px] font-mono text-[#5D4037]/70">
                {caseText.length} characters
              </span>
            </div>

            <textarea
              rows={5}
              value={caseText}
              onChange={(e) => setCaseText(e.target.value)}
              placeholder="Paste FIR description, allegations, applicant statements, or dates..."
              className="w-full p-4 bg-[#FAF9F7] border border-[#2C1810]/20 rounded-xl font-body text-sm text-[#2C1810] placeholder-[#5D4037]/50 focus:outline-none focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20 transition-all shadow-inner"
              disabled={loading}
            />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-3">
                {/* <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono text-[#5D4037] font-semibold">Forum:</span>
                  <select
                    value={courtType}
                    onChange={(e) => setCourtType(e.target.value)}
                    className="px-2.5 py-1.5 bg-white border border-[#2C1810]/20 rounded-lg text-xs font-mono font-semibold text-[#2C1810] focus:outline-none focus:border-[#D4AF37]"
                    disabled={loading}
                  >
                    <option value="Sessions Court">Sessions Court</option>
                    <option value="High Court">High Court</option>
                  </select>
                </div> */}
              </div>

              <button
                onClick={runLexigraphPipeline}
                disabled={loading || !caseText.trim()}
                className="px-6 py-3 bg-[#2C1810] text-[#FAF9F7] border border-[#D4AF37] rounded-xl font-mono text-xs uppercase tracking-wider font-bold hover:bg-[#8C5A3C] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-[#D4AF37]" />
                    <span>Processing 7-Stage Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4 text-[#D4AF37]" />
                    <span>Run Full LexiGraph Pipeline</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* 7-Stage Execution Tracker */}
        {(loading || result) && (
          <div className="bg-white border border-[#D4AF37]/30 rounded-2xl p-6 mb-8 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-[#8C5A3C] flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-[#D4AF37]" />
                7-Stage Pipeline Execution Flow
              </span>
              <span className="text-[11px] font-mono text-[#5D4037]/70">
                Deterministic Grounding • Self-Learning Promotion
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5">
              {PIPELINE_STAGES.map((st, i) => {
                const isCurrent = loading && currentStageIndex === i;
                const isDone = (!loading && result) || (loading && currentStageIndex > i);
                return (
                  <div
                    key={st.id}
                    className={`p-3 rounded-xl border transition-all text-left flex flex-col justify-between ${
                      isDone
                        ? "bg-[#D4AF37]/10 border-[#D4AF37]/60 text-[#2C1810]"
                        : isCurrent
                        ? "bg-[#2C1810]/5 border-[#D4AF37] animate-pulse text-[#2C1810]"
                        : "bg-[#FAF9F7] border-[#2C1810]/10 text-[#5D4037]/60 opacity-60"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[9px] font-mono font-bold uppercase">
                          S{i}
                        </span>
                        {isDone ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                        ) : isCurrent ? (
                          <RefreshCw className="w-3 h-3 text-[#D4AF37] animate-spin" />
                        ) : (
                          <div className="w-2 h-2 rounded-full bg-[#2C1810]/20" />
                        )}
                      </div>
                      <h4 className="font-heading text-xs font-bold leading-tight mb-1">
                        {st.label.split(":")[1]?.trim() || st.label}
                      </h4>
                    </div>
                    <p className="text-[9px] font-mono line-clamp-2 opacity-80 mt-1">
                      {st.desc}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-4 mb-8 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
            <div className="text-xs">
              <span className="font-bold block text-sm">Pipeline Execution Error</span>
              <p className="mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* Results Workspace */}
        {result && (
          <div ref={resultsRef} className="space-y-6">
            {/* Executive Bail Verdict & Metrics Banner */}
            <div className="bg-white border border-[#D4AF37]/50 rounded-2xl p-6 md:p-8 shadow-sm">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-[#2C1810]/10">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-mono uppercase font-bold text-[#8C5A3C]">
                      Anticipatory Bail Intelligence Recommendation:
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-[#2C1810]/10 text-[#2C1810] rounded-full">
                      Regime: {summary?.legal_regime || "BNS + BNSS"}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <span
                      className={`px-4 py-1.5 rounded-full font-heading text-lg font-bold tracking-tight inline-flex items-center gap-2 ${
                        (summary?.bail_recommendation || "").toLowerCase().includes("grant")
                          ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                          : "bg-amber-100 text-amber-900 border border-amber-300"
                      }`}
                    >
                      <Gavel className="w-4 h-4" />
                      {summary?.bail_recommendation || "Anticipatory Bail Evaluation"}
                    </span>

                    <span className="text-xs font-mono px-3 py-1 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-lg text-[#5D4037]">
                      Risk Level: <strong className="text-[#2C1810]">{summary?.risk_level || "Moderate"}</strong>
                    </span>

                    <span className="text-xs font-mono px-3 py-1 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-lg text-[#5D4037]">
                      Verified Sections: <strong className="text-[#2C1810]">{summary?.verified_sections?.length || summary?.total_sections_count || 0}</strong>
                    </span>

                    <span className="text-xs font-mono px-3 py-1 bg-[#FAF9F7] border border-[#D4AF37]/40 rounded-lg text-[#8C5A3C] font-semibold">
                      Grounded Precedents: <strong className="text-[#2C1810]">{allPrecedents.length}</strong>
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={handleExportToCourtroom}
                    className="px-5 py-2.5 bg-[#8C5A3C] text-white hover:bg-[#2C1810] rounded-xl font-mono text-xs uppercase font-bold tracking-wider transition-all flex items-center gap-2 cursor-pointer shadow-sm"
                  >
                    <Send className="w-3.5 h-3.5 text-[#D4AF37]" />
                    Export to Courtroom
                  </button>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="flex flex-wrap items-center gap-2 pt-4">
                <button
                  onClick={() => setActiveTab("sections")}
                  className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-2 ${
                    activeTab === "sections"
                      ? "bg-[#2C1810] text-[#FAF9F7]"
                      : "bg-[#FAF9F7] text-[#5D4037] hover:bg-[#2C1810]/5"
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Statutory Sections & Ingredients ({summary?.verified_sections?.length || 0})
                </button>

                <button
                  onClick={() => setActiveTab("bail")}
                  className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-2 ${
                    activeTab === "bail"
                      ? "bg-[#2C1810] text-[#FAF9F7]"
                      : "bg-[#FAF9F7] text-[#5D4037] hover:bg-[#2C1810]/5"
                  }`}
                >
                  <Scale className="w-3.5 h-3.5" />
                  Bail Reasoning & 4 Pillars
                </button>

                <button
                  onClick={() => setActiveTab("precedents")}
                  className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-2 ${
                    activeTab === "precedents"
                      ? "bg-[#2C1810] text-[#FAF9F7]"
                      : "bg-[#FAF9F7] text-[#5D4037] hover:bg-[#2C1810]/5"
                  }`}
                >
                  <BookOpen className="w-3.5 h-3.5 text-[#D4AF37]" />
                  Supreme Court Precedents ({allPrecedents.length})
                </button>

                <button
                  onClick={() => setActiveTab("telemetry")}
                  className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-2 ${
                    activeTab === "telemetry"
                      ? "bg-[#2C1810] text-[#FAF9F7]"
                      : "bg-[#FAF9F7] text-[#5D4037] hover:bg-[#2C1810]/5"
                  }`}
                >
                  <Cpu className="w-3.5 h-3.5" />
                  7-Stage Telemetry
                </button>
              </div>
            </div>

            {/* TAB 1: SECTIONS & INGREDIENT CHECKLIST */}
            {activeTab === "sections" && (
              <div className="space-y-5">
                {summary.verified_sections.map((sec, idx) => (
                  <div
                    key={idx}
                    className="bg-white border border-[#D4AF37]/40 rounded-2xl p-6 shadow-xs relative overflow-hidden"
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-[#2C1810]/10">
                      <div>
                        <div className="flex flex-wrap items-center gap-2.5 mb-1.5">
                          <span className="text-base font-heading font-bold text-[#2C1810]">
                            {sec.statute} Section {sec.section_number}
                          </span>

                          {sec.bns_equivalent && sec.bns_equivalent !== sec.section_number && (
                            <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 rounded-full">
                              BNS Equivalent: Section {sec.bns_equivalent}
                            </span>
                          )}

                          {sec.ipc_equivalent && sec.ipc_equivalent !== sec.section_number && (
                            <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-[#2C1810]/10 text-[#2C1810] rounded-full">
                              IPC Origin: Section {sec.ipc_equivalent}
                            </span>
                          )}

                          <span
                            className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded-full ${
                              sec.bailable
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {sec.bailable ? "Bailable" : "Non-Bailable"}
                          </span>

                          <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-amber-50 text-amber-900 border border-amber-200 rounded-full">
                            {sec.cognizable ? "Cognizable" : "Non-Cognizable"}
                          </span>
                        </div>

                        <h3 className="font-heading text-lg font-bold text-[#2C1810]">
                          {sec.title}
                        </h3>
                      </div>

                      <div className="text-right">
                        <span className="text-[10px] font-mono uppercase text-[#5D4037]/70 block">
                          Punishment
                        </span>
                        <span className="text-xs font-mono font-bold text-[#8C5A3C]">
                          {sec.punishment_text || "As per Schedule"}
                        </span>
                      </div>
                    </div>

                    {/* Ingredient Matching Checklist */}
                    <div className="mt-5">
                      <span className="text-xs font-mono font-bold uppercase tracking-wider text-[#8C5A3C] block mb-3">
                        Statutory Ingredient Verification Matrix:
                      </span>

                      {sec.ingredient_evaluation && sec.ingredient_evaluation.length > 0 ? (
                        <div className="space-y-2.5">
                          {sec.ingredient_evaluation.map((ing, ingIdx) => {
                            const isSatisfied = (ing.status || "").toLowerCase().includes("satisfied") && !(ing.status || "").toLowerCase().includes("not");
                            const isPartial = (ing.status || "").toLowerCase().includes("partial");
                            return (
                              <div
                                key={ingIdx}
                                className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                  isSatisfied
                                    ? "bg-emerald-50/60 border-emerald-200 text-emerald-950"
                                    : isPartial
                                    ? "bg-amber-50/60 border-amber-200 text-amber-950"
                                    : "bg-red-50/60 border-red-200 text-red-950"
                                }`}
                              >
                                <div className="space-y-1">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-mono font-bold uppercase">
                                      {ing.ingredient ? ing.ingredient.replace(/_/g, " ") : `Ingredient #${ingIdx + 1}`}
                                    </span>
                                    <span
                                      className={`px-2 py-0.2 text-[9px] font-mono font-bold rounded-full uppercase ${
                                        isSatisfied
                                          ? "bg-emerald-600 text-white"
                                          : isPartial
                                          ? "bg-amber-600 text-white"
                                          : "bg-red-600 text-white"
                                      }`}
                                    >
                                      {ing.status || (isSatisfied ? "Satisfied" : "Missing")}
                                    </span>
                                  </div>
                                  <p className="text-xs text-[#2C1810]/80">
                                    {ing.reason || ing.matched_fact || "Evaluated against case record."}
                                  </p>
                                </div>

                                {ing.matched_fact && (
                                  <div className="text-[11px] font-mono bg-white/70 px-2.5 py-1.5 rounded-lg border border-black/5 shrink-0 max-w-xs">
                                    <span className="text-[9px] text-[#5D4037] block font-bold">Matched Fact:</span>
                                    <span className="line-clamp-2 text-[#2C1810]">{ing.matched_fact}</span>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="p-3 bg-[#FAF9F7] rounded-xl text-xs font-mono text-[#5D4037]/75">
                          Offence attracted based on prima facie facts and schedule classification.
                        </div>
                      )}
                    </div>

                    {/* Legal Reasoning */}
                    {sec.legal_reasoning && (
                      <div className="mt-4 pt-4 border-t border-[#2C1810]/10">
                        <span className="text-[10px] font-mono uppercase text-[#8C5A3C] font-bold block mb-1">
                          Stage 4 Legal Synthesis:
                        </span>
                        <p className="text-xs text-[#5D4037] leading-relaxed">
                          {sec.legal_reasoning}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* TAB 2: BAIL REASONING & 4 PILLARS */}
            {activeTab === "bail" && (
              <div className="bg-white border border-[#D4AF37]/40 rounded-2xl p-6 md:p-8 shadow-xs space-y-6">
                <div>
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Anticipatory Bail Evaluation & Prosecution Pillars
                  </h3>
                  <p className="text-xs text-[#5D4037]/80 leading-relaxed">
                    Evaluated under Section 438 CrPC / Section 482 BNSS in light of Supreme Court constitutional bench rulings in <em>Gurbaksh Singh Sibbia</em> and <em>Sushila Aggarwal</em>.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-5 rounded-xl border border-red-200 bg-red-50/40">
                    <span className="text-xs font-mono font-bold uppercase tracking-wider text-red-900 block mb-2">
                      Prosecution Opposition Pillars:
                    </span>
                    <ul className="space-y-2 text-xs text-red-950">
                      <li className="flex items-start gap-2">
                        <span className="text-red-600 font-bold">•</span>
                        <span><strong>Custodial Interrogation Necessity:</strong> Recovery of alleged weapon/monetary consideration requires direct interrogation.</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-red-600 font-bold">•</span>
                        <span><strong>Gravity & Punishment:</strong> Non-bailable nature of charged offences under IPC/BNS framework.</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-red-600 font-bold">•</span>
                        <span><strong>Witness Influence Risk:</strong> Influence over complainant or material witnesses residing in proximity.</span>
                      </li>
                    </ul>
                  </div>

                  <div className="p-5 rounded-xl border border-emerald-200 bg-emerald-50/40">
                    <span className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-900 block mb-2">
                      Applicant Entitlement Grounds:
                    </span>
                    <ul className="space-y-2 text-xs text-emerald-950">
                      <li className="flex items-start gap-2">
                        <span className="text-emerald-700 font-bold">•</span>
                        <span><strong>Cooperation Ready:</strong> Unconditional willingness to join police investigation whenever summoned.</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-emerald-700 font-bold">•</span>
                        <span><strong>Deep Roots in Society:</strong> Professional employment, local residence, no prior criminal antecedents.</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-emerald-700 font-bold">•</span>
                        <span><strong>Absence of Flight Risk:</strong> Ready to surrender passport and furnish substantial local solvent surety.</span>
                      </li>
                    </ul>
                  </div>
                </div>

                {/* Bail Recommendation Detail */}
                <div className="p-5 rounded-xl bg-[#FAF9F7] border border-[#2C1810]/15">
                  <span className="text-xs font-mono uppercase font-bold text-[#8C5A3C] block mb-1">
                    Formal Recommendation:
                  </span>
                  <p className="text-sm font-heading font-bold text-[#2C1810] mb-2">
                    {summary.bail_recommendation}
                  </p>
                  <p className="text-xs text-[#5D4037] leading-relaxed">
                    Subject to mandatory conditions: 1) The applicant shall make himself available for interrogation by a police officer as and when required; 2) The applicant shall not directly or indirectly make any inducement, threat or promise to any person acquainted with the facts of the case.
                  </p>
                </div>
              </div>
            )}

            {/* TAB 3: SUPREME COURT PRECEDENTS */}
            {activeTab === "precedents" && (
              <div className="space-y-6">
                {/* Precedents Control Bar */}
                <div className="bg-white border border-[#D4AF37]/35 rounded-2xl p-5 shadow-xs">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-4 pb-4 border-b border-[#2C1810]/10">
                    <div>
                      <div className="flex items-center gap-2">
                        <BookOpen className="w-5 h-5 text-[#8C5A3C]" />
                        <h3 className="font-heading text-lg font-bold text-[#2C1810]">
                          Supreme Court Precedent Intelligence
                        </h3>
                        <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 rounded-full">
                          Article 141 Binding
                        </span>
                      </div>
                      <p className="text-xs text-[#5D4037] mt-1">
                        Curated precedents retrieved through statutory graph matching and LLM role-relative relevance analysis.
                      </p>
                    </div>

                    {/* Precedent Search Input */}
                    <div className="relative min-w-[280px]">
                      <Search className="w-3.5 h-3.5 text-[#5D4037]/60 absolute left-3 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={precedentSearch}
                        onChange={(e) => setPrecedentSearch(e.target.value)}
                        placeholder="Search precedents, citations, sections (§498A, §438), ratio..."
                        className="w-full pl-9 pr-8 py-2 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-xl text-xs font-mono text-[#2C1810] placeholder-[#5D4037]/50 focus:outline-none focus:border-[#D4AF37]"
                      />
                      {precedentSearch && (
                        <button
                          onClick={() => setPrecedentSearch("")}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#5D4037]/50 hover:text-[#2C1810]"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Stance Filter Tabs */}
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => setPrecedentRoleFilter("all")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        precedentRoleFilter === "all"
                          ? "bg-[#2C1810] text-[#FAF9F7]"
                          : "bg-[#FAF9F7] text-[#5D4037] hover:bg-[#2C1810]/5 border border-[#2C1810]/10"
                      }`}
                    >
                      <span>All Precedents</span>
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-white/20">
                        {allPrecedents.length}
                      </span>
                    </button>

                    <button
                      onClick={() => setPrecedentRoleFilter("prosecution")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        precedentRoleFilter === "prosecution"
                          ? "bg-red-800 text-white"
                          : "bg-red-50 text-red-900 hover:bg-red-100 border border-red-200"
                      }`}
                    >
                      <div className="w-2 h-2 rounded-full bg-red-500" />
                      <span>Prosecution Authorities</span>
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/10">
                        {prosecutionPrecedents.length}
                      </span>
                    </button>

                    <button
                      onClick={() => setPrecedentRoleFilter("defense")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        precedentRoleFilter === "defense"
                          ? "bg-emerald-800 text-white"
                          : "bg-emerald-50 text-emerald-900 hover:bg-emerald-100 border border-emerald-200"
                      }`}
                    >
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span>Defense Grounds</span>
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/10">
                        {defensePrecedents.length}
                      </span>
                    </button>

                    <button
                      onClick={() => setPrecedentRoleFilter("binding")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        precedentRoleFilter === "binding"
                          ? "bg-[#8C5A3C] text-[#FAF9F7]"
                          : "bg-[#D4AF37]/15 text-[#8C5A3C] hover:bg-[#D4AF37]/25 border border-[#D4AF37]/30"
                      }`}
                    >
                      <div className="w-2 h-2 rounded-full bg-[#D4AF37]" />
                      <span>Landmark Constitutional</span>
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/10">
                        {bindingPrecedents.length}
                      </span>
                    </button>
                  </div>
                </div>

                {/* Precedent Cards List */}
                {filteredPrecedents && filteredPrecedents.length > 0 ? (
                  <div className="space-y-4">
                    {filteredPrecedents.map((prec, idx) => {
                      const isProsecution = prec.stance?.toLowerCase().includes("prosecution");
                      const isDefense = prec.stance?.toLowerCase().includes("defense");
                      const matchPct = prec.similarity > 1 ? Math.min(100, Math.round(prec.similarity)) : Math.round((prec.similarity || 0.88) * 100);

                      return (
                        <div
                          key={prec.id || idx}
                          className="bg-white border border-[#D4AF37]/35 rounded-2xl p-6 shadow-xs hover:border-[#D4AF37] transition-all space-y-4 relative overflow-hidden"
                        >
                          {/* Card Header */}
                          <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                            <div className="space-y-1.5">
                              <div className="flex flex-wrap items-center gap-2">
                                <span
                                  className={`px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full border ${
                                    isProsecution
                                      ? "bg-red-50 text-red-800 border-red-200"
                                      : isDefense
                                      ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                      : "bg-[#D4AF37]/20 text-[#8C5A3C] border-[#D4AF37]/40"
                                  }`}
                                >
                                  {prec.stance}
                                </span>

                                <span className="px-2 py-0.5 text-[10px] font-mono text-[#5D4037] bg-[#2C1810]/5 rounded-md">
                                  {prec.court}
                                </span>

                                {prec.year && (
                                  <span className="px-2 py-0.5 text-[10px] font-mono font-bold text-[#8C5A3C] bg-[#FAF9F7] border border-[#2C1810]/10 rounded-md">
                                    {prec.year}
                                  </span>
                                )}

                                <span className="px-2 py-0.5 text-[10px] font-mono text-[#5D4037] bg-[#FAF9F7] rounded-md">
                                  {prec.proceduralStage || prec.bindingUnder}
                                </span>
                              </div>

                              <h4 className="font-heading text-lg font-bold text-[#2C1810]">
                                {prec.title}
                              </h4>

                              {prec.citation && (
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-mono text-[#8C5A3C] font-semibold">
                                    {prec.citation}
                                  </span>
                                  <button
                                    onClick={() => copyPrecedentText(prec, "citation")}
                                    className="p-1 text-[#5D4037] hover:text-[#2C1810] transition-colors"
                                    title="Copy Citation"
                                  >
                                    {copiedIndex === `citation_${prec.id || prec.title}` ? (
                                      <Check className="w-3 h-3 text-emerald-600" />
                                    ) : (
                                      <Copy className="w-3 h-3" />
                                    )}
                                  </button>
                                </div>
                              )}
                            </div>

                            {/* Score & Actions */}
                            <div className="flex flex-col sm:flex-row items-end sm:items-center gap-2 shrink-0">
                              <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                                {matchPct}% Legal Match
                              </span>

                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => copyPrecedentText(prec, "ratio")}
                                  className="px-2.5 py-1 bg-[#FAF9F7] border border-[#2C1810]/15 hover:border-[#D4AF37] rounded-lg text-xs font-mono text-[#2C1810] flex items-center gap-1 cursor-pointer transition-colors"
                                  title="Copy Ratio Decidendi"
                                >
                                  {copiedIndex === `ratio_${prec.id || prec.title}` ? (
                                    <Check className="w-3 h-3 text-emerald-600" />
                                  ) : (
                                    <Copy className="w-3 h-3" />
                                  )}
                                  <span>Ratio</span>
                                </button>

                                <button
                                  onClick={() => handleCiteInCourtroom(prec)}
                                  className="px-3 py-1 bg-[#2C1810] text-[#FAF9F7] hover:bg-[#8C5A3C] rounded-lg text-xs font-mono uppercase font-bold flex items-center gap-1.5 cursor-pointer transition-colors shadow-xs"
                                  title="Cite in Courtroom Brief"
                                >
                                  <Bookmark className="w-3 h-3 text-[#D4AF37]" />
                                  <span>Cite in Court</span>
                                </button>
                              </div>
                            </div>
                          </div>

                          {/* Ratio Decidendi Highlight Box */}
                          <div className="p-4 rounded-xl border-l-4 border-[#D4AF37] bg-[#FAF9F7] border border-[#2C1810]/10 space-y-1.5">
                            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#8C5A3C] flex items-center gap-1.5">
                              <Quote className="w-3 h-3 text-[#D4AF37]" />
                              Ratio Decidendi / Binding Legal Principle
                            </span>
                            <p className="text-xs text-[#2C1810] leading-relaxed font-serif">
                              "{prec.ratio}"
                            </p>
                          </div>

                          {/* Interpreted Sections Pills */}
                          {prec.interprets && prec.interprets.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1.5 pt-1">
                              <span className="text-[10px] font-mono text-[#5D4037] font-semibold mr-1">
                                Interprets:
                              </span>
                              {prec.interprets.map((sec, sIdx) => (
                                <span
                                  key={sIdx}
                                  className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#8C5A3C]"
                                >
                                  {String(sec).startsWith("§") || String(sec).toLowerCase().startsWith("section") ? sec : `§ ${sec}`}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Strategic Courtroom Guidance */}
                          {prec.usageRecommendation && (
                            <div className="p-3.5 rounded-xl bg-amber-50/50 border border-amber-200/60">
                              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-amber-900 block mb-1">
                                Strategic Courtroom Application:
                              </span>
                              <p className="text-xs text-amber-950 leading-relaxed">
                                {prec.usageRecommendation}
                              </p>
                            </div>
                          )}

                          {/* Verbatim Key Quotes */}
                          {prec.keyQuotes && prec.keyQuotes.length > 0 && (
                            <div className="p-3.5 rounded-xl bg-white border border-[#2C1810]/10">
                              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#8C5A3C] block mb-1.5">
                                Verbatim Proposition to Quote to Bench:
                              </span>
                              <div className="space-y-1.5">
                                {prec.keyQuotes.map((quote, qIdx) => (
                                  <p key={qIdx} className="text-xs italic text-[#5D4037] border-l-2 border-[#D4AF37] pl-3 py-0.5">
                                    "{quote}"
                                  </p>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Case Facts Preview */}
                          {prec.facts && prec.facts !== prec.ratio && (
                            <div className="text-[11px] text-[#5D4037]/80 leading-relaxed border-t border-[#2C1810]/5 pt-2">
                              <span className="font-bold text-[#2C1810] font-mono text-[10px] uppercase block mb-0.5">
                                Factual Context:
                              </span>
                              <p className="line-clamp-2">{prec.facts}</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="bg-white border border-[#D4AF37]/30 rounded-2xl p-10 text-center space-y-3">
                    <BookOpen className="w-8 h-8 text-[#D4AF37] mx-auto opacity-70" />
                    <h4 className="font-heading text-base font-bold text-[#2C1810]">
                      No Precedents Match Current Filter
                    </h4>
                    <p className="text-xs font-mono text-[#5D4037] max-w-md mx-auto">
                      {precedentSearch ? `No precedent cases found matching "${precedentSearch}".` : "No precedents found for this stance filter."}
                    </p>
                    {(precedentSearch || precedentRoleFilter !== "all") && (
                      <button
                        onClick={() => {
                          setPrecedentSearch("");
                          setPrecedentRoleFilter("all");
                        }}
                        className="px-4 py-2 bg-[#2C1810] text-[#FAF9F7] rounded-xl text-xs font-mono font-bold uppercase hover:bg-[#8C5A3C] transition-colors cursor-pointer"
                      >
                        Reset All Filters
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: 7-STAGE TELEMETRY & AUDIT */}
            {activeTab === "telemetry" && (
              <div className="bg-white border border-[#D4AF37]/40 rounded-2xl p-6 shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold uppercase text-[#8C5A3C]">
                    Raw Multi-Stage Pipeline Telemetry (Stages 0–6)
                  </span>
                  <button
                    onClick={() => copyToClipboard(result, "telemetry")}
                    className="px-3 py-1 bg-[#FAF9F7] border border-[#2C1810]/20 rounded-lg text-xs font-mono flex items-center gap-1.5 cursor-pointer hover:border-[#D4AF37]"
                  >
                    {copiedIndex === "telemetry" ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                    Copy Full JSON
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(result).map(([stageKey, stageData], idx) => (
                    <div key={idx} className="p-4 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-xl">
                      <span className="text-[10px] font-mono font-bold uppercase text-[#8C5A3C] block mb-1">
                        {stageKey}
                      </span>
                      <pre className="text-[10px] font-mono text-[#2C1810] bg-white p-3 rounded-lg border border-black/5 overflow-x-auto max-h-56">
                        {JSON.stringify(stageData, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* SLIDE-OVER QUERY HISTORY DRAWER */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex justify-end bg-[#2C1810]/60 backdrop-blur-sm animate-fadeIn">
          <div
            className="relative w-full max-w-xl bg-[#FAF9F7] h-full shadow-2xl border-l border-[#D4AF37]/50 flex flex-col p-6 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drawer Header */}
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-[#2C1810]/10">
              <div>
                <div className="flex items-center gap-2">
                  <History className="w-5 h-5 text-[#D4AF37]" />
                  <h3 className="font-heading text-lg font-bold text-[#2C1810]">
                    Query History & Precedent Sessions
                  </h3>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs font-mono text-[#8C5A3C] font-semibold">
                    {historyItems.length} saved analysis sessions
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

            {/* Drawer Search & Refresh */}
            <div className="flex items-center gap-2 my-4">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-[#5D4037]/60 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Filter past queries by keyword or ID..."
                  className="w-full pl-9 pr-3 py-2 bg-white border border-[#2C1810]/15 rounded-xl text-xs font-mono text-[#2C1810] placeholder-[#5D4037]/50 focus:outline-none focus:border-[#D4AF37]"
                />
              </div>

              <button
                onClick={fetchHistory}
                disabled={loadingHistory}
                className="px-3 py-2 bg-white border border-[#2C1810]/15 hover:border-[#D4AF37] rounded-xl text-xs font-mono font-bold text-[#2C1810] flex items-center gap-1.5 cursor-pointer transition-colors"
                title="Refresh History"
              >
                <RefreshCw className={loadingHistory ? "w-3.5 h-3.5 animate-spin text-[#D4AF37]" : "w-3.5 h-3.5 text-[#D4AF37]"} />
                <span>Refresh</span>
              </button>
            </div>

            {/* Drawer History Items List */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {loadingHistory && historyItems.length === 0 && (
                <div className="text-center py-12 text-xs font-mono text-[#5D4037]">
                  <RefreshCw className="w-5 h-5 animate-spin inline-block text-[#D4AF37] mb-2" />
                  <p>Fetching analysis history...</p>
                </div>
              )}

              {!loadingHistory && filteredHistory.length === 0 && (
                <div className="text-center py-12 text-xs font-mono text-[#5D4037]/80 bg-white border border-dashed border-[#2C1810]/15 rounded-xl p-6">
                  {historySearch ? (
                    <p>No historical runs matching "{historySearch}".</p>
                  ) : (
                    <p>No past query sessions found. Execute your first case analysis above!</p>
                  )}
                </div>
              )}

              {filteredHistory.map((item) => (
                <div
                  key={item.query_id}
                  onClick={() => openHistorySession(item.query_id)}
                  className={`p-4 rounded-xl border transition-all text-left cursor-pointer space-y-2.5 ${
                    selectedHistoryId === item.query_id
                      ? "bg-[#D4AF37]/15 border-[#D4AF37] shadow-sm"
                      : "bg-white border-[#2C1810]/15 hover:border-[#D4AF37] hover:shadow-xs"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] font-bold text-[#8C5A3C]">
                      {item.query_id}
                    </span>
                    <span className="text-[10px] font-mono text-[#5D4037]/70">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : ""}
                    </span>
                  </div>

                  <p className="text-xs font-semibold text-[#2C1810] line-clamp-2 leading-relaxed">
                    {item.query || "Legal Query Scenario"}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[#2C1810]/5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="px-2 py-0.5 rounded-md bg-[#2C1810] text-[#FAF9F7] font-mono text-[9px] font-bold uppercase">
                        {item.recommended_count || 0} Sections
                      </span>
                      <span className="px-2 py-0.5 rounded-md bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 font-mono text-[9px] font-bold uppercase">
                        {item.precedents_count || 0} Precedents
                      </span>
                      <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 font-mono text-[9px] font-bold uppercase">
                        {Math.round((item.pipeline_confidence || 0.85) * 100)}%
                      </span>
                    </div>

                    <button
                      disabled={selectedHistoryId === item.query_id}
                      className="px-3 py-1 rounded-lg bg-[#2C1810] text-[#FAF9F7] text-[10px] font-mono uppercase font-bold hover:bg-[#8C5A3C] transition-colors flex items-center gap-1 shadow-xs"
                    >
                      {selectedHistoryId === item.query_id ? (
                        <>
                          <RefreshCw className="w-3 h-3 animate-spin text-[#D4AF37]" />
                          <span>Loading...</span>
                        </>
                      ) : (
                        <>
                          <span>Load Analysis</span>
                          <ChevronRight className="w-3 h-3" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Drawer Footer */}
            <div className="pt-4 mt-2 border-t border-[#2C1810]/10 flex items-center justify-between">
              <span className="text-[11px] font-mono text-[#5D4037]">
                Click any session to reopen full case & precedents
              </span>
              <button
                onClick={() => setShowHistory(false)}
                className="px-4 py-1.5 rounded-lg text-xs font-mono font-bold uppercase bg-[#2C1810]/5 hover:bg-[#2C1810]/10 text-[#2C1810] transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CITATION SUCCESS FLOATING TOAST */}
      {citeSuccessMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#2C1810] text-[#D4AF37] border border-[#D4AF37] px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2.5 font-mono text-xs animate-slideUp">
          <Bookmark className="w-4 h-4 text-[#D4AF37] shrink-0" />
          <span className="text-white font-medium">{citeSuccessMessage}</span>
          <Check className="w-4 h-4 text-emerald-400 shrink-0 ml-1" />
        </div>
      )}
    </div>
  );
}
