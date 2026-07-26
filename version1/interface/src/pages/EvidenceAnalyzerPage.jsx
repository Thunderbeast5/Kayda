import { useState, useEffect, useRef } from "react";
import { sampleCases } from "../data/mockEvidenceData";
import {
  FileText,
  Upload,
  Search,
  Shield,
  ChevronDown,
  ArrowLeft,
  Check,
  AlertTriangle,
  Scale,
  Users,
  MapPin,
  Calendar,
  Clock,
  Briefcase,
  Layers,
} from "lucide-react";
import logo from "../assets/logo1.svg";

// ─── Progress Steps ──────────────────────────────────────────────
const STEPS = [
  { id: "upload", label: "Upload Document", icon: Upload },
  { id: "ocr", label: "OCR Extraction", icon: Search },
  { id: "analysis", label: "AI Analysis", icon: Scale },
  { id: "results", label: "Structured Output", icon: Layers },
];

export default function EvidenceAnalyzerPage({ onBack }) {
  const [selectedCase, setSelectedCase] = useState(null);
  const [currentStep, setCurrentStep] = useState(0); // 0=upload, 1=ocr, 2=analysis, 3=results
  const [ocrProgress, setOcrProgress] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [displayedText, setDisplayedText] = useState("");
  const [showFacts, setShowFacts] = useState(false);
  const [expandedSection, setExpandedSection] = useState("who");
  const textRef = useRef(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

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
    });
    setCurrentStep(1);
    setOcrProgress(0);
    setAnalysisProgress(0);
    setDisplayedText("");
    setShowFacts(false);

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    xhr.open("POST", `${apiUrl}/api/evidence/analyze`, true);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100);
        // Show progress up to 90% during upload phase
        setOcrProgress(Math.min(90, Math.round(percentComplete * 0.9)));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.success) {
            setOcrProgress(100);
            const { rawText, facts } = res.data;
            
            // Set raw OCR output text
            setDisplayedText(rawText);
            
            // Move to Analysis phase
            setCurrentStep(2);
            
            // Fast visual progression for the analysis progress bar (feels responsive and satisfying)
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
                    rawText,
                    facts,
                  }));
                  setCurrentStep(3);
                  setShowFacts(true);
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

  // ─── Simulate the pipeline when a case is selected ─────────────
  const startAnalysis = (caseData) => {
    setSelectedCase(caseData);
    setCurrentStep(1);
    setOcrProgress(0);
    setAnalysisProgress(0);
    setDisplayedText("");
    setShowFacts(false);

    // Step 1: OCR extraction (typewriter)
    let charIdx = 0;
    const rawText = caseData.rawText;
    const charsPerTick = 12;

    const ocrInterval = setInterval(() => {
      charIdx += charsPerTick;
      if (charIdx >= rawText.length) {
        charIdx = rawText.length;
        clearInterval(ocrInterval);
        setOcrProgress(100);
        setDisplayedText(rawText);

        // Move to analysis step after a short pause
        setTimeout(() => {
          setCurrentStep(2);
          // Step 2: Analysis progress bar
          let prog = 0;
          const analysisInterval = setInterval(() => {
            prog += Math.random() * 8 + 2;
            if (prog >= 100) {
              prog = 100;
              clearInterval(analysisInterval);
              setAnalysisProgress(100);
              setTimeout(() => {
                setCurrentStep(3);
                setShowFacts(true);
              }, 600);
            }
            setAnalysisProgress(Math.min(prog, 100));
          }, 120);
        }, 800);
      }
      setDisplayedText(rawText.slice(0, charIdx));
      setOcrProgress(Math.round((charIdx / rawText.length) * 100));
    }, 18);
  };

  // Auto-scroll the OCR text panel
  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight;
    }
  }, [displayedText]);

  const facts = selectedCase?.facts;

  return (
    <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810]">
      {/* ─── Top Bar ─────────────────────────────────────────────── */}
      <header className="fixed top-0 inset-x-0 z-50 bg-[#FAF8F5]/90 backdrop-blur-md border-b border-[#2C1810]/10">
        <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-widest text-[#8C5A3C] hover:text-[#2C1810] transition-colors"
            >
              <ArrowLeft size={14} />
              Back
            </button>
            <div className="w-px h-5 bg-[#2C1810]/15" />
            <div className="flex items-center gap-2.5 cursor-pointer" onClick={onBack}>
              <img src={logo} alt="Kayda" className="w-5 h-auto" />
              <span className="font-heading font-bold text-lg text-[#2C1810] tracking-tight">Kayda</span>
            </div>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#8C5A3C] font-bold">
            Evidence Analyzer // Demo Mode
          </span>
        </div>
      </header>

      <div className="pt-20 max-w-7xl mx-auto px-6 pb-24">
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
                <AlertTriangle size={18} className="text-red-600 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-bold">Error Processing Document</p>
                  <p className="mt-0.5 opacity-90">{error}</p>
                </div>
              </div>
            )}

            {/* Upload zone */}
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
              <Upload size={36} className="mx-auto mb-4 text-[#D4AF37] group-hover:scale-110 transition-transform" strokeWidth={1.5} />
              <p className="font-heading text-lg font-bold text-[#2C1810] mb-1">
                Drop your document here
              </p>
              <p className="text-xs text-[#5D4037]">
                Supports PDF, PNG, JPG, TIFF — up to 50MB
              </p>
              <p className="mt-3 text-[10px] font-mono uppercase tracking-wider text-[#8C5A3C] font-bold">
                Demo Mode: Select a sample case below
              </p>
            </div>

            {/* Sample case cards */}
            <div className="space-y-4">
              <p className="text-xs font-bold uppercase tracking-widest text-[#8C5A3C] mb-2">
                Sample Case Files
              </p>
              {sampleCases.map((c) => (
                <button
                  key={c.id}
                  onClick={() => startAnalysis(c)}
                  className="w-full text-left bg-white border border-[#2C1810]/10 p-5 rounded-lg hover:border-[#D4AF37] hover:shadow-md hover:-translate-y-[1px] transition-all group"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-[#FAF8F5] border border-[#D4AF37]/30 flex items-center justify-center text-[#D4AF37] shrink-0 group-hover:bg-[#D4AF37]/10 transition-colors">
                      <FileText size={18} strokeWidth={1.5} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-heading font-bold text-sm text-[#2C1810] mb-1">
                        {c.label}
                      </h3>
                      <p className="text-xs text-[#5D4037] leading-relaxed">
                        {c.description}
                      </p>
                      <p className="mt-2 font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold">
                        {c.filename}
                      </p>
                    </div>
                    <ArrowLeft size={14} className="rotate-180 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-opacity mt-3" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ─── Steps 1-3: Processing & Results ───────────────────── */}
        {currentStep > 0 && selectedCase && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* LEFT: Raw OCR Text */}
            <div className="lg:col-span-2 flex flex-col">
              <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden flex flex-col h-[600px] lg:h-[700px]">
                {/* Panel header */}
                <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText size={14} />
                    <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
                      Raw OCR Output
                    </span>
                  </div>
                  {currentStep >= 1 && (
                    <span className="font-mono text-[9px] text-[#D4AF37]">
                      {ocrProgress}% extracted
                    </span>
                  )}
                </div>

                {/* Progress bar */}
                {currentStep === 1 && (
                  <div className="h-1 bg-[#2C1810]/20">
                    <div
                      className="h-full bg-[#D4AF37] transition-all duration-100"
                      style={{ width: `${ocrProgress}%` }}
                    />
                  </div>
                )}

                {/* Text content */}
                <div
                  ref={textRef}
                  className="flex-1 overflow-y-auto p-5 font-mono text-[11px] leading-relaxed text-[#2C1810]/85 whitespace-pre-wrap"
                >
                  {displayedText}
                  {currentStep === 1 && ocrProgress < 100 && (
                    <span className="inline-block w-1.5 h-4 bg-[#D4AF37] animate-pulse ml-0.5 align-middle" />
                  )}
                </div>

                {/* File info footer */}
                <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-2.5 flex items-center justify-between">
                  <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
                    {selectedCase.filename}
                  </span>
                  <span className="font-mono text-[9px] text-[#5D4037]">
                    {selectedCase.rawText.length.toLocaleString()} chars
                  </span>
                </div>
              </div>
            </div>

            {/* RIGHT: Analysis / Results */}
            <div className="lg:col-span-3 flex flex-col">
              {/* Analysis in progress */}
              {currentStep === 2 && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-[600px] lg:h-[700px]">
                  <div className="w-20 h-20 rounded-full border-4 border-[#D4AF37]/30 border-t-[#D4AF37] animate-spin mb-8" />
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Analyzing Document
                  </h3>
                  <p className="text-xs text-[#5D4037] mb-6 text-center max-w-sm">
                    Multi-pass LLM extraction in progress. Identifying parties, incident details,
                    property records, and applicable legal sections...
                  </p>
                  <div className="w-full max-w-xs">
                    <div className="h-2 bg-[#2C1810]/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] rounded-full transition-all duration-200"
                        style={{ width: `${analysisProgress}%` }}
                      />
                    </div>
                    <div className="flex justify-between mt-2">
                      <span className="font-mono text-[9px] text-[#8C5A3C]">Processing chunks...</span>
                      <span className="font-mono text-[9px] text-[#D4AF37] font-bold">{Math.round(analysisProgress)}%</span>
                    </div>
                  </div>

                  {analysisProgress > 30 && (
                    <div className="mt-6 space-y-2 w-full max-w-xs animate-[fadeIn_0.5s_ease-out]">
                      <div className="flex items-center gap-2 text-[10px] text-[#5D4037]">
                        <Check size={12} className="text-green-600" />
                        <span>Parties identified</span>
                      </div>
                      {analysisProgress > 55 && (
                        <div className="flex items-center gap-2 text-[10px] text-[#5D4037] animate-[fadeIn_0.5s_ease-out]">
                          <Check size={12} className="text-green-600" />
                          <span>Incident timeline extracted</span>
                        </div>
                      )}
                      {analysisProgress > 75 && (
                        <div className="flex items-center gap-2 text-[10px] text-[#5D4037] animate-[fadeIn_0.5s_ease-out]">
                          <Check size={12} className="text-green-600" />
                          <span>Property and sections mapped</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Waiting for OCR */}
              {currentStep === 1 && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-[600px] lg:h-[700px]">
                  <Search size={36} className="text-[#D4AF37] mb-4 animate-pulse" strokeWidth={1.5} />
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Extracting Text
                  </h3>
                  <p className="text-xs text-[#5D4037] text-center max-w-sm">
                    Google Vision OCR is processing the document pages.
                    Raw text will appear in the left panel as each page completes.
                  </p>
                  <div className="mt-6 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce" />
                    <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce [animation-delay:0.2s]" />
                    <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce [animation-delay:0.4s]" />
                  </div>
                </div>
              )}

              {/* Results */}
              {currentStep === 3 && showFacts && facts && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden h-[600px] lg:h-[700px] flex flex-col">
                  {/* Results header */}
                  <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Shield size={14} />
                      <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
                        Structured Facts — Extraction Complete
                      </span>
                    </div>
                    <span className="font-mono text-[9px] text-green-400 flex items-center gap-1">
                      <Check size={10} strokeWidth={3} /> Verified
                    </span>
                  </div>

                  <div className="flex-1 overflow-y-auto p-5 space-y-4">
                    {/* WHO */}
                    <FactCard
                      title="Parties Identified"
                      icon={<Users size={16} />}
                      isOpen={expandedSection === "who"}
                      onToggle={() => setExpandedSection(expandedSection === "who" ? null : "who")}
                    >
                      <FactRow label="Complainant" value={facts.who.complainant} />
                      <FactRow label="Accused" value={facts.who.accused?.join(", ") || "—"} highlight />
                      <FactRow label="Victims" value={facts.who.victims?.join(", ") || "—"} />
                    </FactCard>

                    {/* INCIDENT */}
                    <FactCard
                      title="Incident Details"
                      icon={<AlertTriangle size={16} />}
                      isOpen={expandedSection === "incident"}
                      onToggle={() => setExpandedSection(expandedSection === "incident" ? null : "incident")}
                    >
                      <FactRow label="Summary" value={facts.incident.summary} long />
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                        <MiniCard icon={<Calendar size={13} />} label="Date" value={facts.incident.date} />
                        <MiniCard icon={<Clock size={13} />} label="Time" value={facts.incident.time} />
                        <MiniCard icon={<MapPin size={13} />} label="Place" value={facts.incident.place} />
                      </div>
                    </FactCard>

                    {/* PROPERTY */}
                    <FactCard
                      title="Property & Loss"
                      icon={<Briefcase size={16} />}
                      isOpen={expandedSection === "property"}
                      onToggle={() => setExpandedSection(expandedSection === "property" ? null : "property")}
                    >
                      {facts.property.cash && <FactRow label="Cash" value={facts.property.cash} />}
                      {facts.property.gold && <FactRow label="Gold / Ornaments" value={facts.property.gold} />}
                      {facts.property.documents && <FactRow label="Documents" value={facts.property.documents} />}
                      
                      {/* Vehicles */}
                      {facts.property.vehicles?.length > 0 && (
                        <div className="mt-4 space-y-3">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C] mb-3">
                            Vehicles ({facts.property.vehicles.length})
                          </div>
                          {facts.property.vehicles.map((vehicle, idx) => (
                            <div key={idx} className="bg-[#FAF8F5] border border-[#2C1810]/10 rounded-lg p-4 space-y-2">
                              {vehicle.type && (
                                <FactRow label="Type" value={vehicle.type} />
                              )}
                              {vehicle.make_model && (
                                <FactRow label="Make / Model" value={vehicle.make_model} />
                              )}
                              {vehicle.registration_no && (
                                <FactRow label="Registration No." value={vehicle.registration_no} highlight />
                              )}
                              {vehicle.engine_chassis_no && (
                                <FactRow label="Engine / Chassis No." value={vehicle.engine_chassis_no} />
                              )}
                              {vehicle.estimated_value && (
                                <FactRow label="Estimated Value" value={vehicle.estimated_value} />
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      
                      {facts.property.other_property?.length > 0 && (
                        <FactRow label="Other Property" value={facts.property.other_property.join("; ")} />
                      )}
                      {facts.property.estimated_loss && (
                        <div className="mt-3 bg-[#FFF8E1] border border-[#D4AF37]/30 rounded-lg px-4 py-3 flex items-center justify-between">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C]">
                            Total Estimated Loss
                          </span>
                          <span className="font-heading font-bold text-lg text-[#2C1810]">
                            {facts.property.estimated_loss}
                          </span>
                        </div>
                      )}
                    </FactCard>

                    {/* SECTIONS */}
                    <FactCard
                      title="Applicable Sections"
                      icon={<Scale size={16} />}
                      isOpen={expandedSection === "sections"}
                      onToggle={() => setExpandedSection(expandedSection === "sections" ? null : "sections")}
                    >
                      <div className="flex flex-wrap gap-2">
                        {facts.sections.map((s, i) => (
                          <span
                            key={i}
                            className="px-3 py-1.5 bg-[#2C1810] text-[#FAF8F5] font-mono text-[11px] font-bold rounded-md border border-[#D4AF37]/40"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </FactCard>
                  </div>

                  {/* Footer */}
                  <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-3 flex items-center justify-between">
                    <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
                      Schema: v4_unified_prompt // OCR: Google Vision
                    </span>
                    <button
                      onClick={() => {
                        setSelectedCase(null);
                        setCurrentStep(0);
                      }}
                      className="text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
                    >
                      Analyze Another
                      <ArrowLeft size={12} className="rotate-180" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────

function FactCard({ title, icon, isOpen, onToggle, children }) {
  return (
    <div className={`border rounded-lg overflow-hidden transition-all duration-300 ${
      isOpen ? "border-[#D4AF37]/40 shadow-sm" : "border-[#2C1810]/10"
    }`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-3.5 bg-[#FAF8F5] hover:bg-[#F5F0E8] transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-[#D4AF37]">{icon}</span>
          <span className="font-heading font-bold text-sm text-[#2C1810]">{title}</span>
        </div>
        <ChevronDown
          size={16}
          className={`text-[#8C5A3C] transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {isOpen && (
        <div className="px-5 py-4 space-y-2.5 animate-[fadeIn_0.3s_ease-out]">
          {children}
        </div>
      )}
    </div>
  );
}

function FactRow({ label, value, highlight, long }) {
  if (!value) return null;
  return (
    <div className={`flex ${long ? "flex-col gap-1" : "flex-col sm:flex-row sm:items-start gap-1 sm:gap-4"}`}>
      <span className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold shrink-0 sm:w-32 pt-0.5">
        {label}
      </span>
      <span className={`text-[12px] leading-relaxed ${highlight ? "text-[#991B1B] font-semibold" : "text-[#2C1810]"}`}>
        {value}
      </span>
    </div>
  );
}

function MiniCard({ icon, label, value }) {
  if (!value) return null;
  return (
    <div className="bg-[#FAF8F5] border border-[#2C1810]/10 rounded-lg p-3">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="text-[#D4AF37]">{icon}</span>
        <span className="font-mono text-[8px] uppercase tracking-wider text-[#8C5A3C] font-bold">{label}</span>
      </div>
      <p className="text-[11px] text-[#2C1810] leading-snug">{value}</p>
    </div>
  );
}
