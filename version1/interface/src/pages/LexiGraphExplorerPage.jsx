import { useState, useEffect, useRef } from "react";
import {
  Search,
  Database,
  ArrowLeft,
  Check,
  AlertTriangle,
  Shield,
  Scale,
  BookOpen,
  FileText,
  ChevronDown,
  Zap,
  Layers,
  Filter,
  GitBranch,
  Network,
  Brain,
  AlertCircle,
} from "lucide-react";
import logo from "../assets/logo1.svg";

const SAMPLE_CASES = [
  { 
    id: "theft_case",
    label: "Residential Theft — Gold Ornaments & Cash",
    description: "Neighbor forcibly entered home, broke almirah, and stole valuables.",
    query: "My neighbor Ramesh came into my house yesterday evening while I was away, broke open my steel almirah with a crowbar, and stole gold ornaments worth 5 lakhs and 50,000 cash."
  },
  { 
    id: "dowry_death",
    label: "Dowry Death — Section 304B Investigation",
    description: "Woman died within seven years of marriage due to dowry harassment.",
    query: "A woman died within seven years of marriage due to continuous harassment by her husband and in-laws for dowry. Medical reports show unnatural death."
  },
  { 
    id: "sexual_assault",
    label: "Sexual Assault — False Promise of Marriage",
    description: "Man induced woman into sexual relationship under false pretense.",
    query: "A woman alleged that a man induced her into a sexual relationship by falsely promising marriage despite already being married and having no intention of marrying her."
  },
  { 
    id: "kidnapping",
    label: "Kidnapping & Murder — Child Victim",
    description: "Child abducted for ransom and subsequently killed.",
    query: "A 10-year-old child was kidnapped from outside school, held for ransom of 10 lakhs, and later found murdered in an abandoned warehouse."
  },
];

// ─── Pipeline Steps ──────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: "understanding", label: "Query Understanding", icon: Search },
  { id: "embedding", label: "Vector Embedding", icon: Layers },
  { id: "retrieval", label: "Pinecone Retrieval", icon: Database },
  { id: "filtering", label: "Candidate Filtering", icon: Filter },
  { id: "verification", label: "Graph Verification", icon: Shield },
  { id: "enrichment", label: "Neo4j Enrichment", icon: GitBranch },
  { id: "community", label: "Community Context", icon: Network },
  { id: "reasoning", label: "Legal Reasoning", icon: Brain },
];

export default function LexiGraphExplorerPage({ onBack }) {
  const [selectedCase, setSelectedCase] = useState(null);
  const [currentStep, setCurrentStep] = useState(0); // 0=selection, 1-8=pipeline steps, 9=results
  const [stepProgress, setStepProgress] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [expandedSection, setExpandedSection] = useState("recommended");
  const [displayedQuery, setDisplayedQuery] = useState("");
  const [customQuery, setCustomQuery] = useState("");

  const startAnalysis = async (caseData) => {
    setSelectedCase(caseData);
    setCurrentStep(1);
    setStepProgress({});
    setResult(null);
    setError(null);
    setDisplayedQuery("");

    // Typewriter effect for query display
    const query = caseData.query;
    let charIdx = 0;
    const typeInterval = setInterval(() => {
      charIdx += 8;
      if (charIdx >= query.length) {
        charIdx = query.length;
        clearInterval(typeInterval);
        setDisplayedQuery(query);
        
        // Start pipeline after typewriter completes
        setTimeout(() => {
          runPipeline(query);
        }, 500);
      } else {
        setDisplayedQuery(query.slice(0, charIdx));
      }
    }, 20);
  };

  const runPipeline = async (query) => {
    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

    // Simulate step-by-step progress
    for (let i = 0; i < PIPELINE_STEPS.length; i++) {
      setCurrentStep(i + 1);
      setStepProgress(prev => ({ ...prev, [PIPELINE_STEPS[i].id]: "running" }));
      
      // Simulate processing time for visual effect
      await new Promise(resolve => setTimeout(resolve, i === 0 ? 800 : 600));
      
      setStepProgress(prev => ({ ...prev, [PIPELINE_STEPS[i].id]: "complete" }));
    }

    // Now make actual API call
    try {
      const response = await fetch(`${apiUrl}/api/lexigraph/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || "Failed to analyze query.");
      }

      setResult(data.data);
      setCurrentStep(9); // Results step
      setExpandedSection("recommended");
    } catch (err) {
      console.error("LexiGraph query error:", err);
      setError(err.message || "Unable to reach LexiGraph backend. Make sure it's running on port 5001.");
      setCurrentStep(0);
      setSelectedCase(null);
    }
  };

  const handleCustomQuery = () => {
    if (!customQuery.trim()) return;
    startAnalysis({
      id: `custom_${Date.now()}`,
      label: "Custom Legal Query",
      description: "User-submitted legal scenario for analysis",
      query: customQuery.trim()
    });
  };

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
              <img src={logo} alt="Kayda" className="w-12 h-auto" />
              <span className="font-heading font-bold text-2xl text-[#2C1810] tracking-tight">Kayda</span>
            </div>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#8C5A3C] font-bold">
            LexiGraph Explorer // GraphRAG Intelligence
          </span>
        </div>
      </header>

      <div className="pt-20 max-w-7xl mx-auto px-6 pb-24">
        {/* ─── Progress Steps Bar ────────────────────────────────── */}
        {currentStep > 0 && (
          <div className="flex items-center justify-center gap-2 md:gap-3 py-8 overflow-x-auto">
            {PIPELINE_STEPS.map((step, i) => {
              const Icon = step.icon;
              const stepNum = i + 1;
              const isActive = currentStep === stepNum;
              const isDone = currentStep > stepNum;
              
              return (
                <div key={step.id} className="flex items-center gap-2 md:gap-3">
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-full border transition-all duration-500 ${
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
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className={`w-6 md:w-12 h-px transition-colors duration-500 ${
                      currentStep > stepNum ? "bg-[#D4AF37]" : "bg-[#2C1810]/10"
                    }`} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ─── Step 0: Case Selection ────────────────────────────── */}
        {currentStep === 0 && (
          <div className="max-w-3xl mx-auto">
            <div className="text-center mb-12">
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#D4AF37] font-bold mb-3 block">
                Hierarchical GraphRAG Legal Intelligence
              </span>
              <h1 className="font-heading text-3xl md:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
                LexiGraph Explorer
              </h1>
              <p className="font-body text-sm md:text-base text-[#5D4037] max-w-xl mx-auto leading-relaxed">
                Describe your legal scenario in natural language. Our 8-stage GraphRAG pipeline combines 
                vector embeddings, Neo4j graph traversal, and LLM reasoning to identify applicable sections.
              </p>
            </div>

            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 text-red-800 animate-[fadeIn_0.3s_ease-out]">
                <AlertTriangle size={18} className="text-red-600 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-bold">Pipeline Execution Error</p>
                  <p className="mt-0.5 opacity-90">{error}</p>
                </div>
              </div>
            )}

            {/* Custom Query Input */}
            <div className="mb-8 p-6 border-2 border-dashed border-[#D4AF37]/40 rounded-xl bg-white/60 hover:bg-white hover:border-[#D4AF37] transition-all">
              <div className="flex items-start gap-4">
                <div className="flex-1">
                  <label className="block text-xs font-bold uppercase tracking-widest text-[#8C5A3C] mb-2">
                    Describe Your Legal Scenario
                  </label>
                  <textarea
                    value={customQuery}
                    onChange={(e) => setCustomQuery(e.target.value)}
                    placeholder="e.g., My neighbor broke into my house and stole gold ornaments worth 5 lakhs..."
                    className="w-full px-4 py-3 rounded-lg border border-[#2C1810]/20 focus:border-[#D4AF37] focus:outline-none focus:ring-2 focus:ring-[#D4AF37]/20 text-sm resize-none"
                    rows={3}
                  />
                </div>
                <button
                  onClick={handleCustomQuery}
                  disabled={!customQuery.trim()}
                  className="mt-7 px-6 py-3 bg-[#D4AF37] text-[#2C1810] font-semibold text-sm rounded-lg hover:bg-[#c49f27] transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Zap size={16} />
                  Analyze
                </button>
              </div>
            </div>

            {/* Sample case cards */}
            <div className="space-y-4">
              <p className="text-xs font-bold uppercase tracking-widest text-[#8C5A3C] mb-2">
                Sample Legal Scenarios
              </p>
              {SAMPLE_CASES.map((c) => (
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
                    </div>
                    <ArrowLeft size={14} className="rotate-180 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-opacity mt-3" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ─── Steps 1-8: Processing & Results ───────────────────── */}
        {currentStep > 0 && selectedCase && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* LEFT: Query Display */}
            <div className="lg:col-span-2 flex flex-col">
              <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden flex flex-col h-[600px] lg:h-[700px]">
                {/* Panel header */}
                <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Search size={14} />
                    <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
                      Legal Query Input
                    </span>
                  </div>
                  {currentStep < 9 && (
                    <span className="font-mono text-[9px] text-[#D4AF37]">
                      Processing...
                    </span>
                  )}
                </div>

                {/* Query content */}
                <div className="flex-1 overflow-y-auto p-5 font-body text-sm leading-relaxed text-[#2C1810]">
                  {displayedQuery}
                  {currentStep > 0 && currentStep < 9 && displayedQuery.length < selectedCase.query.length && (
                    <span className="inline-block w-1.5 h-4 bg-[#D4AF37] animate-pulse ml-0.5 align-middle" />
                  )}
                </div>

                {/* File info footer */}
                <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-2.5 flex items-center justify-between">
                  <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
                    {selectedCase.label}
                  </span>
                  <span className="font-mono text-[9px] text-[#5D4037]">
                    {selectedCase.query.length} chars
                  </span>
                </div>
              </div>
            </div>

            {/* RIGHT: Pipeline Status / Results */}
            <div className="lg:col-span-3 flex flex-col">
              {/* Pipeline in progress */}
              {currentStep > 0 && currentStep < 9 && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-[600px] lg:h-[700px]">
                  <div className="w-20 h-20 rounded-full border-4 border-[#D4AF37]/30 border-t-[#D4AF37] animate-spin mb-8" />
                  <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    {PIPELINE_STEPS[currentStep - 1]?.label}
                  </h3>
                  <p className="text-xs text-[#5D4037] mb-6 text-center max-w-sm">
                    {currentStep === 1 && "Analyzing query intent, extracting keywords and legal concepts..."}
                    {currentStep === 2 && "Generating semantic embeddings for similarity matching..."}
                    {currentStep === 3 && "Querying Pinecone vector database for candidate sections..."}
                    {currentStep === 4 && "Filtering candidates by relevance and intent alignment..."}
                    {currentStep === 5 && "Verifying candidates against Neo4j graph database..."}
                    {currentStep === 6 && "Enriching with constitutional articles, cases, and principles..."}
                    {currentStep === 7 && "Retrieving community context for domain-specific insights..."}
                    {currentStep === 8 && "Running LLM legal reasoning for final recommendations..."}
                  </p>

                  {/* Step progress indicators */}
                  <div className="space-y-2 w-full max-w-md">
                    {PIPELINE_STEPS.map((step, idx) => {
                      const status = stepProgress[step.id];
                      const stepNum = idx + 1;
                      return (
                        <div key={step.id} className={`flex items-center gap-3 text-xs transition-all duration-300 ${
                          stepNum < currentStep ? "opacity-100" : 
                          stepNum === currentStep ? "opacity-100" : "opacity-30"
                        }`}>
                          <div className="w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0">
                            {status === "complete" ? (
                              <Check size={12} className="text-green-600" strokeWidth={3} />
                            ) : status === "running" ? (
                              <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-pulse" />
                            ) : (
                              <span className="text-[9px] font-bold text-[#2C1810]/40">{stepNum}</span>
                            )}
                          </div>
                          <span className={`font-semibold ${
                            status === "complete" ? "text-green-700" :
                            status === "running" ? "text-[#D4AF37]" : "text-[#2C1810]/40"
                          }`}>
                            {step.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Results */}
              {currentStep === 9 && result && (
                <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden h-[600px] lg:h-[700px] flex flex-col">
                  {/* Results header */}
                  <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Shield size={14} />
                      <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
                        Legal Analysis Complete
                      </span>
                    </div>
                    <span className="font-mono text-[9px] text-green-400 flex items-center gap-1">
                      <Check size={10} strokeWidth={3} /> {Math.round((result.pipeline_confidence || 0) * 100)}% Confidence
                    </span>
                  </div>

                  <div className="flex-1 overflow-y-auto p-5 space-y-4">
                    {/* Recommended Sections */}
                    <ResultCard
                      title="Recommended Legal Sections"
                      icon={<Scale size={16} />}
                      isOpen={expandedSection === "recommended"}
                      onToggle={() => setExpandedSection(expandedSection === "recommended" ? null : "recommended")}
                      count={result.recommended_sections?.length || 0}
                    >
                      {result.recommended_sections && result.recommended_sections.length > 0 ? (
                        <div className="space-y-3">
                          {result.recommended_sections.map((sec, idx) => (
                            <div key={idx} className="p-4 rounded-lg bg-[#FAF8F5] border border-[#2C1810]/10">
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="px-2.5 py-1 bg-[#2C1810] text-[#FAF8F5] font-mono text-[11px] font-bold rounded">
                                    {sec.act} {sec.section}
                                  </span>
                                  {sec.equivalent_section && (
                                    <span className="px-2 py-0.5 bg-[#D4AF37]/20 text-[#8C5A3C] font-mono text-[10px] font-bold rounded border border-[#D4AF37]/40">
                                      ↔ {sec.equivalent_section.act} {sec.equivalent_section.section}
                                    </span>
                                  )}
                                </div>
                                <div className="text-lg font-heading font-bold text-[#2C1810]">
                                  {Math.round((sec.confidence || 0) * 100)}%
                                </div>
                              </div>
                              <h4 className="font-heading font-bold text-xs text-[#2C1810] mb-1.5">
                                {sec.title}
                              </h4>
                              <p className="text-[11px] text-[#5D4037] leading-relaxed">
                                {sec.applicability || sec.reason}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-[#5D4037] italic">No applicable sections found.</p>
                      )}
                    </ResultCard>

                    {/* Supporting Cases */}
                    {result.supporting_cases && result.supporting_cases.length > 0 && (
                      <ResultCard
                        title="Precedent Cases"
                        icon={<FileText size={16} />}
                        isOpen={expandedSection === "cases"}
                        onToggle={() => setExpandedSection(expandedSection === "cases" ? null : "cases")}
                        count={result.supporting_cases.length}
                      >
                        <div className="space-y-3">
                          {result.supporting_cases.slice(0, 3).map((cs, idx) => (
                            <div key={idx} className="p-3 rounded-lg bg-[#FAF8F5] border border-[#2C1810]/10">
                              <h4 className="font-heading font-bold text-xs text-[#2C1810] mb-0.5">
                                {cs.case_name}
                              </h4>
                              <p className="text-[10px] text-[#8C5A3C] font-mono mb-1.5">{cs.citation}</p>
                              <p className="text-[11px] text-[#5D4037] leading-relaxed">{cs.reason}</p>
                            </div>
                          ))}
                        </div>
                      </ResultCard>
                    )}

                    {/* Supporting Evidence */}
                    {result.supporting_evidence && result.supporting_evidence.length > 0 && (
                      <ResultCard
                        title="Required Evidence"
                        icon={<Layers size={16} />}
                        isOpen={expandedSection === "evidence"}
                        onToggle={() => setExpandedSection(expandedSection === "evidence" ? null : "evidence")}
                        count={result.supporting_evidence.length}
                      >
                        <div className="flex flex-wrap gap-2">
                          {result.supporting_evidence.map((ev, idx) => (
                            <span key={idx} className="px-2.5 py-1 bg-[#FFF8E1] border border-[#D4AF37]/30 text-[#8C5A3C] text-[10px] font-semibold rounded">
                              {ev}
                            </span>
                          ))}
                        </div>
                      </ResultCard>
                    )}

                    {/* Constitutional Articles */}
                    {result.supporting_articles && result.supporting_articles.length > 0 && (
                      <ResultCard
                        title="Constitutional Articles"
                        icon={<BookOpen size={16} />}
                        isOpen={expandedSection === "articles"}
                        onToggle={() => setExpandedSection(expandedSection === "articles" ? null : "articles")}
                        count={result.supporting_articles.length}
                      >
                        <div className="space-y-2">
                          {result.supporting_articles.map((art, idx) => (
                            <div key={idx} className="p-2.5 rounded bg-[#FAF8F5] border border-[#2C1810]/10 text-[10px] text-[#2C1810]">
                              {art}
                            </div>
                          ))}
                        </div>
                      </ResultCard>
                    )}

                    {/* Rejected Sections */}
                    {result.rejected_sections && result.rejected_sections.length > 0 && (
                      <ResultCard
                        title="Rejected Sections"
                        icon={<AlertCircle size={16} />}
                        isOpen={expandedSection === "rejected"}
                        onToggle={() => setExpandedSection(expandedSection === "rejected" ? null : "rejected")}
                        count={result.rejected_sections.length}
                      >
                        <div className="space-y-2">
                          {result.rejected_sections.slice(0, 3).map((rej, idx) => (
                            <div key={idx} className="p-3 rounded bg-red-50 border border-red-200">
                              <div className="font-mono text-[10px] font-bold text-red-900 mb-0.5">{rej.section}</div>
                              <div className="text-[10px] text-red-700">{rej.reason}</div>
                            </div>
                          ))}
                        </div>
                      </ResultCard>
                    )}
                  </div>

                  {/* Footer */}
                  <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-3 flex items-center justify-between">
                    <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
                      GraphRAG Pipeline v2.0
                    </span>
                    <button
                      onClick={() => {
                        setSelectedCase(null);
                        setCurrentStep(0);
                        setCustomQuery("");
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

function ResultCard({ title, icon, isOpen, onToggle, count, children }) {
  return (
    <div className={`border rounded-lg overflow-hidden transition-all duration-300 ${
      isOpen ? "border-[#D4AF37]/40 shadow-sm" : "border-[#2C1810]/10"
    }`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-[#FAF8F5] hover:bg-[#F5F0E8] transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-[#D4AF37]">{icon}</span>
          <span className="font-heading font-bold text-xs text-[#2C1810]">{title}</span>
          {count !== undefined && (
            <span className="px-2 py-0.5 bg-[#D4AF37]/20 text-[#8C5A3C] text-[9px] font-bold rounded-full">
              {count}
            </span>
          )}
        </div>
        <ChevronDown
          size={14}
          className={`text-[#8C5A3C] transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {isOpen && (
        <div className="px-4 py-3 animate-[fadeIn_0.3s_ease-out]">
          {children}
        </div>
      )}
    </div>
  );
}
