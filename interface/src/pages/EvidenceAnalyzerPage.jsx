import { useState, useEffect, useRef, useMemo } from "react";
import {
  FileText,
  Upload,
  Search,
  Shield,
  Check,
  AlertTriangle,
  Scale,
  Users,
  MapPin,
  Calendar,
  Briefcase,
  Layers,
  ArrowLeft,
  History,
  RefreshCw,
  X,
} from "lucide-react";
import ForceGraph2D from "react-force-graph-2d";
import StandardNavbar from "../components/StandardNavbar";
import { db } from "../firebase";
import { collection, getDocs, doc, getDoc } from "firebase/firestore";

// ─── Progress Steps ──────────────────────────────────────────────
const STEPS = [
  { id: "upload", label: "Upload Document", icon: Upload },
  { id: "ocr", label: "OCR Extraction", icon: Search },
  { id: "analysis", label: "AI Analysis", icon: Scale },
  { id: "results", label: "Structured Output", icon: Layers },
];

export default function EvidenceAnalyzerPage({ onBack }) {
  const [selectedCase, setSelectedCase] = useState(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [ocrProgress, setOcrProgress] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [displayedText, setDisplayedText] = useState("");
  const [showFacts, setShowFacts] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState(null);
  const [showHistory, setShowHistory] = useState(false);

  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

  const normalizeSessionPayload = (payload, fallbackSessionId = null) => {
    const rawText = payload?.rawText || payload?.raw_text || "";
    let facts = payload?.facts || null;
    const timeline = payload?.timeline || [];
    const graph = payload?.graph || { nodes: [], edges: [] };

    let description = "Stored evidence analysis session";
    if (Array.isArray(facts)) {
      const summaryText = facts.map(f => (typeof f === "object" ? f.text : f)).filter(Boolean).join(" ");
      description = facts[0]?.text || summaryText.slice(0, 150) || description;
      facts = {
        incident: {
          summary: summaryText.slice(0, 500) || "Extracted fact statements from document.",
          date: facts.find(f => f.date)?.date || "",
          time: "",
          place: ""
        },
        who: {
          complainant: "Extracted from record",
          accused: [],
          victims: []
        },
        property: {
          vehicles: [],
          cash: null,
          gold: null,
          documents: null,
          other_property: [],
          estimated_loss: null
        },
        sections: [],
        raw_facts: facts
      };
    } else if (facts?.incident?.summary) {
      description = facts.incident.summary;
    }

    return {
      id: payload?.session_id || payload?.sessionId || fallbackSessionId || `session_${Date.now()}`,
      filename: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
      label: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
      description,
      rawText,
      facts,
      timeline,
      graph,
    };
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      let items = [];

      // 1. First attempt: fetch from configured API (local or remote)
      const candidateApiUrls = [apiUrl];
      if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
        if (!candidateApiUrls.includes("http://localhost:5001")) candidateApiUrls.push("http://localhost:5001");
      }

      for (const url of candidateApiUrls) {
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 4000);
          const response = await fetch(`${url}/api/evidence/history?limit=25`, { signal: controller.signal });
          clearTimeout(timeoutId);
          if (response.ok) {
            const res = await response.json();
            if (res.success && Array.isArray(res.data) && res.data.length > 0) {
              items = res.data;
              break;
            }
          }
        } catch {
          // Continue to next fallback
        }
      }

      // 2. Direct Firestore fallback (if backend returned 0 items, is sleeping, or unreachable)
      if (items.length === 0 && db) {
        try {
          for (const colName of ["document_store", "evidence", "evidence_history", "ocr_history", "documents"]) {
            const snap = await getDocs(collection(db, colName));
            if (!snap.empty) {
              const firestoreItems = [];
              snap.forEach((docSnap) => {
                const data = docSnap.data() || {};
                const facts = data.facts;
                let incidentSummary = "";
                let incidentDate = "";
                let incidentTime = "";
                let incidentPlace = "";

                if (facts && typeof facts === "object") {
                  if (facts.incident && typeof facts.incident === "object") {
                    incidentSummary = facts.incident.summary || "";
                    incidentDate = facts.incident.date || "";
                    incidentTime = facts.incident.time || "";
                    incidentPlace = facts.incident.place || "";
                  } else if (typeof facts.incident === "string") {
                    incidentSummary = facts.incident;
                  }
                } else if (Array.isArray(facts)) {
                  for (const f of facts) {
                    if (f && typeof f === "object" && f.text) {
                      incidentSummary = f.text.slice(0, 180);
                      break;
                    }
                  }
                }
                if (!incidentSummary && data.description) incidentSummary = String(data.description);
                if (!incidentSummary && data.raw_text) incidentSummary = String(data.raw_text).slice(0, 160) + "...";

                firestoreItems.push({
                  session_id: data.session_id || docSnap.id,
                  created_at: String(data.created_at || ""),
                  filename: data.filename || data.source_filename || docSnap.id,
                  incident_summary: incidentSummary,
                  incident_date: incidentDate,
                  incident_time: incidentTime,
                  incident_place: incidentPlace,
                  timeline_count: Array.isArray(data.timeline) ? data.timeline.length : 0,
                  node_count: Array.isArray(data.graph?.nodes) ? data.graph.nodes.length : 0,
                  edge_count: Array.isArray(data.graph?.edges) ? data.graph.edges.length : 0,
                });
              });
              if (firestoreItems.length > 0) {
                items = firestoreItems;
                break;
              }
            }
          }
        } catch (dbErr) {
          console.warn("[EvidenceAnalyzer] Direct Firestore fetch error:", dbErr);
        }
      }

      setHistoryItems(items);
    } catch (err) {
      setHistoryError(err.message || "Failed to load history.");
    } finally {
      setHistoryLoading(false);
    }
  };

  const openHistorySession = async (sessionId) => {
    setHistoryError(null);
    setSelectedHistoryId(sessionId);
    try {
      let sessionData = null;

      // 1. Try candidate API URLs
      const candidateApiUrls = [apiUrl];
      if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
        if (!candidateApiUrls.includes("http://localhost:5001")) candidateApiUrls.push("http://localhost:5001");
      }

      for (const url of candidateApiUrls) {
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 4000);
          const response = await fetch(`${url}/api/evidence/history/${sessionId}`, { signal: controller.signal });
          clearTimeout(timeoutId);
          if (response.ok) {
            const res = await response.json();
            if (res.success && res.data) {
              sessionData = res.data;
              break;
            }
          }
        } catch {
          // Continue to next fallback
        }
      }

      // 2. Direct Firestore lookup
      if (!sessionData && db) {
        for (const colName of ["document_store", "evidence", "evidence_history", "ocr_history", "documents"]) {
          try {
            const docSnap = await getDoc(doc(db, colName, sessionId));
            if (docSnap.exists()) {
              sessionData = docSnap.data();
              break;
            }
          } catch {
            // Continue to next collection
          }
        }
      }

      if (!sessionData) {
        throw new Error(`Evidence session '${sessionId}' not found.`);
      }

      const sessionCase = normalizeSessionPayload(sessionData, sessionId);
      setSelectedCase(sessionCase);
      setOcrProgress(100);
      setAnalysisProgress(100);
      setCurrentStep(3);
      setShowFacts(true);
      setShowHistory(false);
    } catch (err) {
      setHistoryError(err.message || "Failed to load session.");
    } finally {
      setSelectedHistoryId(null);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setSelectedCase({
      id: `uploaded_${Date.now()}`,
      filename: file.name,
      label: `Uploaded — ${file.name}`,
      description: "Processing case document via backend intelligence pipeline...",
      rawText: "",
      facts: null,
      timeline: [],
      graph: { nodes: [], edges: [] },
    });
    setCurrentStep(1);
    setOcrProgress(0);
    setAnalysisProgress(0);
    setDisplayedText("");
    setShowFacts(false);
    setSelectedHistoryId(null);

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.open("POST", `${apiUrl}/api/evidence/analyze`, true);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100);
        setOcrProgress(Math.min(90, Math.round(percentComplete * 0.9)));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.success) {
            setOcrProgress(100);
            const { rawText, facts, timeline = [], graph = { nodes: [], edges: [] } } = res.data;
            
            setDisplayedText(rawText);
            setCurrentStep(2);
            
            let prog = 0;
            const interval = setInterval(() => {
              prog += Math.random() * 15 + 10;
              if (prog >= 100) {
                prog = 100;
                clearInterval(interval);
                setAnalysisProgress(100);
                setTimeout(() => {
                  setSelectedCase((prev) => ({
                    ...prev,
                    id: res.data.sessionId || prev?.id,
                    rawText,
                    facts,
                    timeline,
                    graph,
                  }));
                  setCurrentStep(3);
                  setShowFacts(true);
                  fetchHistory();
                }, 600);
              } else {
                setAnalysisProgress(Math.min(prog, 100));
              }
            }, 150);
          } else {
            setError(res.message || "Analysis failed.");
            setCurrentStep(0);
            setSelectedCase(null);
          }
        } catch (err) {
          setError("Failed to parse API response.");
          setCurrentStep(0);
          setSelectedCase(null);
        }
      } else {
        try {
          const res = JSON.parse(xhr.responseText);
          setError(res.message || `Error ${xhr.status}: ${xhr.statusText}`);
        } catch (err) {
          setError(`Server returned status code ${xhr.status}`);
        }
        setCurrentStep(0);
        setSelectedCase(null);
      }
    };

    xhr.onerror = () => {
      setError("Network connection failed. Make sure the backend server is running.");
      setCurrentStep(0);
      setSelectedCase(null);
    };

    xhr.send(formData);
  };

  const facts = selectedCase?.facts;
  const timeline = selectedCase?.timeline || [];
  const graph = selectedCase?.graph || { nodes: [], edges: [] };

  return (
    <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810]">
      <StandardNavbar onBack={onBack} subtitle="Demo Mode" title="Evidence Analyzer" />

      <div className="max-w-[1400px] mx-auto px-6 pt-4 flex justify-end">
        <button
          onClick={() => {
            setShowHistory(true);
            fetchHistory();
          }}
          className="flex items-center gap-2 px-4 py-2.5 text-xs font-mono font-bold  tracking-wider text-[#2C1810] bg-white border border-[#2C1810]/15 rounded-xl hover:border-[#D4AF37] hover:bg-[#D4AF37]/5 transition-colors shadow-sm"
        >
          <History className="w-4 h-4 text-[#D4AF37]" />
          History 
        </button>
      </div>

      <div className="pt-6 max-w-[1400px] mx-auto px-6 pb-24">
        {/* ─── Progress Steps Bar ────────────────────────────────── */}
        <div className="flex items-center justify-center gap-2 md:gap-4 py-8">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const isActive = i === currentStep;
            const isDone = i < currentStep;
            return (
              <div key={step.id} className="flex items-center gap-2 md:gap-4">
                <div className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-all duration-500 ${
                  isDone
                    ? "bg-[#2C1810] text-[#FAF8F5] border-[#D4AF37]"
                    : isActive
                    ? "bg-white text-[#2C1810] border-[#D4AF37] shadow-md"
                    : "bg-transparent text-[#2C1810]/30 border-[#2C1810]/10"
                }`}>
                  {isDone ? (
                    <Check size={14} strokeWidth={3} />
                  ) : (
                    <Icon size={14} strokeWidth={isActive ? 2.5 : 1.5} />
                  )}
                  <span className="text-[10px] font-bold uppercase tracking-wider hidden md:inline">
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`w-8 md:w-16 h-px transition-colors duration-500 ${
                    i < currentStep ? "bg-[#D4AF37]" : "bg-[#2C1810]/10"
                  }`} />
                )}
              </div>
            );
          })}
        </div>

        {/* ─── Step 0: File Selection ────────────────────────────── */}
        {currentStep === 0 && (
          <div className="max-w-3xl mx-auto">
            <div className="text-center mb-12">
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#D4AF37] font-bold mb-3 block">
                Document Intelligence Pipeline
              </span>
              <h1 className="font-heading text-3xl md:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
                Evidence Analyzer
              </h1>
              <p className="font-body text-sm md:text-base text-[#5D4037] max-w-xl mx-auto leading-relaxed">
                Upload an FIR, charge sheet, or legal document. The AI pipeline extracts structured facts
                using OCR and multi-pass language model analysis.
              </p>
            </div>

            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 text-red-800 animate-[fadeIn_0.3s_ease-out]">
                <AlertTriangle className="text-red-600 shrink-0 mt-0.5" size={18} />
                <div className="text-xs">
                  <p className="font-bold">Error Processing Document</p>
                  <p className="mt-0.5 opacity-90">{error}</p>
                </div>
              </div>
            )}

            <div 
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              className="border-2 border-dashed border-[#D4AF37]/40 rounded-xl p-8 md:p-12 bg-white/60 hover:bg-white hover:border-[#D4AF37] transition-all mb-8 text-center cursor-pointer group"
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileUpload}
                accept="application/pdf,image/*"
              />
              <Upload className="mx-auto mb-4 text-[#D4AF37] group-hover:scale-110 transition-transform" size={36} strokeWidth={1.5} />
              <p className="font-heading text-lg font-bold text-[#2C1810] mb-1">
                Drop your document here
              </p>
              <p className="text-xs text-[#5D4037]">
                Supports PDF, PNG, JPG, TIFF — up to 50MB
              </p>
            </div>

          </div>
        )}

        {/* ─── Steps 1-3: Processing & Results ───────────────────── */}
        {currentStep > 0 && selectedCase && (
          <div className="flex flex-col lg:flex-row gap-6 h-[750px] relative overflow-hidden">
            
            {/* MAIN CONTENT AREA */}
            <div className="flex-1 flex flex-col min-w-0 transition-all duration-300">
              
              {/* Waiting for OCR */}
              {currentStep === 1 && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-full">
                  <Search className="text-[#D4AF37] mb-4 animate-pulse" size={36} strokeWidth={1.5} />
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Extracting Text
                  </h3>
                  <p className="text-xs text-[#5D4037] text-center max-w-sm">
                    Processing document pages. OCR progress is tracked here while the analysis runs.
                  </p>
                </div>
              )}

              {/* Analysis in progress */}
              {currentStep === 2 && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-full">
                  <div className="w-20 h-20 rounded-full border-4 border-[#D4AF37]/30 border-t-[#D4AF37] animate-spin mb-8" />
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Analyzing Document
                  </h3>
                  <p className="text-xs text-[#5D4037] mb-6 text-center max-w-sm">
                    Multi-pass LLM extraction in progress. Identifying parties, incident details, timeline events, and relationship graphs...
                  </p>
                  <div className="w-full max-w-xs">
                    <div className="h-2 bg-[#2C1810]/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] rounded-full transition-all duration-200"
                        style={{ width: `${analysisProgress}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Results Dashboard */}
              {currentStep === 3 && showFacts && facts && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden h-full flex flex-col relative shadow-sm">
                  
                  {/* Header */}
                  <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between z-10">
                    <div className="flex items-center gap-2">
                      <Shield size={14} />
                      <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
                        Intelligence Dashboard
                      </span>
                    </div>
                    <span className="font-mono text-[9px] text-green-400 flex items-center gap-1 hidden sm:flex">
                      <Check size={10} strokeWidth={3} /> Verified Extraction
                    </span>
                  </div>

                  {/* Scrollable Body */}
                  <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-[#FAF8F5]/30">
                    <div className="space-y-6">
                      {/* Extracted Entities Cards */}
                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
                        <FactCard compact icon={<Users size={16} />} title="Parties Identified" isOpen={true} className="lg:col-span-1">
                          <FactRow compact label="Complainant" value={facts.who?.complainant} />
                          <FactRow compact highlight label="Accused" value={facts.who?.accused?.join(", ")} />
                          <FactRow compact label="Victims" value={facts.who?.victims?.join(", ")} />
                        </FactCard>
                        
                        <FactCard icon={<Briefcase size={16} />} title="Property & Loss" isOpen={true} className="lg:col-span-1">
                          {facts.property?.vehicles?.length > 0 ? (
                            facts.property.vehicles.map((v, i) => (
                              <div key={i} className="mb-4 last:mb-0 rounded-lg border border-[#2C1810]/10 bg-[#FAF8F5]/60 p-3">
                                <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C] mb-2">
                                  Vehicle {i + 1}
                                </p>
                                <FactRow label="Type" value={v?.type} />
                                <FactRow label="Make / Model" value={v?.make_model} />
                                <FactRow highlight label="Registration No." value={v?.registration_no} />
                                <FactRow label="Engine / Chassis No." value={v?.engine_chassis_no} />
                                <FactRow label="Estimated Value" value={v?.estimated_value} />
                              </div>
                            ))
                          ) : (
                            <p className="text-xs text-[#5D4037] mb-3">No vehicle details extracted.</p>
                          )}
                          <FactRow label="Cash" value={facts.property?.cash} />
                          <FactRow label="Gold" value={facts.property?.gold} />
                          <FactRow label="Documents" value={facts.property?.documents} />
                          <FactRow label="Other Property" value={facts.property?.other_property?.join(", ")} />
                          <FactRow highlight label="Est. Loss" value={facts.property?.estimated_loss} />
                        </FactCard>

                        <FactCard icon={<AlertTriangle size={16} />} title="Incident Summary" isOpen={true} className="lg:col-span-1">
                          <FactRow label="Details" value={facts.incident?.summary} />
                          <FactRow label="Date" value={facts.incident?.date} />
                          <FactRow label="Time" value={facts.incident?.time} />
                          <FactRow label="Location" value={facts.incident?.place} />
                          <FactRow highlight label="Applicable IPC" value={facts.sections?.join(", ")} />
                        </FactCard>
                      </div>

                      {/* Extracted Facts List if present */}
                      {facts?.raw_facts && facts.raw_facts.length > 0 && (
                        <div>
                          <h3 className="font-heading font-bold text-lg text-[#2C1810] border-b border-[#2C1810]/10 pb-2 mb-4 flex items-center gap-2">
                            <FileText className="text-[#D4AF37]" size={18} /> Extracted Fact Statements ({facts.raw_facts.length})
                          </h3>
                          <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
                            {facts.raw_facts.map((rf, idx) => (
                              <div key={rf.id || idx} className="p-3 bg-white rounded-lg border border-[#2C1810]/10 text-xs">
                                <span className="font-mono font-bold text-[#8C5A3C] mr-2">[{rf.id || idx + 1}]</span>
                                {formatFactValue(rf?.text ?? rf)}
                                {rf?.source && (
                                  <span className="ml-2 text-[#8C5A3C]">Source: {formatFactValue(rf.source)}</span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Visual Timeline Section */}
                      <div>
                        <h3 className="font-heading font-bold text-lg text-[#2C1810] border-b border-[#2C1810]/10 pb-2 mb-6 flex items-center gap-2">
                          <Calendar className="text-[#D4AF37]" size={18} /> Case Timeline
                        </h3>
                        <VisualTimeline timeline={timeline} />
                      </div>

                      {/* Interactive Graph Section */}
                      <div>
                        <h3 className="font-heading font-bold text-lg text-[#2C1810] border-b border-[#2C1810]/10 pb-2 mb-6 flex items-center gap-2">
                          <Layers className="text-[#D4AF37]" size={18} /> Entity Graph
                        </h3>
                        <div className="border border-[#2C1810]/10 rounded-xl bg-white h-[450px] overflow-hidden shadow-inner">
                          <NetworkGraph graph={graph} />
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Reset Button Footer */}
                  <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-3 flex items-center justify-between">
                    <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
                      Processing Complete
                    </span>
                    <button
                      onClick={() => {
                        setSelectedCase(null);
                        setCurrentStep(0);
                      }}
                      className="text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
                    >
                      Analyze Another Case
                      <ArrowLeft className="rotate-180" size={12} />
                    </button>
                  </div>
                </div>
              )}
            </div>

          </div>
        )}
      </div>

      {showHistory && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-[#2C1810]/60 backdrop-blur-sm"
          onClick={() => setShowHistory(false)}
        >
          <aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-history-title"
            className="flex h-full w-full max-w-xl flex-col overflow-hidden border-l border-[#D4AF37]/50 bg-[#FAF9F7] p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#2C1810]/10 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <History className="h-5 w-5 text-[#D4AF37]" />
                  <h2 id="evidence-history-title" className="font-heading text-lg font-bold text-[#2C1810]">
                    OCR History
                  </h2>
                </div>
                <p className="mt-1 text-xs font-mono font-semibold text-[#8C5A3C]">
                  {historyItems.length} saved analysis sessions
                </p>
              </div>
              <button
                onClick={() => setShowHistory(false)}
                aria-label="Close history"
                className="rounded-full p-2 text-[#5D4037] transition-colors hover:bg-[#2C1810]/5 hover:text-[#2C1810]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="my-4 flex items-center justify-between gap-3">
              <p className="text-xs text-[#5D4037]">
                Open an analyzed document to review its OCR text, timeline, and graph.
              </p>
              <button
                onClick={fetchHistory}
                disabled={historyLoading}
                className="flex shrink-0 items-center gap-1.5 rounded-xl border border-[#2C1810]/15 bg-white px-3 py-2 text-xs font-mono font-bold text-[#2C1810] transition-colors hover:border-[#D4AF37] disabled:opacity-60"
              >
                <RefreshCw className={`h-3.5 w-3.5 text-[#D4AF37] ${historyLoading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>

            {historyError && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {historyError}
              </div>
            )}

            <div className="flex-1 space-y-3 overflow-y-auto pr-1">
              {historyLoading && historyItems.length === 0 && (
                <div className="py-12 text-center text-xs font-mono text-[#5D4037]">
                  <RefreshCw className="mb-2 inline-block h-5 w-5 animate-spin text-[#D4AF37]" />
                  <p>Loading OCR history...</p>
                </div>
              )}
              {!historyLoading && historyItems.length === 0 && !historyError && (
                <div className="rounded-xl border border-dashed border-[#2C1810]/15 bg-white p-6 py-12 text-center text-xs text-[#5D4037]">
                  No saved OCR sessions yet.
                </div>
              )}
              {historyItems.map((item) => (
                <button
                  key={item.session_id}
                  onClick={() => openHistorySession(item.session_id)}
                  disabled={selectedHistoryId === item.session_id}
                  className={`w-full rounded-xl border p-4 text-left transition-all disabled:cursor-wait disabled:opacity-70 ${
                    selectedCase?.id === item.session_id
                      ? "border-[#D4AF37] bg-[#FFF8E1]"
                      : "border-[#2C1810]/10 bg-white hover:border-[#D4AF37]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C]">
                          {item.session_id}
                        </span>
                        <span className="rounded-md bg-[#2C1810] px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-wider text-[#FAF8F5]">
                          {item.timeline_count || 0} events
                        </span>
                      </div>
                      <p className="mt-2 truncate text-[12px] font-semibold text-[#2C1810]">
                        {item.incident_summary
                          ? formatFactValue(item.incident_summary)
                          : "No incident summary available"}
                      </p>
                      <p className="mt-1 text-[11px] text-[#5D4037]">
                        {item.incident_date ? formatFactValue(item.incident_date) : "No date"}
                        {item.incident_time ? ` • ${formatFactValue(item.incident_time)}` : ""}
                        {item.incident_place ? ` • ${formatFactValue(item.incident_place)}` : ""}
                      </p>
                      {(item.vehicle_count || item.vehicle_summary) && (
                        <p className="mt-1 text-[10px] text-[#8C5A3C]">
                          {item.vehicle_count ? `${item.vehicle_count} vehicle${item.vehicle_count === 1 ? "" : "s"}` : "Vehicle details"}
                          {item.vehicle_summary ? ` • ${formatFactValue(item.vehicle_summary)}` : ""}
                        </p>
                      )}
                    </div>
                    <span className="whitespace-nowrap font-mono text-[10px] text-[#8C5A3C]">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown time"}
                    </span>
                  </div>
                  {selectedHistoryId === item.session_id && (
                    <span className="mt-3 inline-flex items-center gap-2 text-[10px] font-mono font-bold uppercase text-[#8C5A3C]">
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      Loading session...
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-3 border-t border-[#2C1810]/10 pt-4">
              <span className="text-[11px] font-mono text-[#5D4037]">
                Select a session to reopen its analysis.
              </span>
              <button
                onClick={() => setShowHistory(false)}
                className="rounded-lg bg-[#2C1810]/5 px-4 py-1.5 text-xs font-mono font-bold uppercase text-[#2C1810] transition-colors hover:bg-[#2C1810]/10"
              >
                Close
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

// ─── Visual Timeline Component ─────────────────────────────
function VisualTimeline({ timeline }) {
  if (!timeline || timeline.length === 0) return <p className="text-sm text-gray-500">No timeline data.</p>;

  return (
    <div className="relative border-l-2 border-[#D4AF37]/50 ml-4 space-y-8 py-2">
      {timeline.map((event, idx) => (
        <div key={event.event_id || idx} className="relative pl-8 pr-4 group">
          {/* Node Dot */}
          <div className="absolute -left-[9px] top-1.5 w-4 h-4 rounded-full bg-white border-2 border-[#D4AF37] group-hover:bg-[#D4AF37] transition-colors" />
          
          <div className="bg-white border border-[#2C1810]/10 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <span className="px-2 py-1 bg-[#FAF8F5] text-[#8C5A3C] font-mono text-[10px] font-bold border border-[#2C1810]/5 rounded">
                {formatFactValue(event.date)} {event.time && `• ${formatFactValue(event.time)}`}
              </span>
              <span className="px-2 py-1 rounded-md bg-[#FFF8E1] text-[#8C5A3C] font-mono text-[9px] font-bold uppercase tracking-wider">
                {formatFactValue(event.event_type).replace(/_/g, " ")}
              </span>
            </div>
            
            <p className="text-[13px] text-[#2C1810] leading-relaxed mb-3">
              {formatFactValue(event.description)}
            </p>
            
            {/* Metadata Tags */}
            <div className="flex flex-wrap gap-2">
              {event.actors?.length > 0 && (
                <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
                  <Users size={10} /> {formatFactValue(event.actors)}
                </div>
              )}
              {event.location && (
                <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
                  <MapPin size={10} /> {formatFactValue(event.location)}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Neo4j-Style Interactive Graph ─────────────────────────
function NetworkGraph({ graph }) {
  const fgRef = useRef();

  // Transform backend schema into react-force-graph expected schema
  const graphData = useMemo(() => {
    if (!graph.nodes) return { nodes: [], links: [] };
    
    const mappedNodes = graph.nodes.map(n => ({
      id: n.id,
      label: n.label,
      name: n.properties?.name || n.properties?.registration_no || n.properties?.summary || n.id,
      val: n.label === 'Case' ? 4 : n.label === 'Person' ? 3 : 2,
      color: 
        n.label === 'Case' ? '#D4AF37' : 
        n.label === 'Person' ? '#8C5A3C' : 
        n.label === 'Location' ? '#4A5568' : '#718096'
    }));

    const mappedLinks = graph.edges.map(e => ({
      source: e.source,
      target: e.target,
      label: e.type ? e.type.replace(/_/g, ' ') : ''
    }));

    return { nodes: mappedNodes, links: mappedLinks };
  }, [graph]);

  useEffect(() => {
    if (fgRef.current) {
      // Significantly increase link distance and node repulsion to uncluster complex networks
      fgRef.current.d3Force('charge').strength(-500); 
      fgRef.current.d3Force('link').distance(120);
      
      setTimeout(() => {
        fgRef.current.zoomToFit(400, 50);
      }, 800);
    }
  }, [graphData]);

  if (!graphData.nodes.length) return <p className="p-4 text-sm text-gray-500">No graph data.</p>;

  return (
    <div className="w-full h-full relative cursor-move">
      <ForceGraph2D 
        ref={fgRef}
        graphData={graphData} 
        nodeLabel="name" 
        nodeColor="color" 
        nodeRelSize={5}
        linkColor={() => '#CBD5E0'}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.15}
        width={900} 
        height={450}
        backgroundColor="#FFFFFF"
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.name;
          const fontSize = 12 / globalScale;
          ctx.font = `${fontSize}px Sans-Serif`;
          
          // Draw Node
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.val * 2.5, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.color;
          ctx.fill();
          ctx.strokeStyle = '#fff';
          ctx.lineWidth = 1.5 / globalScale;
          ctx.stroke();

          // Draw Text Label
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillStyle = '#2C1810';
          
          // Truncate long labels
          const displayLabel = label.length > 20 ? label.substring(0, 20) + '...' : label;
          ctx.fillText(displayLabel, node.x, node.y + (node.val * 2.5) + 2);
        }}
        linkCanvasObjectMode={() => 'after'}
        linkCanvasObject={(link, ctx, globalScale) => {
          // Ensure valid coordinates
          if (typeof link.source.x !== 'number' || typeof link.target.x !== 'number') return;
          
          const MAX_FONT_SIZE = 10 / globalScale;
          const start = link.source;
          const end = link.target;

          // Calculate center point for text
          const textPos = {
            x: start.x + (end.x - start.x) / 2,
            y: start.y + (end.y - start.y) / 2
          };

          const relLink = { x: end.x - start.x, y: end.y - start.y };
          
          // Calculate text rotation angle to align with the edge
          let textAngle = Math.atan2(relLink.y, relLink.x);
          if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
          if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

          const label = link.label;
          if (!label) return;

          const fontSize = Math.min(MAX_FONT_SIZE, 12 / globalScale);
          ctx.font = `${fontSize}px Sans-Serif`;
          
          const textWidth = ctx.measureText(label).width;
          const bgWidth = textWidth + (4 / globalScale);
          const bgHeight = fontSize + (4 / globalScale);

          ctx.save();
          ctx.translate(textPos.x, textPos.y);
          ctx.rotate(textAngle);

          // Draw background to mask line beneath text
          ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
          ctx.fillRect(-bgWidth / 2, -bgHeight / 2, bgWidth, bgHeight);

          // Draw relationship label
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = '#8C5A3C';
          ctx.fillText(label, 0, 0);
          ctx.restore();
        }}
      />
      <div className="absolute bottom-3 left-3 bg-white/80 px-2 py-1 rounded text-[10px] font-mono text-gray-500 pointer-events-none">
        Scroll to zoom, drag to pan
      </div>
    </div>
  );
}

// ─── Fact Cards ──────────────────────────────────────────────────
function FactCard({ title, icon, isOpen, children, compact = false, className = "" }) {
  if (!isOpen) return null;
  return (
    <div className={`border border-[#2C1810]/10 rounded-lg overflow-hidden bg-white shadow-sm ${className}`}>
      <div className={`flex items-center gap-2.5 bg-[#FAF8F5] border-b border-[#2C1810]/5 ${compact ? "px-3 py-2" : "px-4 py-3"}`}>
        <span className="text-[#D4AF37]">{icon}</span>
        <span className={`font-heading font-bold text-[#2C1810] ${compact ? "text-[12px]" : "text-sm"}`}>{title}</span>
      </div>
      <div className={`${compact ? "p-3 space-y-2" : "p-4 space-y-3"}`}>{children}</div>
    </div>
  );
}

function FactRow({ label, value, highlight, compact = false }) {
  if (!value) return null;
  return (
    <div className={`flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4 ${compact ? "sm:gap-3" : ""}`}>
      <span className={`font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold shrink-0 pt-0.5 ${compact ? "sm:w-24" : "sm:w-28"}`}>
        {label}
      </span>
      <span className={`leading-relaxed ${compact ? "text-[11px]" : "text-[12px]"} ${highlight ? "text-[#991B1B] font-semibold" : "text-[#2C1810]"}`}>
        {formatFactValue(value)}
      </span>
    </div>
  );
}

function formatFactValue(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(formatFactValue).filter(Boolean).join(", ");
  if (typeof value === "object") {
    if (value.text != null) return formatFactValue(value.text);
    return Object.entries(value)
      .map(([key, entry]) => `${key}: ${formatFactValue(entry)}`)
      .join(" • ");
  }
  return String(value);
}
