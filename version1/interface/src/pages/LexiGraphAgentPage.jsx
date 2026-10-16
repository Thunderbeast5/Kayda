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
} from "lucide-react";
import StandardNavbar from "../components/StandardNavbar";

const SAMPLE_BENCHMARK_CASES = [
  {
    id: "dowry_cruelty",
    title: "Matrimonial Cruelty & Dowry Demand",
    sections: "IPC 498A ⇄ BNS 85",
    regime: "IPC + CrPC",
    court: "Sessions Court",
    summary: "Demand for ₹5L dowry and vehicle, verbal cruelty, physical eviction.",
    text: "The applicant seeks anticipatory bail in connection with FIR No. 204/2024 registered at Pune Police Station. The complainant, Kavya, married the applicant Rohan in December 2021. The FIR alleges that shortly after marriage, the applicant and his parents commenced persistent demands for an additional ₹5,00,000 cash dowry and a vehicle. Complainant alleges verbal abuse, mental cruelty, financial restrictions, and that on 14th June 2024, she was physically assaulted and forced out of the house. The applicant submits that allegations are exaggerated arising from matrimonial discord, no MLC injury certificate exists, and he is a respected software professional willing to cooperate with investigation.",
  },
  {
    id: "property_assault",
    title: "House Trespass & Simple Hurt with Threat",
    sections: "BNS 332, 115, 351 (IPC 452, 323, 506)",
    regime: "BNS + BNSS",
    court: "Sessions Court",
    summary: "Boundary dispute assault with stick, minor injury, threat to life.",
    text: "The applicant seeks anticipatory bail after an FIR was registered at Nashik Road Police Station on 15-08-2024 alleging offences under Sections 332, 115, and 351(2) BNS. Complainant alleges applicant unlawfully entered his courtyard during an argument regarding a boundary fence, pushed him, and brandished a wooden stick causing simple contusions. Complainant also alleges applicant threatened dire consequences if civil suit was not withdrawn. The applicant submits this is a counterblast to an ongoing civil title injunction, cross-complaints were lodged, injuries are minor abrasions, and custodial interrogation is wholly unnecessary.",
  },
  {
    id: "extortion_threat",
    title: "Extortion & Cyber Blackmail",
    sections: "BNS 308, 351 (IPC 384, 506)",
    regime: "BNS + BNSS",
    court: "High Court",
    summary: "Demands for ₹10L under threat of leaking confidential trade secrets.",
    text: "Anticipatory bail application under Section 482 BNSS before the High Court of Bombay. FIR lodged at Cyber Police Station Bandra alleging that former business consultant demanded ₹10,00,000 under threat of publishing confidential trade records and filing defamatory criminal petitions against the complainant company directors. Complainant transferred ₹2,00,000 into a bank account. Applicant contends that the sum requested was legitimate outstanding consultancy fee as per signed MoA, emails demonstrate contractual settlement negotiations, and no criminal extortion was ever intended.",
  },
  {
    id: "culpable_homicide_negligence",
    title: "Rash & Negligent Driving Collision",
    sections: "BNS 106 (IPC 304A)",
    regime: "BNS + BNSS",
    court: "Sessions Court",
    summary: "Motor vehicle junction collision resulting in fatal head trauma.",
    text: "FIR No. 88/2024 registered under Section 106(1) BNS at Thane City Police Station. Accused driver of commercial truck was involved in a collision with a motorcyclist at a dimly lit junction. Motorcyclist succumbed to head injuries at Civil Hospital. Accused remained at the scene, called ambulance, and submitted to breathalyzer test indicating zero blood alcohol content. Applicant seeks anticipatory bail citing mechanical brake failure, absence of rash intention, complete cooperation with police, and availability of dashcam telemetry.",
  },
];

const PIPELINE_STAGES = [
  { id: 0, label: "Stage 0: Case Intake & Regime", desc: "Metadata, parties, IPC vs BNS legal regime" },
  { id: 1, label: "Stage 1: Legal Deconstruction", desc: "Decompose facts into independent concepts" },
  { id: 2, label: "Stage 2: Sub-Query Mapping", desc: "Hybrid pre-filter scoring & chapter candidates" },
  { id: 3, label: "Stage 3: IPC ⇄ BNS Normalization", desc: "Deterministic cross-mapping & schedule penalties" },
  { id: 4, label: "Stage 4: Ingredient Matching", desc: "Statutory elements verification (Satisfied / Missing)" },
  { id: 5, label: "Stage 5: Anticipatory Bail Reasoning", desc: "Flight risk, custodial necessity & recommendation" },
  { id: 6, label: "Stage 6: Precedent Retrieval", desc: "Supreme Court citations & ratio decidendi grounding" },
];

export default function LexiGraphAgentPage({ onSwitchToCypher }) {
  const [caseText, setCaseText] = useState(SAMPLE_BENCHMARK_CASES[0].text);
  const [selectedCaseId, setSelectedCaseId] = useState(SAMPLE_BENCHMARK_CASES[0].id);
  const [courtType, setCourtType] = useState("Sessions Court");
  const [legalRegime, setLegalRegime] = useState("auto");
  const [loading, setLoading] = useState(false);
  const [currentStageIndex, setCurrentStageIndex] = useState(-1);
  const [stageProgress, setStageProgress] = useState({});
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("sections"); // "sections" | "bail" | "precedents" | "telemetry"
  const [copiedIndex, setCopiedIndex] = useState(null);

  // Quick Statute Lookup
  const [statuteQuery, setStatuteQuery] = useState("");
  const [statuteResult, setStatuteResult] = useState(null);
  const [loadingStatute, setLoadingStatute] = useState(false);
  const [showStatuteModal, setShowStatuteModal] = useState(false);

  // History Drawer State
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const eventSourceRef = useRef(null);

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

  const handleSelectBenchmarkCase = (benchCase) => {
    setSelectedCaseId(benchCase.id);
    setCaseText(benchCase.text);
    if (benchCase.court) setCourtType(benchCase.court);
    if (benchCase.regime) {
      setLegalRegime(benchCase.regime.includes("IPC") ? "IPC + CrPC" : "BNS + BNSS");
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
        await new Promise((r) => setTimeout(r, 450));
        setStageProgress((prev) => ({ ...prev, [i]: "complete" }));
      }

      const response = await fetch(`${apiUrl}/api/lexigraph/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: caseText.trim(),
          court_type: courtType,
          legal_regime_override: legalRegime === "auto" ? null : legalRegime,
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
    } catch (err) {
      console.error("LexiGraph error:", err);
      setError(err.message || "Failed to connect to LexiGraph API on port 5001.");
      setCurrentStageIndex(-1);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickStatuteLookup = async (sec) => {
    const targetSec = sec || statuteQuery;
    if (!targetSec || !targetSec.trim()) return;

    setLoadingStatute(true);
    setStatuteResult(null);
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

    try {
      const response = await fetch(`${apiUrl}/api/lexigraph/statute/${encodeURIComponent(targetSec.trim())}`);
      const data = await response.json();
      if (response.ok && data.success) {
        setStatuteResult(data.data);
      } else {
        setStatuteResult({ error: data.message || `Section ${targetSec} not found in repository.` });
      }
    } catch (err) {
      setStatuteResult({ error: `Lookup error: ${err.message}` });
    } finally {
      setLoadingStatute(false);
    }
  };

  const copyToClipboard = (text, index) => {
    navigator.clipboard.writeText(typeof text === "string" ? text : JSON.stringify(text, null, 2));
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleExportToCourtroom = () => {
    // Store in localStorage so the CourtroomInterface can pick up the verified sections and arguments
    const exportData = {
      timestamp: new Date().toISOString(),
      case_text: caseText,
      verified_sections: summary?.verified_sections || [],
      bail_recommendation: summary?.bail_recommendation,
      precedents: summary?.precedents || [],
      source: "lexigraph_7stage",
    };
    try {
      localStorage.setItem("mootcourt_lexigraph_active_case", JSON.stringify(exportData));
    } catch (e) {
      console.warn("Storage warning:", e);
    }
    // Navigate to courtroom
    window.location.hash = "#/";
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#2C1810] font-body selection:bg-gold/30 relative">
      <StandardNavbar />

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* <div className="flex flex-wrap justify-end gap-3 mb-4">
          <button
            onClick={() => {
              setShowStatuteModal(true);
              if (!statuteResult) handleQuickStatuteLookup("498A");
            }}
            className="px-3.5 py-2 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-white border border-[#2C1810]/20 rounded-lg hover:border-[#D4AF37] hover:bg-[#D4AF37]/10 transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
          >
            <BookOpen className="w-3.5 h-3.5 text-[#8C5A3C]" />
            Statute Inspector
          </button>
          <button
            onClick={onSwitchToCypher || (() => { window.location.hash = "#/text2cypher"; })}
            className="px-3.5 py-2 text-xs font-mono font-bold uppercase tracking-wider text-[#2C1810] bg-white border border-[#2C1810]/20 rounded-lg hover:border-[#D4AF37] hover:bg-[#D4AF37]/10 transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
          >
            <Terminal className="w-3.5 h-3.5 text-[#8C5A3C]" />
            Cypher Query
          </button>
        </div> */}

        {/* Hero Banner with Benchmarks */}
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

            <div className="flex items-center gap-2 bg-[#FAF9F7] p-1.5 rounded-xl border border-[#2C1810]/15">
              <span className="text-[11px] font-mono text-[#5D4037] font-semibold px-2">Regime:</span>
              <button
                onClick={() => setLegalRegime("auto")}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all ${legalRegime === "auto" ? "bg-[#2C1810] text-[#FAF9F7]" : "text-[#5D4037] hover:bg-[#2C1810]/5"}`}
              >
                Auto-Detect
              </button>
              <button
                onClick={() => setLegalRegime("IPC + CrPC")}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all ${legalRegime === "IPC + CrPC" ? "bg-[#8C5A3C] text-[#FAF9F7]" : "text-[#5D4037] hover:bg-[#2C1810]/5"}`}
              >
                IPC + CrPC
              </button>
              <button
                onClick={() => setLegalRegime("BNS + BNSS")}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all ${legalRegime === "BNS + BNSS" ? "bg-[#C5A059] text-[#2C1810]" : "text-[#5D4037] hover:bg-[#2C1810]/5"}`}
              >
                BNS + BNSS
              </button>
            </div>
          </div>

          {/* Benchmark Case Selectors */}
          <div className="mb-5">
            <span className="text-[11px] font-mono uppercase tracking-wider font-bold text-[#8C5A3C] block mb-2.5">
              1-Click Benchmark Scenarios:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {SAMPLE_BENCHMARK_CASES.map((bc) => (
                <div
                  key={bc.id}
                  onClick={() => handleSelectBenchmarkCase(bc)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer text-left flex flex-col justify-between ${
                    selectedCaseId === bc.id
                      ? "bg-[#D4AF37]/15 border-[#D4AF37] shadow-sm"
                      : "bg-[#FAF9F7] border-[#2C1810]/15 hover:border-[#D4AF37]/50 hover:bg-white"
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[9px] font-mono font-bold uppercase px-2 py-0.5 rounded-full bg-[#2C1810]/10 text-[#2C1810]">
                        {bc.court}
                      </span>
                      <span className="text-[10px] font-mono text-[#8C5A3C] font-bold">
                        {bc.sections}
                      </span>
                    </div>
                    <h3 className="font-heading text-sm font-bold text-[#2C1810] line-clamp-1 mb-1">
                      {bc.title}
                    </h3>
                    <p className="text-[11px] text-[#5D4037]/80 line-clamp-2 leading-relaxed">
                      {bc.summary}
                    </p>
                  </div>
                  <div className="mt-2.5 pt-2 border-t border-[#2C1810]/10 flex items-center justify-between text-[10px] font-mono text-[#8C5A3C]">
                    <span>Load Case</span>
                    <ChevronRight className="w-3 h-3" />
                  </div>
                </div>
              ))}
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
              rows={4}
              value={caseText}
              onChange={(e) => {
                setCaseText(e.target.value);
                setSelectedCaseId(null);
              }}
              placeholder="Paste FIR description, allegations, applicant statements, or dates..."
              className="w-full p-4 bg-[#FAF9F7] border border-[#2C1810]/20 rounded-xl font-body text-sm text-[#2C1810] placeholder-[#5D4037]/50 focus:outline-none focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/20 transition-all shadow-inner"
              disabled={loading}
            />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5">
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
                </div>
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
        {result && summary && (
          <div className="space-y-6">
            {/* Executive Bail Verdict & Metrics Banner */}
            <div className="bg-white border border-[#D4AF37]/50 rounded-2xl p-6 md:p-8 shadow-sm">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-[#2C1810]/10">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-mono uppercase font-bold text-[#8C5A3C]">
                      Anticipatory Bail Intelligence Recommendation:
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-[#2C1810]/10 text-[#2C1810] rounded-full">
                      Regime: {summary.legal_regime}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <span
                      className={`px-4 py-1.5 rounded-full font-heading text-lg font-bold tracking-tight inline-flex items-center gap-2 ${
                        summary.bail_recommendation.toLowerCase().includes("grant")
                          ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                          : "bg-amber-100 text-amber-900 border border-amber-300"
                      }`}
                    >
                      <Gavel className="w-4 h-4" />
                      {summary.bail_recommendation}
                    </span>

                    <span className="text-xs font-mono px-3 py-1 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-lg text-[#5D4037]">
                      Risk Level: <strong className="text-[#2C1810]">{summary.risk_level}</strong>
                    </span>

                    <span className="text-xs font-mono px-3 py-1 bg-[#FAF9F7] border border-[#2C1810]/15 rounded-lg text-[#5D4037]">
                      Verified Sections: <strong className="text-[#2C1810]">{summary.total_sections_count}</strong>
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
                  Statutory Sections & Ingredients ({summary.verified_sections.length})
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
                  <BookOpen className="w-3.5 h-3.5" />
                  Supreme Court Precedents ({summary.precedents.length})
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
              <div className="space-y-4">
                {summary.precedents && summary.precedents.length > 0 ? (
                  summary.precedents.map((prec, idx) => (
                    <div
                      key={idx}
                      className="bg-white border border-[#D4AF37]/35 rounded-2xl p-6 shadow-xs"
                    >
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div>
                          <span className="text-[10px] font-mono font-bold uppercase bg-[#D4AF37]/20 text-[#8C5A3C] px-2.5 py-0.5 rounded-full mb-1.5 inline-block">
                            Binding Precedent #{idx + 1}
                          </span>
                          <h4 className="font-heading text-base font-bold text-[#2C1810]">
                            {prec.case_title || prec.title || prec.citation || "Supreme Court Ruling"}
                          </h4>
                          {prec.citation && (
                            <span className="text-xs font-mono text-[#8C5A3C] font-semibold">
                              {prec.citation}
                            </span>
                          )}
                        </div>
                      </div>

                      <p className="text-xs text-[#5D4037] leading-relaxed mt-2">
                        {prec.ratio_decidendi || prec.principles || prec.summary || "Establishes constitutional parameters governing discretionary grant of anticipatory bail."}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="bg-white border border-[#D4AF37]/30 rounded-2xl p-6 text-center">
                    <p className="text-xs font-mono text-[#5D4037]">
                      Refer to landmark authorities: <em>Gurbaksh Singh Sibbia (1980)</em> and <em>Sushila Aggarwal (2020)</em>.
                    </p>
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

      {/* QUICK STATUTE INSPECTOR MODAL */}
      {showStatuteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#2C1810]/60 backdrop-blur-md animate-fadeIn">
          <div
            className="relative w-full max-w-2xl bg-[#FAF9F7] border border-[#D4AF37] rounded-2xl shadow-2xl p-6 md:p-8 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowStatuteModal(false)}
              className="absolute top-5 right-5 p-2 text-[#5D4037] hover:text-[#2C1810] rounded-full hover:bg-[#2C1810]/5 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 mb-4">
              <BookOpen className="w-5 h-5 text-[#8C5A3C]" />
              <h3 className="font-heading text-xl font-bold text-[#2C1810]">
                Statute & Schedule Inspector
              </h3>
            </div>

            <p className="text-xs text-[#5D4037]/80 mb-5">
              Inspect official IPC / BNS section text, First Schedule cognizability, bailability, and cross-code equivalents with zero latency.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleQuickStatuteLookup();
              }}
              className="flex items-center gap-2 mb-5"
            >
              <input
                type="text"
                value={statuteQuery}
                onChange={(e) => setStatuteQuery(e.target.value)}
                placeholder="Enter Section Number (e.g. 498A, 85, 302, 103, 304B, 384, 308)..."
                className="flex-1 px-4 py-2.5 bg-white border border-[#2C1810]/20 rounded-xl text-xs font-mono text-[#2C1810] focus:outline-none focus:border-[#D4AF37]"
              />
              <button
                type="submit"
                disabled={loadingStatute}
                className="px-5 py-2.5 bg-[#2C1810] text-[#FAF9F7] rounded-xl font-mono text-xs uppercase font-bold hover:bg-[#8C5A3C] transition-all cursor-pointer"
              >
                {loadingStatute ? "Fetching..." : "Lookup"}
              </button>
            </form>

            {/* Quick Pills */}
            <div className="flex flex-wrap items-center gap-1.5 mb-5 text-[11px] font-mono">
              <span className="text-[#5D4037]">Quick:</span>
              {["498A", "85", "302", "103", "304B", "80", "384", "308", "452", "332"].map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setStatuteQuery(s);
                    handleQuickStatuteLookup(s);
                  }}
                  className="px-2 py-0.5 bg-white border border-[#2C1810]/15 hover:border-[#D4AF37] rounded-md text-[#8C5A3C] font-bold cursor-pointer"
                >
                  §{s}
                </button>
              ))}
            </div>

            {/* Results Display */}
            {statuteResult && (
              <div className="p-4 bg-white border border-[#2C1810]/15 rounded-xl max-h-80 overflow-y-auto">
                {statuteResult.error ? (
                  <p className="text-xs text-red-700 font-mono">{statuteResult.error}</p>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-heading text-base font-bold text-[#2C1810]">
                        Section {statuteResult.section}
                      </span>
                      {statuteResult.metadata?.punishment_maximum && (
                        <span className="text-xs font-mono text-[#8C5A3C] font-bold">
                          Max Punishment: {statuteResult.metadata.punishment_maximum}
                        </span>
                      )}
                    </div>

                    {statuteResult.metadata && Object.keys(statuteResult.metadata).length > 0 && (
                      <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                        <span className={`px-2 py-0.5 rounded-full ${statuteResult.metadata.bailable ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>
                          {statuteResult.metadata.bailable ? "Bailable" : "Non-Bailable"}
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                          {statuteResult.metadata.cognizable ? "Cognizable" : "Non-Cognizable"}
                        </span>
                        {statuteResult.metadata.chapter_number && (
                          <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-800">
                            Chapter {statuteResult.metadata.chapter_number}
                          </span>
                        )}
                      </div>
                    )}

                    {statuteResult.statute_text?.section_title && (
                      <h4 className="font-heading text-sm font-bold text-[#2C1810]">
                        {statuteResult.statute_text.section_title}
                      </h4>
                    )}

                    {statuteResult.statute_text?.full_text && (
                      <p className="text-xs text-[#5D4037] leading-relaxed whitespace-pre-line border-t border-black/5 pt-2">
                        {statuteResult.statute_text.full_text}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
