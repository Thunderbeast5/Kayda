// // /*import { useState, useEffect, useRef } from "react";
// // import { sampleCases } from "../data/mockEvidenceData";
// // import {
// //   FileText,
// //   Upload,
// //   Search,
// //   Shield,
// //   ChevronDown,
// //   ArrowLeft,
// //   Check,
// //   AlertTriangle,
// //   Scale,
// //   Users,
// //   MapPin,
// //   Calendar,
// //   Clock,
// //   Briefcase,
// //   Layers,
// // } from "lucide-react";
// // import logo from "../assets/logo1.svg";

// // import StandardNavbar from "../components/StandardNavbar";

// // // ─── Progress Steps ──────────────────────────────────────────────
// // const STEPS = [
// //   { id: "upload", label: "Upload Document", icon: Upload },
// //   { id: "ocr", label: "OCR Extraction", icon: Search },
// //   { id: "analysis", label: "AI Analysis", icon: Scale },
// //   { id: "results", label: "Structured Output", icon: Layers },
// // ];

// // export default function EvidenceAnalyzerPage({ onBack }) {
// //   const [selectedCase, setSelectedCase] = useState(null);
// //   const [currentStep, setCurrentStep] = useState(0); // 0=upload, 1=ocr, 2=analysis, 3=results
// //   const [ocrProgress, setOcrProgress] = useState(0);
// //   const [analysisProgress, setAnalysisProgress] = useState(0);
// //   const [displayedText, setDisplayedText] = useState("");
// //   const [showFacts, setShowFacts] = useState(false);
// //   const [expandedSection, setExpandedSection] = useState("timeline");
// //   const textRef = useRef(null);
// //   const [error, setError] = useState(null);
// //   const fileInputRef = useRef(null);

// //   const handleFileUpload = (e) => {
// //     const file = e.target.files?.[0];
// //     if (!file) return;

// //     setError(null);
// //     setSelectedCase({
// //       id: `uploaded_${Date.now()}`,
// //       filename: file.name,
// //       label: `Uploaded — ${file.name}`,
// //       description: "Processing case document via backend intelligence pipeline...",
// //       rawText: "",
// //       facts: null,
// //       timeline: [],
// //       graph: { nodes: [], edges: [] },
// //     });
// //     setCurrentStep(1);
// //     setOcrProgress(0);
// //     setAnalysisProgress(0);
// //     setDisplayedText("");
// //     setShowFacts(false);

// //     const xhr = new XMLHttpRequest();
// //     const formData = new FormData();
// //     formData.append("file", file);

// //     const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
// //     xhr.open("POST", `${apiUrl}/api/evidence/analyze`, true);

// //     xhr.upload.onprogress = (event) => {
// //       if (event.lengthComputable) {
// //         const percentComplete = Math.round((event.loaded / event.total) * 100);
// //         // Show progress up to 90% during upload phase
// //         setOcrProgress(Math.min(90, Math.round(percentComplete * 0.9)));
// //       }
// //     };

// //     xhr.onload = () => {
// //       if (xhr.status >= 200 && xhr.status < 300) {
// //         try {
// //           const res = JSON.parse(xhr.responseText);
// //           if (res.success) {
// //             setOcrProgress(100);
// //             const { rawText, facts, timeline = [], graph = { nodes: [], edges: [] } } = res.data;
            
// //             // Set raw OCR output text
// //             setDisplayedText(rawText);
            
// //             // Move to Analysis phase
// //             setCurrentStep(2);
            
// //             // Fast visual progression for the analysis progress bar (feels responsive and satisfying)
// //             let prog = 0;
// //             const interval = setInterval(() => {
// //               prog += Math.random() * 15 + 10;
// //               if (prog >= 100) {
// //                 prog = 100;
// //                 clearInterval(interval);
// //                 setAnalysisProgress(100);
// //                 setTimeout(() => {
// //                   setSelectedCase((prev) => ({
// //                     ...prev,
// //                     rawText,
// //                     facts,
// //                     timeline,
// //                     graph,
// //                   }));
// //                   setExpandedSection("timeline");
// //                   setCurrentStep(3);
// //                   setShowFacts(true);
// //                 }, 600);
// //               } else {
// //                 setAnalysisProgress(Math.min(prog, 100));
// //               }
// //             }, 150);
// //           } else {
// //             setError(res.message || "Analysis failed.");
// //             setCurrentStep(0);
// //             setSelectedCase(null);
// //           }
// //         } catch (err) {
// //           setError("Failed to parse API response.");
// //           setCurrentStep(0);
// //           setSelectedCase(null);
// //         }
// //       } else {
// //         try {
// //           const res = JSON.parse(xhr.responseText);
// //           setError(res.message || `Error ${xhr.status}: ${xhr.statusText}`);
// //         } catch (err) {
// //           setError(`Server returned status code ${xhr.status}`);
// //         }
// //         setCurrentStep(0);
// //         setSelectedCase(null);
// //       }
// //     };

// //     xhr.onerror = () => {
// //       setError("Network connection failed. Make sure the backend server is running.");
// //       setCurrentStep(0);
// //       setSelectedCase(null);
// //     };

// //     xhr.send(formData);
// //   };

// //   // ─── Simulate the pipeline when a case is selected ─────────────
// //   const startAnalysis = (caseData) => {
// //     setSelectedCase(caseData);
// //     setCurrentStep(1);
// //     setOcrProgress(0);
// //     setAnalysisProgress(0);
// //     setDisplayedText("");
// //     setShowFacts(false);
// //     setExpandedSection("timeline");

// //     // Step 1: OCR extraction (typewriter)
// //     let charIdx = 0;
// //     const rawText = caseData.rawText;
// //     const charsPerTick = 12;

// //     const ocrInterval = setInterval(() => {
// //       charIdx += charsPerTick;
// //       if (charIdx >= rawText.length) {
// //         charIdx = rawText.length;
// //         clearInterval(ocrInterval);
// //         setOcrProgress(100);
// //         setDisplayedText(rawText);

// //         // Move to analysis step after a short pause
// //         setTimeout(() => {
// //           setCurrentStep(2);
// //           // Step 2: Analysis progress bar
// //           let prog = 0;
// //           const analysisInterval = setInterval(() => {
// //             prog += Math.random() * 8 + 2;
// //             if (prog >= 100) {
// //               prog = 100;
// //               clearInterval(analysisInterval);
// //               setAnalysisProgress(100);
// //               setTimeout(() => {
// //                 setCurrentStep(3);
// //                 setShowFacts(true);
// //               }, 600);
// //             }
// //             setAnalysisProgress(Math.min(prog, 100));
// //           }, 120);
// //         }, 800);
// //       }
// //       setDisplayedText(rawText.slice(0, charIdx));
// //       setOcrProgress(Math.round((charIdx / rawText.length) * 100));
// //     }, 18);
// //   };

// //   // Auto-scroll the OCR text panel
// //   useEffect(() => {
// //     if (textRef.current) {
// //       textRef.current.scrollTop = textRef.current.scrollHeight;
// //     }
// //   }, [displayedText]);

// //   const facts = selectedCase?.facts;
// //   const timeline = selectedCase?.timeline || [];
// //   const graph = selectedCase?.graph || { nodes: [], edges: [] };

// //   return (
// //     <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810]">
// //       {/* ─── Reusable Sticky Top Navbar ─────────────────────────── */}
// //       <StandardNavbar onBack={onBack} title="Evidence Analyzer" subtitle="Demo Mode" />

// //       <div className="pt-6 max-w-7xl mx-auto px-6 pb-24">
// //         {/* ─── Progress Steps Bar ────────────────────────────────── */}
// //         <div className="flex items-center justify-center gap-2 md:gap-4 py-8">
// //           {STEPS.map((step, i) => {
// //             const Icon = step.icon;
// //             const isActive = i === currentStep;
// //             const isDone = i < currentStep;
// //             return (
// //               <div key={step.id} className="flex items-center gap-2 md:gap-4">
// //                 <div className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-all duration-500 ${
// //                   isDone
// //                     ? "bg-[#2C1810] text-[#FAF8F5] border-[#D4AF37]"
// //                     : isActive
// //                     ? "bg-white text-[#2C1810] border-[#D4AF37] shadow-md"
// //                     : "bg-transparent text-[#2C1810]/30 border-[#2C1810]/10"
// //                 }`}>
// //                   {isDone ? (
// //                     <Check size={14} strokeWidth={3} />
// //                   ) : (
// //                     <Icon size={14} strokeWidth={isActive ? 2.5 : 1.5} />
// //                   )}
// //                   <span className="text-[10px] font-bold uppercase tracking-wider hidden md:inline">
// //                     {step.label}
// //                   </span>
// //                 </div>
// //                 {i < STEPS.length - 1 && (
// //                   <div className={`w-8 md:w-16 h-px transition-colors duration-500 ${
// //                     i < currentStep ? "bg-[#D4AF37]" : "bg-[#2C1810]/10"
// //                   }`} />
// //                 )}
// //               </div>
// //             );
// //           })}
// //         </div>

// //         {/* ─── Step 0: File Selection ────────────────────────────── */}
// //         {currentStep === 0 && (
// //           <div className="max-w-3xl mx-auto">
// //             <div className="text-center mb-12">
// //               <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#D4AF37] font-bold mb-3 block">
// //                 Document Intelligence Pipeline
// //               </span>
// //               <h1 className="font-heading text-3xl md:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
// //                 Evidence Analyzer
// //               </h1>
// //               <p className="font-body text-sm md:text-base text-[#5D4037] max-w-xl mx-auto leading-relaxed">
// //                 Upload an FIR, charge sheet, or legal document. The AI pipeline extracts structured facts
// //                 using OCR and multi-pass language model analysis.
// //               </p>
// //             </div>

// //             {error && (
// //               <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 text-red-800 animate-[fadeIn_0.3s_ease-out]">
// //                 <AlertTriangle size={18} className="text-red-600 shrink-0 mt-0.5" />
// //                 <div className="text-xs">
// //                   <p className="font-bold">Error Processing Document</p>
// //                   <p className="mt-0.5 opacity-90">{error}</p>
// //                 </div>
// //               </div>
// //             )}

// //             {/* Upload zone */}
// //             <div 
// //               onClick={() => fileInputRef.current && fileInputRef.current.click()}
// //               className="border-2 border-dashed border-[#D4AF37]/40 rounded-xl p-8 md:p-12 bg-white/60 hover:bg-white hover:border-[#D4AF37] transition-all mb-8 text-center cursor-pointer group"
// //             >
// //               <input
// //                 ref={fileInputRef}
// //                 type="file"
// //                 className="hidden"
// //                 onChange={handleFileUpload}
// //                 accept="application/pdf,image/*"
// //               />
// //               <Upload size={36} className="mx-auto mb-4 text-[#D4AF37] group-hover:scale-110 transition-transform" strokeWidth={1.5} />
// //               <p className="font-heading text-lg font-bold text-[#2C1810] mb-1">
// //                 Drop your document here
// //               </p>
// //               <p className="text-xs text-[#5D4037]">
// //                 Supports PDF, PNG, JPG, TIFF — up to 50MB
// //               </p>
// //               <p className="mt-3 text-[10px] font-mono uppercase tracking-wider text-[#8C5A3C] font-bold">
// //                 Demo Mode: Select a sample case below
// //               </p>
// //             </div>

// //             {/* Sample case cards */}
// //             <div className="space-y-4">
// //               <p className="text-xs font-bold uppercase tracking-widest text-[#8C5A3C] mb-2">
// //                 Sample Case Files
// //               </p>
// //               {sampleCases.map((c) => (
// //                 <button
// //                   key={c.id}
// //                   onClick={() => startAnalysis(c)}
// //                   className="w-full text-left bg-white border border-[#2C1810]/10 p-5 rounded-lg hover:border-[#D4AF37] hover:shadow-md hover:-translate-y-[1px] transition-all group"
// //                 >
// //                   <div className="flex items-start gap-4">
// //                     <div className="w-10 h-10 rounded-lg bg-[#FAF8F5] border border-[#D4AF37]/30 flex items-center justify-center text-[#D4AF37] shrink-0 group-hover:bg-[#D4AF37]/10 transition-colors">
// //                       <FileText size={18} strokeWidth={1.5} />
// //                     </div>
// //                     <div className="flex-1 min-w-0">
// //                       <h3 className="font-heading font-bold text-sm text-[#2C1810] mb-1">
// //                         {c.label}
// //                       </h3>
// //                       <p className="text-xs text-[#5D4037] leading-relaxed">
// //                         {c.description}
// //                       </p>
// //                       <p className="mt-2 font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold">
// //                         {c.filename}
// //                       </p>
// //                     </div>
// //                     <ArrowLeft size={14} className="rotate-180 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-opacity mt-3" />
// //                   </div>
// //                 </button>
// //               ))}
// //             </div>
// //           </div>
// //         )}

// //         {/* ─── Steps 1-3: Processing & Results ───────────────────── */}
// //         {currentStep > 0 && selectedCase && (
// //           <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
// //             {/* LEFT: Raw OCR Text */}
// //             <div className="lg:col-span-2 flex flex-col">
// //               <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden flex flex-col h-[600px] lg:h-[700px]">
// //                 {/* Panel header */}
// //                 <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
// //                   <div className="flex items-center gap-2">
// //                     <FileText size={14} />
// //                     <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
// //                       Raw OCR Output
// //                     </span>
// //                   </div>
// //                   {currentStep >= 1 && (
// //                     <span className="font-mono text-[9px] text-[#D4AF37]">
// //                       {ocrProgress}% extracted
// //                     </span>
// //                   )}
// //                 </div>

// //                 {/* Progress bar */}
// //                 {currentStep === 1 && (
// //                   <div className="h-1 bg-[#2C1810]/20">
// //                     <div
// //                       className="h-full bg-[#D4AF37] transition-all duration-100"
// //                       style={{ width: `${ocrProgress}%` }}
// //                     />
// //                   </div>
// //                 )}

// //                 {/* Text content */}
// //                 <div
// //                   ref={textRef}
// //                   className="flex-1 overflow-y-auto p-5 font-mono text-[11px] leading-relaxed text-[#2C1810]/85 whitespace-pre-wrap"
// //                 >
// //                   {displayedText}
// //                   {currentStep === 1 && ocrProgress < 100 && (
// //                     <span className="inline-block w-1.5 h-4 bg-[#D4AF37] animate-pulse ml-0.5 align-middle" />
// //                   )}
// //                 </div>

// //                 {/* File info footer */}
// //                 <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-2.5 flex items-center justify-between">
// //                   <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
// //                     {selectedCase.filename}
// //                   </span>
// //                   <span className="font-mono text-[9px] text-[#5D4037]">
// //                     {(selectedCase.rawText || "").length.toLocaleString()} chars
// //                   </span>
// //                 </div>
// //               </div>
// //             </div>

// //             {/* RIGHT: Analysis / Results */}
// //             <div className="lg:col-span-3 flex flex-col">
// //               {/* Analysis in progress */}
// //               {currentStep === 2 && (
// //                 <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-[600px] lg:h-[700px]">
// //                   <div className="w-20 h-20 rounded-full border-4 border-[#D4AF37]/30 border-t-[#D4AF37] animate-spin mb-8" />
// //                   <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
// //                     Analyzing Document
// //                   </h3>
// //                   <p className="text-xs text-[#5D4037] mb-6 text-center max-w-sm">
// //                     Multi-pass LLM extraction in progress. Identifying parties, incident details,
// //                     timeline events, relationship graph links, property records, and applicable legal sections...
// //                   </p>
// //                   <div className="w-full max-w-xs">
// //                     <div className="h-2 bg-[#2C1810]/10 rounded-full overflow-hidden">
// //                       <div
// //                         className="h-full bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] rounded-full transition-all duration-200"
// //                         style={{ width: `${analysisProgress}%` }}
// //                       />
// //                     </div>
// //                     <div className="flex justify-between mt-2">
// //                       <span className="font-mono text-[9px] text-[#8C5A3C]">Processing chunks...</span>
// //                       <span className="font-mono text-[9px] text-[#D4AF37] font-bold">{Math.round(analysisProgress)}%</span>
// //                     </div>
// //                   </div>

// //                   {analysisProgress > 30 && (
// //                     <div className="mt-6 space-y-2 w-full max-w-xs animate-[fadeIn_0.5s_ease-out]">
// //                       <div className="flex items-center gap-2 text-[10px] text-[#5D4037]">
// //                         <Check size={12} className="text-green-600" />
// //                         <span>Parties identified</span>
// //                       </div>
// //                       {analysisProgress > 55 && (
// //                         <div className="flex items-center gap-2 text-[10px] text-[#5D4037] animate-[fadeIn_0.5s_ease-out]">
// //                           <Check size={12} className="text-green-600" />
// //                           <span>Incident timeline extracted</span>
// //                         </div>
// //                       )}
// //                       {analysisProgress > 75 && (
// //                         <div className="flex items-center gap-2 text-[10px] text-[#5D4037] animate-[fadeIn_0.5s_ease-out]">
// //                           <Check size={12} className="text-green-600" />
// //                           <span>Property and sections mapped</span>
// //                         </div>
// //                       )}
// //                     </div>
// //                   )}
// //                 </div>
// //               )}

// //               {/* Waiting for OCR */}
// //               {currentStep === 1 && (
// //                 <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-[600px] lg:h-[700px]">
// //                   <Search size={36} className="text-[#D4AF37] mb-4 animate-pulse" strokeWidth={1.5} />
// //                   <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
// //                     Extracting Text
// //                   </h3>
// //                   <p className="text-xs text-[#5D4037] text-center max-w-sm">
// //                     Google Vision OCR is processing the document pages.
// //                     Raw text will appear in the left panel as each page completes.
// //                   </p>
// //                   <div className="mt-6 flex items-center gap-2">
// //                     <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce" />
// //                     <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce [animation-delay:0.2s]" />
// //                     <div className="w-2 h-2 rounded-full bg-[#D4AF37] animate-bounce [animation-delay:0.4s]" />
// //                   </div>
// //                 </div>
// //               )}

// //               {/* Results */}
// //               {currentStep === 3 && showFacts && facts && (
// //                 <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden h-[600px] lg:h-[700px] flex flex-col">
// //                   {/* Results header */}
// //                   <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between">
// //                     <div className="flex items-center gap-2">
// //                       <Shield size={14} />
// //                       <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
// //                         Structured Facts — Extraction Complete
// //                       </span>
// //                     </div>
// //                     <span className="font-mono text-[9px] text-green-400 flex items-center gap-1">
// //                       <Check size={10} strokeWidth={3} /> Verified
// //                     </span>
// //                   </div>

// //                   <div className="flex-1 overflow-y-auto p-5 space-y-4">
// //                     {/* WHO */}
// //                     <FactCard
// //                       title="Parties Identified"
// //                       icon={<Users size={16} />}
// //                       isOpen={expandedSection === "who"}
// //                       onToggle={() => setExpandedSection(expandedSection === "who" ? null : "who")}
// //                     >
// //                       <FactRow label="Complainant" value={facts.who.complainant} />
// //                       <FactRow label="Accused" value={facts.who.accused?.join(", ") || "—"} highlight />
// //                       <FactRow label="Victims" value={facts.who.victims?.join(", ") || "—"} />
// //                     </FactCard>

// //                     {/* INCIDENT */}
// //                     <FactCard
// //                       title="Incident Details"
// //                       icon={<AlertTriangle size={16} />}
// //                       isOpen={expandedSection === "incident"}
// //                       onToggle={() => setExpandedSection(expandedSection === "incident" ? null : "incident")}
// //                     >
// //                       <FactRow label="Summary" value={facts.incident.summary} long />
// //                       <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
// //                         <MiniCard icon={<Calendar size={13} />} label="Date" value={facts.incident.date} />
// //                         <MiniCard icon={<Clock size={13} />} label="Time" value={facts.incident.time} />
// //                         <MiniCard icon={<MapPin size={13} />} label="Place" value={facts.incident.place} />
// //                       </div>
// //                     </FactCard>

// //                     {/* TIMELINE */}
// //                     <FactCard
// //                       title="Timeline"
// //                       icon={<Calendar size={16} />}
// //                       isOpen={expandedSection === "timeline"}
// //                       onToggle={() => setExpandedSection(expandedSection === "timeline" ? null : "timeline")}
// //                     >
// //                       {timeline.length > 0 ? (
// //                         <div className="space-y-3">
// //                           {timeline.map((event, idx) => (
// //                             <div key={event.event_id || idx} className="bg-[#FAF8F5] border border-[#2C1810]/10 rounded-lg p-4">
// //                               <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
// //                                 <div className="flex items-center gap-2">
// //                                   <span className="px-2 py-1 rounded-md bg-[#2C1810] text-[#FAF8F5] font-mono text-[10px] font-bold">
// //                                     {event.event_id || `E${idx + 1}`}
// //                                   </span>
// //                                   <span className="px-2 py-1 rounded-md bg-[#FFF8E1] text-[#8C5A3C] font-mono text-[10px] font-bold uppercase tracking-wider">
// //                                     {event.event_type || "other"}
// //                                   </span>
// //                                 </div>
// //                                 <span className="font-mono text-[10px] text-[#8C5A3C]">
// //                                   {(event.date || "No date")} {event.time ? `• ${event.time}` : ""}
// //                                 </span>
// //                               </div>
// //                               <p className="text-[12px] leading-relaxed text-[#2C1810]">
// //                                 {event.description || "No description available."}
// //                               </p>
// //                               <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
// //                                 <MiniCard icon={<Users size={13} />} label="Actors" value={event.actors?.length ? event.actors.join(", ") : "—"} />
// //                                 <MiniCard icon={<MapPin size={13} />} label="Location" value={event.location || "—"} />
// //                                 <MiniCard icon={<Briefcase size={13} />} label="Amount" value={event.amount || "—"} />
// //                               </div>
// //                             </div>
// //                           ))}
// //                         </div>
// //                       ) : (
// //                         <p className="text-[12px] text-[#5D4037]">
// //                           No timeline data returned for this case.
// //                         </p>
// //                       )}
// //                     </FactCard>

// //                     {/* GRAPH */}
// //                     <FactCard
// //                       title="Relationship Graph"
// //                       icon={<Layers size={16} />}
// //                       isOpen={expandedSection === "graph"}
// //                       onToggle={() => setExpandedSection(expandedSection === "graph" ? null : "graph")}
// //                     >
// //                       <GraphView graph={graph} />
// //                     </FactCard>

// //                     {/* PROPERTY */}
// //                     <FactCard
// //                       title="Property & Loss"
// //                       icon={<Briefcase size={16} />}
// //                       isOpen={expandedSection === "property"}
// //                       onToggle={() => setExpandedSection(expandedSection === "property" ? null : "property")}
// //                     >
// //                       {facts.property.cash && <FactRow label="Cash" value={facts.property.cash} />}
// //                       {facts.property.gold && <FactRow label="Gold / Ornaments" value={facts.property.gold} />}
// //                       {facts.property.documents && <FactRow label="Documents" value={facts.property.documents} />}
                      
// //                       {/* Vehicles */}
// //                       {facts.property.vehicles?.length > 0 && (
// //                         <div className="mt-4 space-y-3">
// //                           <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C] mb-3">
// //                             Vehicles ({facts.property.vehicles.length})
// //                           </div>
// //                           {facts.property.vehicles.map((vehicle, idx) => (
// //                             <div key={idx} className="bg-[#FAF8F5] border border-[#2C1810]/10 rounded-lg p-4 space-y-2">
// //                               {vehicle.type && (
// //                                 <FactRow label="Type" value={vehicle.type} />
// //                               )}
// //                               {vehicle.make_model && (
// //                                 <FactRow label="Make / Model" value={vehicle.make_model} />
// //                               )}
// //                               {vehicle.registration_no && (
// //                                 <FactRow label="Registration No." value={vehicle.registration_no} highlight />
// //                               )}
// //                               {vehicle.engine_chassis_no && (
// //                                 <FactRow label="Engine / Chassis No." value={vehicle.engine_chassis_no} />
// //                               )}
// //                               {vehicle.estimated_value && (
// //                                 <FactRow label="Estimated Value" value={vehicle.estimated_value} />
// //                               )}
// //                             </div>
// //                           ))}
// //                         </div>
// //                       )}
                      
// //                       {facts.property.other_property?.length > 0 && (
// //                         <FactRow label="Other Property" value={facts.property.other_property.join("; ")} />
// //                       )}
// //                       {facts.property.estimated_loss && (
// //                         <div className="mt-3 bg-[#FFF8E1] border border-[#D4AF37]/30 rounded-lg px-4 py-3 flex items-center justify-between">
// //                           <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C]">
// //                             Total Estimated Loss
// //                           </span>
// //                           <span className="font-heading font-bold text-lg text-[#2C1810]">
// //                             {facts.property.estimated_loss}
// //                           </span>
// //                         </div>
// //                       )}
// //                     </FactCard>

// //                     {/* SECTIONS */}
// //                     <FactCard
// //                       title="Applicable Sections"
// //                       icon={<Scale size={16} />}
// //                       isOpen={expandedSection === "sections"}
// //                       onToggle={() => setExpandedSection(expandedSection === "sections" ? null : "sections")}
// //                     >
// //                       <div className="flex flex-wrap gap-2">
// //                         {facts.sections.map((s, i) => (
// //                           <span
// //                             key={i}
// //                             className="px-3 py-1.5 bg-[#2C1810] text-[#FAF8F5] font-mono text-[11px] font-bold rounded-md border border-[#D4AF37]/40"
// //                           >
// //                             {s}
// //                           </span>
// //                         ))}
// //                       </div>
// //                     </FactCard>
// //                   </div>

// //                   {/* Footer */}
// //                   <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-3 flex items-center justify-between">
// //                     <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
// //                       Schema: v4_unified_prompt // OCR: Google Vision
// //                     </span>
// //                     <button
// //                       onClick={() => {
// //                         setSelectedCase(null);
// //                         setCurrentStep(0);
// //                       }}
// //                       className="text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
// //                     >
// //                       Analyze Another
// //                       <ArrowLeft size={12} className="rotate-180" />
// //                     </button>
// //                   </div>
// //                 </div>
// //               )}
// //             </div>
// //           </div>
// //         )}
// //       </div>
// //     </div>
// //   );
// // }

// // // ─── Sub-components ────────────────────────────────────────────────

// // function FactCard({ title, icon, isOpen, onToggle, children }) {
// //   return (
// //     <div className={`border rounded-lg overflow-hidden transition-all duration-300 ${
// //       isOpen ? "border-[#D4AF37]/40 shadow-sm" : "border-[#2C1810]/10"
// //     }`}>
// //       <button
// //         onClick={onToggle}
// //         className="w-full flex items-center justify-between px-5 py-3.5 bg-[#FAF8F5] hover:bg-[#F5F0E8] transition-colors"
// //       >
// //         <div className="flex items-center gap-2.5">
// //           <span className="text-[#D4AF37]">{icon}</span>
// //           <span className="font-heading font-bold text-sm text-[#2C1810]">{title}</span>
// //         </div>
// //         <ChevronDown
// //           size={16}
// //           className={`text-[#8C5A3C] transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}
// //         />
// //       </button>
// //       {isOpen && (
// //         <div className="px-5 py-4 space-y-2.5 animate-[fadeIn_0.3s_ease-out]">
// //           {children}
// //         </div>
// //       )}
// //     </div>
// //   );
// // }

// // function FactRow({ label, value, highlight, long }) {
// //   if (!value) return null;
// //   return (
// //     <div className={`flex ${long ? "flex-col gap-1" : "flex-col sm:flex-row sm:items-start gap-1 sm:gap-4"}`}>
// //       <span className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold shrink-0 sm:w-32 pt-0.5">
// //         {label}
// //       </span>
// //       <span className={`text-[12px] leading-relaxed ${highlight ? "text-[#991B1B] font-semibold" : "text-[#2C1810]"}`}>
// //         {value}
// //       </span>
// //     </div>
// //   );
// // }

// // function MiniCard({ icon, label, value }) {
// //   if (!value) return null;
// //   return (
// //     <div className="bg-[#FAF8F5] border border-[#2C1810]/10 rounded-lg p-3">
// //       <div className="flex items-center gap-1.5 mb-1.5">
// //         <span className="text-[#D4AF37]">{icon}</span>
// //         <span className="font-mono text-[8px] uppercase tracking-wider text-[#8C5A3C] font-bold">{label}</span>
// //       </div>
// //       <p className="text-[11px] text-[#2C1810] leading-snug">{value}</p>
// //     </div>
// //   );
// // }

// // function GraphView({ graph }) {
// //   const nodes = graph?.nodes || [];
// //   const edges = graph?.edges || [];

// //   if (!nodes.length && !edges.length) {
// //     return (
// //       <p className="text-[12px] text-[#5D4037]">
// //         No graph data returned for this case.
// //       </p>
// //     );
// //   }

// //   return (
// //     <div className="space-y-4">
// //       <div className="flex items-center justify-between rounded-lg bg-[#FAF8F5] border border-[#2C1810]/10 px-4 py-3">
// //         <div>
// //           <p className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold">Graph Summary</p>
// //           <p className="text-[12px] text-[#2C1810] mt-1">
// //             {nodes.length} nodes, {edges.length} edges
// //           </p>
// //         </div>
// //       </div>

// //       {nodes.length > 0 && (
// //         <div>
// //           <p className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold mb-2">
// //             Nodes
// //           </p>
// //           <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
// //             {nodes.map((node) => {
// //               const props = node.properties || {};
// //               const labelValue =
// //                 props.name ||
// //                 props.summary ||
// //                 props.description ||
// //                 props.session_id ||
// //                 node.id;

// //               return (
// //                 <div key={node.id} className="rounded-lg border border-[#2C1810]/10 bg-[#FAF8F5] p-3">
// //                   <div className="flex items-center justify-between gap-2 mb-2">
// //                     <span className="px-2 py-1 rounded-md bg-[#2C1810] text-[#FAF8F5] font-mono text-[10px] font-bold">
// //                       {node.label}
// //                     </span>
// //                     <span className="font-mono text-[9px] text-[#8C5A3C] break-all">
// //                       {node.id}
// //                     </span>
// //                   </div>
// //                   <p className="text-[12px] text-[#2C1810] leading-relaxed">
// //                     {labelValue}
// //                   </p>
// //                 </div>
// //               );
// //             })}
// //           </div>
// //         </div>
// //       )}

// //       {edges.length > 0 && (
// //         <div>
// //           <p className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold mb-2">
// //             Edges
// //           </p>
// //           <div className="space-y-2">
// //             {edges.map((edge, idx) => (
// //               <div key={`${edge.source}-${edge.target}-${idx}`} className="rounded-lg border border-[#2C1810]/10 bg-white px-4 py-3">
// //                 <div className="flex flex-wrap items-center gap-2 text-[11px] text-[#2C1810]">
// //                   <span className="font-mono text-[10px] text-[#8C5A3C] break-all">{edge.source}</span>
// //                   <span className="text-[#D4AF37] font-bold">→</span>
// //                   <span className="font-mono text-[10px] text-[#8C5A3C] break-all">{edge.target}</span>
// //                 </div>
// //                 <div className="mt-1 flex flex-wrap items-center gap-2">
// //                   <span className="px-2 py-1 rounded-md bg-[#FFF8E1] text-[#8C5A3C] font-mono text-[10px] font-bold uppercase tracking-wider">
// //                     {edge.type}
// //                   </span>
// //                   {edge.properties && Object.keys(edge.properties).length > 0 && (
// //                     <span className="text-[10px] text-[#5D4037]">
// //                       {JSON.stringify(edge.properties)}
// //                     </span>
// //                   )}
// //                 </div>
// //               </div>
// //             ))}
// //           </div>
// //         </div>
// //       )}
// //     </div>
// //   );
// // } 
// import { useState, useEffect, useRef, useMemo } from "react";
// import { sampleCases } from "../data/mockEvidenceData";
// import {
//   FileText,
//   Upload,
//   Search,
//   Shield,
//   Check,
//   AlertTriangle,
//   Scale,
//   Users,
//   MapPin,
//   Calendar,
//   Briefcase,
//   Layers,
//   ArrowLeft,
//   History,
//   RefreshCw,
// } from "lucide-react";
// import ForceGraph2D from "react-force-graph-2d";
// import StandardNavbar from "../components/StandardNavbar";

// // ─── Progress Steps ──────────────────────────────────────────────
// const STEPS = [
//   { id: "upload", label: "Upload Document", icon: Upload },
//   { id: "ocr", label: "OCR Extraction", icon: Search },
//   { id: "analysis", label: "AI Analysis", icon: Scale },
//   { id: "results", label: "Structured Output", icon: Layers },
// ];

// export default function EvidenceAnalyzerPage({ onBack }) {
//   const [selectedCase, setSelectedCase] = useState(null);
//   const [currentStep, setCurrentStep] = useState(0); // 0=upload, 1=ocr, 2=analysis, 3=results
//   const [ocrProgress, setOcrProgress] = useState(0);
//   const [analysisProgress, setAnalysisProgress] = useState(0);
//   const [displayedText, setDisplayedText] = useState("");
//   const [showFacts, setShowFacts] = useState(false);
//   const [historyItems, setHistoryItems] = useState([]);
//   const [historyLoading, setHistoryLoading] = useState(false);
//   const [historyError, setHistoryError] = useState(null);
//   const [selectedHistoryId, setSelectedHistoryId] = useState(null);

//   const [error, setError] = useState(null);
//   const fileInputRef = useRef(null);

//   const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

//   const normalizeSessionPayload = (payload, fallbackSessionId = null) => {
//     const rawText = payload?.rawText || payload?.raw_text || "";
//     const facts = payload?.facts || null;
//     const timeline = payload?.timeline || [];
//     const graph = payload?.graph || { nodes: [], edges: [] };

//     return {
//       id: payload?.session_id || payload?.sessionId || fallbackSessionId || `session_${Date.now()}`,
//       filename: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
//       label: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
//       description: payload?.facts?.incident?.summary || "Stored evidence analysis session",
//       rawText,
//       facts,
//       timeline,
//       graph,
//     };
//   };

//   const fetchHistory = async () => {
//     setHistoryLoading(true);
//     setHistoryError(null);
//     try {
//       const response = await fetch(`${apiUrl}/api/evidence/history?limit=25`);
//       const res = await response.json();
//       if (!response.ok || !res.success) {
//         throw new Error(res.message || `Failed to load history (${response.status})`);
//       }
//       setHistoryItems(res.data || []);
//     } catch (err) {
//       setHistoryError(err.message || "Failed to load history.");
//     } finally {
//       setHistoryLoading(false);
//     }
//   };

//   const openHistorySession = async (sessionId) => {
//     setHistoryError(null);
//     setSelectedHistoryId(sessionId);
//     try {
//       const response = await fetch(`${apiUrl}/api/evidence/history/${sessionId}`);
//       const res = await response.json();
//       if (!response.ok || !res.success) {
//         throw new Error(res.message || `Failed to load session (${response.status})`);
//       }
//       const sessionCase = normalizeSessionPayload(res.data, sessionId);
//       setSelectedCase(sessionCase);
//       setOcrProgress(100);
//       setAnalysisProgress(100);
//       setCurrentStep(3);
//       setShowFacts(true);
//       await fetchHistory();
//     } catch (err) {
//       setHistoryError(err.message || "Failed to load session.");
//     } finally {
//       setSelectedHistoryId(null);
//     }
//   };

//   useEffect(() => {
//     fetchHistory();
//   }, []);

//   const handleFileUpload = (e) => {
//     const file = e.target.files?.[0];
//     if (!file) return;

//     setError(null);
//     setSelectedCase({
//       id: `uploaded_${Date.now()}`,
//       filename: file.name,
//       label: `Uploaded — ${file.name}`,
//       description: "Processing case document via backend intelligence pipeline...",
//       rawText: "",
//       facts: null,
//       timeline: [],
//       graph: { nodes: [], edges: [] },
//     });
//     setCurrentStep(1);
//     setOcrProgress(0);
//     setAnalysisProgress(0);
//     setDisplayedText("");
//     setShowFacts(false);
//     setSelectedHistoryId(null);

//     const xhr = new XMLHttpRequest();
//     const formData = new FormData();
//     formData.append("file", file);

//     xhr.open("POST", `${apiUrl}/api/evidence/analyze`, true);

//     xhr.upload.onprogress = (event) => {
//       if (event.lengthComputable) {
//         const percentComplete = Math.round((event.loaded / event.total) * 100);
//         setOcrProgress(Math.min(90, Math.round(percentComplete * 0.9)));
//       }
//     };

//     xhr.onload = () => {
//       if (xhr.status >= 200 && xhr.status < 300) {
//         try {
//           const res = JSON.parse(xhr.responseText);
//           if (res.success) {
//             setOcrProgress(100);
//             const { rawText, facts, timeline = [], graph = { nodes: [], edges: [] } } = res.data;
            
//             setDisplayedText(rawText);
//             setCurrentStep(2);
            
//             let prog = 0;
//             const interval = setInterval(() => {
//               prog += Math.random() * 15 + 10;
//               if (prog >= 100) {
//                 prog = 100;
//                 clearInterval(interval);
//                 setAnalysisProgress(100);
//                 setTimeout(() => {
//                   setSelectedCase((prev) => ({
//                     ...prev,
//                     id: res.data.sessionId || prev?.id,
//                     rawText,
//                     facts,
//                     timeline,
//                     graph,
//                   }));
//                   setCurrentStep(3);
//                   setShowFacts(true);
//                   fetchHistory();
//                 }, 600);
//               } else {
//                 setAnalysisProgress(Math.min(prog, 100));
//               }
//             }, 150);
//           } else {
//             setError(res.message || "Analysis failed.");
//             setCurrentStep(0);
//             setSelectedCase(null);
//           }
//         } catch (err) {
//           setError("Failed to parse API response.");
//           setCurrentStep(0);
//           setSelectedCase(null);
//         }
//       } else {
//         try {
//           const res = JSON.parse(xhr.responseText);
//           setError(res.message || `Error ${xhr.status}: ${xhr.statusText}`);
//         } catch (err) {
//           setError(`Server returned status code ${xhr.status}`);
//         }
//         setCurrentStep(0);
//         setSelectedCase(null);
//       }
//     };

//     xhr.onerror = () => {
//       setError("Network connection failed. Make sure the backend server is running.");
//       setCurrentStep(0);
//       setSelectedCase(null);
//     };

//     xhr.send(formData);
//   };

//   const startAnalysis = (caseData) => {
//     setSelectedCase(caseData);
//     setCurrentStep(1);
//     setOcrProgress(0);
//     setAnalysisProgress(0);
//     setDisplayedText("");
//     setShowFacts(false);
//     setSelectedHistoryId(null);

//     let charIdx = 0;
//     const rawText = caseData.rawText || "";
//     const charsPerTick = 12;

//     const ocrInterval = setInterval(() => {
//       charIdx += charsPerTick;
//       if (charIdx >= rawText.length) {
//         charIdx = rawText.length;
//         clearInterval(ocrInterval);
//         setOcrProgress(100);
//         setDisplayedText(rawText);

//         setTimeout(() => {
//           setCurrentStep(2);
//           let prog = 0;
//           const analysisInterval = setInterval(() => {
//             prog += Math.random() * 8 + 2;
//             if (prog >= 100) {
//               prog = 100;
//               clearInterval(analysisInterval);
//               setAnalysisProgress(100);
//               setTimeout(() => {
//                 setCurrentStep(3);
//                 setShowFacts(true);
//               }, 600);
//             }
//             setAnalysisProgress(Math.min(prog, 100));
//           }, 120);
//         }, 800);
//       }
//       setDisplayedText(rawText.slice(0, charIdx));
//       setOcrProgress(Math.round((charIdx / rawText.length) * 100));
//     }, 18);
//   };

//   useEffect(() => {
//     fetchHistory();
//   }, []);
//   const facts = selectedCase?.facts;
//   const timeline = selectedCase?.timeline || [];
//   const graph = selectedCase?.graph || { nodes: [], edges: [] };

//   return (
//     <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810]">
//       <StandardNavbar onBack={onBack} title="Evidence Analyzer" subtitle="Demo Mode" />

//       <div className="pt-6 max-w-[1400px] mx-auto px-6 pb-24">
//         {/* ─── Progress Steps Bar ────────────────────────────────── */}
//         <div className="flex items-center justify-center gap-2 md:gap-4 py-8">
//           {STEPS.map((step, i) => {
//             const Icon = step.icon;
//             const isActive = i === currentStep;
//             const isDone = i < currentStep;
//             return (
//               <div key={step.id} className="flex items-center gap-2 md:gap-4">
//                 <div className={`flex items-center gap-2 px-4 py-2 rounded-full border transition-all duration-500 ${
//                   isDone
//                     ? "bg-[#2C1810] text-[#FAF8F5] border-[#D4AF37]"
//                     : isActive
//                     ? "bg-white text-[#2C1810] border-[#D4AF37] shadow-md"
//                     : "bg-transparent text-[#2C1810]/30 border-[#2C1810]/10"
//                 }`}>
//                   {isDone ? (
//                     <Check size={14} strokeWidth={3} />
//                   ) : (
//                     <Icon size={14} strokeWidth={isActive ? 2.5 : 1.5} />
//                   )}
//                   <span className="text-[10px] font-bold uppercase tracking-wider hidden md:inline">
//                     {step.label}
//                   </span>
//                 </div>
//                 {i < STEPS.length - 1 && (
//                   <div className={`w-8 md:w-16 h-px transition-colors duration-500 ${
//                     i < currentStep ? "bg-[#D4AF37]" : "bg-[#2C1810]/10"
//                   }`} />
//                 )}
//               </div>
//             );
//           })}
//         </div>

//         {/* ─── Step 0: File Selection ────────────────────────────── */}
//         {currentStep === 0 && (
//           <div className="max-w-3xl mx-auto">
//             <div className="text-center mb-12">
//               <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#D4AF37] font-bold mb-3 block">
//                 Document Intelligence Pipeline
//               </span>
//               <h1 className="font-heading text-3xl md:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
//                 Evidence Analyzer
//               </h1>
//               <p className="font-body text-sm md:text-base text-[#5D4037] max-w-xl mx-auto leading-relaxed">
//                 Upload an FIR, charge sheet, or legal document. The AI pipeline extracts structured facts
//                 using OCR and multi-pass language model analysis.
//               </p>
//             </div>

//             {error && (
//               <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 text-red-800 animate-[fadeIn_0.3s_ease-out]">
//                 <AlertTriangle size={18} className="text-red-600 shrink-0 mt-0.5" />
//                 <div className="text-xs">
//                   <p className="font-bold">Error Processing Document</p>
//                   <p className="mt-0.5 opacity-90">{error}</p>
//                 </div>
//               </div>
//             )}

//             <div 
//               onClick={() => fileInputRef.current && fileInputRef.current.click()}
//               className="border-2 border-dashed border-[#D4AF37]/40 rounded-xl p-8 md:p-12 bg-white/60 hover:bg-white hover:border-[#D4AF37] transition-all mb-8 text-center cursor-pointer group"
//             >
//               <input
//                 ref={fileInputRef}
//                 type="file"
//                 className="hidden"
//                 onChange={handleFileUpload}
//                 accept="application/pdf,image/*"
//               />
//               <Upload size={36} className="mx-auto mb-4 text-[#D4AF37] group-hover:scale-110 transition-transform" strokeWidth={1.5} />
//               <p className="font-heading text-lg font-bold text-[#2C1810] mb-1">
//                 Drop your document here
//               </p>
//               <p className="text-xs text-[#5D4037]">
//                 Supports PDF, PNG, JPG, TIFF — up to 50MB
//               </p>
//             </div>

//             <div className="mb-8 bg-white border border-[#2C1810]/10 rounded-xl p-5 shadow-sm">
//               <div className="flex items-center justify-between gap-3 mb-4">
//                 <div>
//                   <div className="flex items-center gap-2">
//                     <History size={14} className="text-[#D4AF37]" />
//                     <p className="font-heading font-bold text-sm text-[#2C1810]">OCR History</p>
//                   </div>
//                   <p className="text-[11px] text-[#5D4037] mt-1">
//                     Open any previously analyzed document to review OCR text, timeline, and graph.
//                   </p>
//                 </div>
//                 <button
//                   onClick={fetchHistory}
//                   className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[#2C1810]/10 text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:border-[#D4AF37] hover:text-[#D4AF37] transition-colors"
//                 >
//                   <RefreshCw size={12} className={historyLoading ? "animate-spin" : ""} />
//                   Refresh
//                 </button>
//               </div>

//               {historyError && (
//                 <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
//                   {historyError}
//                 </div>
//               )}

//               <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
//                 {historyLoading && historyItems.length === 0 && (
//                   <div className="text-xs text-[#5D4037]">Loading history...</div>
//                 )}
//                 {!historyLoading && historyItems.length === 0 && !historyError && (
//                   <div className="text-xs text-[#5D4037]">No saved OCR sessions yet.</div>
//                 )}
//                 {historyItems.map((item) => (
//                   <button
//                     key={item.session_id}
//                     onClick={() => openHistorySession(item.session_id)}
//                     disabled={selectedHistoryId === item.session_id}
//                     className={`w-full text-left rounded-lg border p-4 transition-all ${
//                       selectedCase?.id === item.session_id
//                         ? "border-[#D4AF37] bg-[#FFF8E1]"
//                         : "border-[#2C1810]/10 bg-[#FAF8F5] hover:border-[#D4AF37] hover:bg-white"
//                     }`}
//                   >
//                     <div className="flex items-start justify-between gap-3">
//                       <div className="min-w-0">
//                         <div className="flex items-center gap-2 flex-wrap">
//                           <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C]">
//                             {item.session_id}
//                           </span>
//                           <span className="px-2 py-1 rounded-md bg-[#2C1810] text-[#FAF8F5] font-mono text-[9px] font-bold uppercase tracking-wider">
//                             {item.timeline_count || 0} events
//                           </span>
//                         </div>
//                         <p className="mt-2 text-[12px] font-semibold text-[#2C1810] truncate">
//                           {item.incident_summary || "No incident summary available"}
//                         </p>
//                         <p className="mt-1 text-[11px] text-[#5D4037]">
//                           {item.incident_date || "No date"}{item.incident_place ? ` • ${item.incident_place}` : ""}
//                         </p>
//                       </div>
//                       <span className="text-[10px] text-[#8C5A3C] font-mono whitespace-nowrap">
//                         {item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown time"}
//                       </span>
//                     </div>
//                   </button>
//                 ))}
//               </div>
//             </div>

//             <div className="space-y-4">
//               <p className="text-xs font-bold uppercase tracking-widest text-[#8C5A3C] mb-2">
//                 Sample Case Files
//               </p>
//               {sampleCases.map((c) => (
//                 <button
//                   key={c.id}
//                   onClick={() => startAnalysis(c)}
//                   className="w-full text-left bg-white border border-[#2C1810]/10 p-5 rounded-lg hover:border-[#D4AF37] hover:shadow-md hover:-translate-y-[1px] transition-all group"
//                 >
//                   <div className="flex items-start gap-4">
//                     <div className="w-10 h-10 rounded-lg bg-[#FAF8F5] border border-[#D4AF37]/30 flex items-center justify-center text-[#D4AF37] shrink-0 group-hover:bg-[#D4AF37]/10 transition-colors">
//                       <FileText size={18} strokeWidth={1.5} />
//                     </div>
//                     <div className="flex-1 min-w-0">
//                       <h3 className="font-heading font-bold text-sm text-[#2C1810] mb-1">
//                         {c.label}
//                       </h3>
//                       <p className="text-xs text-[#5D4037] leading-relaxed">
//                         {c.description}
//                       </p>
//                     </div>
//                     <ArrowLeft size={14} className="rotate-180 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-opacity mt-3" />
//                   </div>
//                 </button>
//               ))}
//             </div>
//           </div>
//         )}

//         {/* ─── Steps 1-3: Processing & Results ───────────────────── */}
//         {currentStep > 0 && selectedCase && (
//           <div className="flex flex-col lg:flex-row gap-6 h-[750px] relative overflow-hidden">
            
//             {/* MAIN CONTENT AREA */}
//             <div className="flex-1 flex flex-col min-w-0 transition-all duration-300">
              
//               {/* Waiting for OCR */}
//               {currentStep === 1 && (
//                 <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-full">
//                   <Search size={36} className="text-[#D4AF37] mb-4 animate-pulse" strokeWidth={1.5} />
//                   <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
//                     Extracting Text
//                   </h3>
//                   <p className="text-xs text-[#5D4037] text-center max-w-sm">
//                     Processing document pages. OCR progress is tracked here while the analysis runs.
//                   </p>
//                 </div>
//               )}

//               {/* Analysis in progress */}
//               {currentStep === 2 && (
//                 <div className="bg-white border border-[#2C1810]/10 rounded-xl p-8 flex flex-col items-center justify-center h-full">
//                   <div className="w-20 h-20 rounded-full border-4 border-[#D4AF37]/30 border-t-[#D4AF37] animate-spin mb-8" />
//                   <h3 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
//                     Analyzing Document
//                   </h3>
//                   <p className="text-xs text-[#5D4037] mb-6 text-center max-w-sm">
//                     Multi-pass LLM extraction in progress. Identifying parties, incident details, timeline events, and relationship graphs...
//                   </p>
//                   <div className="w-full max-w-xs">
//                     <div className="h-2 bg-[#2C1810]/10 rounded-full overflow-hidden">
//                       <div
//                         className="h-full bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] rounded-full transition-all duration-200"
//                         style={{ width: `${analysisProgress}%` }}
//                       />
//                     </div>
//                   </div>
//                 </div>
//               )}

//               {/* Results Dashboard */}
//               {currentStep === 3 && showFacts && facts && (
//                 <div className="bg-white border border-[#2C1810]/10 rounded-xl overflow-hidden h-full flex flex-col relative shadow-sm">
                  
//                   {/* Header */}
//                   <div className="bg-[#2C1810] text-[#FAF8F5] px-5 py-3 flex items-center justify-between z-10">
//                     <div className="flex items-center gap-2">
//                       <Shield size={14} />
//                       <span className="font-mono text-[10px] uppercase tracking-wider font-bold">
//                         Intelligence Dashboard
//                       </span>
//                     </div>
//                     <span className="font-mono text-[9px] text-green-400 flex items-center gap-1 hidden sm:flex">
//                       <Check size={10} strokeWidth={3} /> Verified Extraction
//                     </span>
//                   </div>

//                   {/* Scrollable Body */}
//                   <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-[#FAF8F5]/30">
                    
//                     {/* Visual Timeline Section */}
//                     <div>
//                       <h3 className="font-heading font-bold text-lg text-[#2C1810] border-b border-[#2C1810]/10 pb-2 mb-6 flex items-center gap-2">
//                         <Calendar size={18} className="text-[#D4AF37]" /> Case Timeline
//                       </h3>
//                       <VisualTimeline timeline={timeline} />
//                     </div>

//                     {/* Interactive Graph Section */}
//                     <div>
//                       <h3 className="font-heading font-bold text-lg text-[#2C1810] border-b border-[#2C1810]/10 pb-2 mb-6 flex items-center gap-2">
//                         <Layers size={18} className="text-[#D4AF37]" /> Entity Graph
//                       </h3>
//                       <div className="border border-[#2C1810]/10 rounded-xl bg-white h-[450px] overflow-hidden shadow-inner">
//                         <NetworkGraph graph={graph} />
//                       </div>
//                     </div>

//                     {/* Extracted Entities Cards */}
//                     <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
//                         <FactCard title="Parties Identified" icon={<Users size={16} />} isOpen={true}>
//                           <FactRow label="Complainant" value={facts.who.complainant} />
//                           <FactRow label="Accused" value={facts.who.accused?.join(", ") || "—"} highlight />
//                           <FactRow label="Victims" value={facts.who.victims?.join(", ") || "—"} />
//                         </FactCard>
                        
//                         <FactCard title="Property & Loss" icon={<Briefcase size={16} />} isOpen={true}>
//                           {facts.property.vehicles?.map((v, i) => (
//                               <FactRow key={i} label="Vehicle" value={`${v.make_model} (${v.registration_no})`} />
//                           ))}
//                           <FactRow label="Est. Loss" value={facts.property.estimated_loss} highlight />
//                         </FactCard>

//                         <FactCard title="Incident Summary" icon={<AlertTriangle size={16} />} isOpen={true}>
//                           <FactRow label="Details" value={facts.incident.summary} />
//                           <FactRow label="Location" value={facts.incident.place} />
//                           <FactRow label="Applicable IPC" value={facts.sections?.join(", ")} highlight />
//                         </FactCard>
//                     </div>
//                   </div>
                  
//                   {/* Reset Button Footer */}
//                   <div className="bg-[#FAF8F5] border-t border-[#2C1810]/10 px-5 py-3 flex items-center justify-between">
//                     <span className="font-mono text-[9px] text-[#8C5A3C] font-bold uppercase tracking-wider">
//                       Processing Complete
//                     </span>
//                     <button
//                       onClick={() => {
//                         setSelectedCase(null);
//                         setCurrentStep(0);
//                       }}
//                       className="text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:text-[#D4AF37] transition-colors flex items-center gap-1"
//                     >
//                       Analyze Another Case
//                       <ArrowLeft size={12} className="rotate-180" />
//                     </button>
//                   </div>
//                 </div>
//               )}
//             </div>

//           </div>
//         )}
//       </div>
//     </div>
//   );
// }

// // ─── Visual Timeline Component ─────────────────────────────
// function VisualTimeline({ timeline }) {
//   if (!timeline || timeline.length === 0) return <p className="text-sm text-gray-500">No timeline data.</p>;

//   return (
//     <div className="relative border-l-2 border-[#D4AF37]/50 ml-4 space-y-8 py-2">
//       {timeline.map((event, idx) => (
//         <div key={event.event_id || idx} className="relative pl-8 pr-4 group">
//           {/* Node Dot */}
//           <div className="absolute -left-[9px] top-1.5 w-4 h-4 rounded-full bg-white border-2 border-[#D4AF37] group-hover:bg-[#D4AF37] transition-colors" />
          
//           <div className="bg-white border border-[#2C1810]/10 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
//             <div className="flex flex-wrap items-center gap-3 mb-2">
//               <span className="px-2 py-1 bg-[#FAF8F5] text-[#8C5A3C] font-mono text-[10px] font-bold border border-[#2C1810]/5 rounded">
//                 {event.date} {event.time && `• ${event.time}`}
//               </span>
//               <span className="px-2 py-1 rounded-md bg-[#FFF8E1] text-[#8C5A3C] font-mono text-[9px] font-bold uppercase tracking-wider">
//                 {event.event_type.replace(/_/g, ' ')}
//               </span>
//             </div>
            
//             <p className="text-[13px] text-[#2C1810] leading-relaxed mb-3">
//               {event.description}
//             </p>
            
//             {/* Metadata Tags */}
//             <div className="flex flex-wrap gap-2">
//               {event.actors?.length > 0 && (
//                 <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
//                   <Users size={10} /> {event.actors.join(", ")}
//                 </div>
//               )}
//               {event.location && (
//                 <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
//                   <MapPin size={10} /> {event.location}
//                 </div>
//               )}
//             </div>
//           </div>
//         </div>
//       ))}
//     </div>
//   );
// }

// // ─── Neo4j-Style Interactive Graph ─────────────────────────
// function NetworkGraph({ graph }) {
//   const fgRef = useRef();

//   // Transform backend schema into react-force-graph expected schema (nodes & links)
//   const graphData = useMemo(() => {
//     if (!graph.nodes) return { nodes: [], links: [] };
    
//     const mappedNodes = graph.nodes.map(n => ({
//       id: n.id,
//       label: n.label,
//       name: n.properties.name || n.properties.registration_no || n.properties.summary || n.id,
//       val: n.label === 'Case' ? 3 : n.label === 'Person' ? 2 : 1.5,
//       color: 
//         n.label === 'Case' ? '#D4AF37' : 
//         n.label === 'Person' ? '#8C5A3C' : 
//         n.label === 'Location' ? '#4A5568' : '#718096'
//     }));

//     const mappedLinks = graph.edges.map(e => ({
//       source: e.source,
//       target: e.target,
//       label: e.type.replace(/_/g, ' ')
//     }));

//     return { nodes: mappedNodes, links: mappedLinks };
//   }, [graph]);

//   useEffect(() => {
//     // Zoom to fit on load
//     if (fgRef.current) {
//       setTimeout(() => {
//         fgRef.current.zoomToFit(400, 50);
//       }, 500);
//     }
//   }, [graphData]);

//   if (!graphData.nodes.length) return <p className="p-4 text-sm text-gray-500">No graph data.</p>;

//   return (
//     <div className="w-full h-full relative cursor-move">
//       <ForceGraph2D
//         ref={fgRef}
//         graphData={graphData}
//         nodeLabel="name"
//         nodeColor="color"
//         nodeRelSize={6}
//         linkColor={() => '#CBD5E0'}
//         linkDirectionalArrowLength={3.5}
//         linkDirectionalArrowRelPos={1}
//         linkCurvature={0.2}
//         linkLabel="label"
//         width={900} // You can dynamically calculate container size using a ResizeObserver for production
//         height={450}
//         backgroundColor="#FFFFFF"
//         nodeCanvasObject={(node, ctx, globalScale) => {
//           const label = node.name;
//           const fontSize = 12 / globalScale;
//           ctx.font = `${fontSize}px Sans-Serif`;
          
//           // Draw Node
//           ctx.beginPath();
//           ctx.arc(node.x, node.y, node.val * 3, 0, 2 * Math.PI, false);
//           ctx.fillStyle = node.color;
//           ctx.fill();
//           ctx.strokeStyle = '#fff';
//           ctx.lineWidth = 1 / globalScale;
//           ctx.stroke();

//           // Draw Text Label
//           ctx.textAlign = 'center';
//           ctx.textBaseline = 'top';
//           ctx.fillStyle = '#2C1810';
          
//           // Truncate long labels (e.g. Case summary)
//           const displayLabel = label.length > 25 ? label.substring(0, 25) + '...' : label;
//           ctx.fillText(displayLabel, node.x, node.y + (node.val * 3) + 2);
//         }}
//       />
//       <div className="absolute bottom-3 left-3 bg-white/80 px-2 py-1 rounded text-[10px] font-mono text-gray-500 pointer-events-none">
//         Scroll to zoom, drag to pan
//       </div>
//     </div>
//   );
// }

// // ─── Fact Cards ──────────────────────────────────────────────────
// function FactCard({ title, icon, isOpen, children }) {
//   if (!isOpen) return null;
//   return (
//     <div className="border border-[#2C1810]/10 rounded-lg overflow-hidden bg-white shadow-sm">
//       <div className="flex items-center gap-2.5 px-4 py-3 bg-[#FAF8F5] border-b border-[#2C1810]/5">
//         <span className="text-[#D4AF37]">{icon}</span>
//         <span className="font-heading font-bold text-sm text-[#2C1810]">{title}</span>
//       </div>
//       <div className="p-4 space-y-3">{children}</div>
//     </div>
//   );
// }

// function FactRow({ label, value, highlight }) {
//   if (!value) return null;
//   return (
//     <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
//       <span className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold shrink-0 sm:w-28 pt-0.5">
//         {label}
//       </span>
//       <span className={`text-[12px] leading-relaxed ${highlight ? "text-[#991B1B] font-semibold" : "text-[#2C1810]"}`}>
//         {value}
//       </span>
//     </div>
//   );
// }

import { useState, useEffect, useRef, useMemo } from "react";
import { sampleCases } from "../data/mockEvidenceData";
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
} from "lucide-react";
import ForceGraph2D from "react-force-graph-2d";
import StandardNavbar from "../components/StandardNavbar";

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

  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";

  const normalizeSessionPayload = (payload, fallbackSessionId = null) => {
    const rawText = payload?.rawText || payload?.raw_text || "";
    const facts = payload?.facts || null;
    const timeline = payload?.timeline || [];
    const graph = payload?.graph || { nodes: [], edges: [] };

    return {
      id: payload?.session_id || payload?.sessionId || fallbackSessionId || `session_${Date.now()}`,
      filename: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
      label: payload?.filename || payload?.source_filename || payload?.session_id || fallbackSessionId || "Evidence Session",
      description: payload?.facts?.incident?.summary || "Stored evidence analysis session",
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
      const response = await fetch(`${apiUrl}/api/evidence/history?limit=25`);
      const res = await response.json();
      if (!response.ok || !res.success) {
        throw new Error(res.message || `Failed to load history (${response.status})`);
      }
      setHistoryItems(res.data || []);
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
      const response = await fetch(`${apiUrl}/api/evidence/history/${sessionId}`);
      const res = await response.json();
      if (!response.ok || !res.success) {
        throw new Error(res.message || `Failed to load session (${response.status})`);
      }
      const sessionCase = normalizeSessionPayload(res.data, sessionId);
      setSelectedCase(sessionCase);
      setOcrProgress(100);
      setAnalysisProgress(100);
      setCurrentStep(3);
      setShowFacts(true);
      await fetchHistory();
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

  const startAnalysis = (caseData) => {
    setSelectedCase(caseData);
    setCurrentStep(1);
    setOcrProgress(0);
    setAnalysisProgress(0);
    setDisplayedText("");
    setShowFacts(false);
    setSelectedHistoryId(null);

    let charIdx = 0;
    const rawText = caseData.rawText || "";
    const charsPerTick = 12;

    const ocrInterval = setInterval(() => {
      charIdx += charsPerTick;
      if (charIdx >= rawText.length) {
        charIdx = rawText.length;
        clearInterval(ocrInterval);
        setOcrProgress(100);
        setDisplayedText(rawText);

        setTimeout(() => {
          setCurrentStep(2);
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

  const facts = selectedCase?.facts;
  const timeline = selectedCase?.timeline || [];
  const graph = selectedCase?.graph || { nodes: [], edges: [] };

  return (
    <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810]">
      <StandardNavbar onBack={onBack} subtitle="Demo Mode" title="Evidence Analyzer" />

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

            <div className="mb-8 bg-white border border-[#2C1810]/10 rounded-xl p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3 mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <History className="text-[#D4AF37]" size={14} />
                    <p className="font-heading font-bold text-sm text-[#2C1810]">OCR History</p>
                  </div>
                  <p className="text-[11px] text-[#5D4037] mt-1">
                    Open any previously analyzed document to review OCR text, timeline, and graph.
                  </p>
                </div>
                <button
                  onClick={fetchHistory}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[#2C1810]/10 text-[11px] font-bold uppercase tracking-wider text-[#2C1810] hover:border-[#D4AF37] hover:text-[#D4AF37] transition-colors"
                >
                  <RefreshCw className={historyLoading ? "animate-spin" : ""} size={12} />
                  Refresh
                </button>
              </div>

              {historyError && (
                <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  {historyError}
                </div>
              )}

              <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1">
                {historyLoading && historyItems.length === 0 && (
                  <div className="text-xs text-[#5D4037]">Loading history...</div>
                )}
                {!historyLoading && historyItems.length === 0 && !historyError && (
                  <div className="text-xs text-[#5D4037]">No saved OCR sessions yet.</div>
                )}
                {historyItems.map((item) => (
                  <button
                    key={item.session_id}
                    onClick={() => openHistorySession(item.session_id)}
                    disabled={selectedHistoryId === item.session_id}
                    className={`w-full text-left rounded-lg border p-4 transition-all ${
                      selectedCase?.id === item.session_id
                        ? "border-[#D4AF37] bg-[#FFF8E1]"
                        : "border-[#2C1810]/10 bg-[#FAF8F5] hover:border-[#D4AF37] hover:bg-white"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#8C5A3C]">
                            {item.session_id}
                          </span>
                          <span className="px-2 py-1 rounded-md bg-[#2C1810] text-[#FAF8F5] font-mono text-[9px] font-bold uppercase tracking-wider">
                            {item.timeline_count || 0} events
                          </span>
                        </div>
                        <p className="mt-2 text-[12px] font-semibold text-[#2C1810] truncate">
                          {item.incident_summary || "No incident summary available"}
                        </p>
                        <p className="mt-1 text-[11px] text-[#5D4037]">
                          {item.incident_date || "No date"}{item.incident_place ? ` • ${item.incident_place}` : ""}
                        </p>
                      </div>
                      <span className="text-[10px] text-[#8C5A3C] font-mono whitespace-nowrap">
                        {item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown time"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>

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
                    </div>
                    <ArrowLeft className="rotate-180 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-opacity mt-3" size={14} />
                  </div>
                </button>
              ))}
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

                    {/* Extracted Entities Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FactCard icon={<Users size={16} />} title="Parties Identified" isOpen={true}>
                          <FactRow label="Complainant" value={facts.who.complainant} />
                          <FactRow highlight label="Accused" value={facts.who.accused?.join(", ") || "—"} />
                          <FactRow label="Victims" value={facts.who.victims?.join(", ") || "—"} />
                        </FactCard>
                        
                        <FactCard icon={<Briefcase size={16} />} title="Property & Loss" isOpen={true}>
                          {facts.property.vehicles?.map((v, i) => (
                              <FactRow key={i} label="Vehicle" value={`${v.make_model} (${v.registration_no})`} />
                          ))}
                          <FactRow highlight label="Est. Loss" value={facts.property.estimated_loss} />
                        </FactCard>

                        <FactCard icon={<AlertTriangle size={16} />} title="Incident Summary" isOpen={true}>
                          <FactRow label="Details" value={facts.incident.summary} />
                          <FactRow label="Location" value={facts.incident.place} />
                          <FactRow highlight label="Applicable IPC" value={facts.sections?.join(", ")} />
                        </FactCard>
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
                {event.date} {event.time && `• ${event.time}`}
              </span>
              <span className="px-2 py-1 rounded-md bg-[#FFF8E1] text-[#8C5A3C] font-mono text-[9px] font-bold uppercase tracking-wider">
                {event.event_type.replace(/_/g, ' ')}
              </span>
            </div>
            
            <p className="text-[13px] text-[#2C1810] leading-relaxed mb-3">
              {event.description}
            </p>
            
            {/* Metadata Tags */}
            <div className="flex flex-wrap gap-2">
              {event.actors?.length > 0 && (
                <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
                  <Users size={10} /> {event.actors.join(", ")}
                </div>
              )}
              {event.location && (
                <div className="flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 px-2 py-1 rounded">
                  <MapPin size={10} /> {event.location}
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
function FactCard({ title, icon, isOpen, children }) {
  if (!isOpen) return null;
  return (
    <div className="border border-[#2C1810]/10 rounded-lg overflow-hidden bg-white shadow-sm">
      <div className="flex items-center gap-2.5 px-4 py-3 bg-[#FAF8F5] border-b border-[#2C1810]/5">
        <span className="text-[#D4AF37]">{icon}</span>
        <span className="font-heading font-bold text-sm text-[#2C1810]">{title}</span>
      </div>
      <div className="p-4 space-y-3">{children}</div>
    </div>
  );
}

function FactRow({ label, value, highlight }) {
  if (!value) return null;
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="font-mono text-[9px] uppercase tracking-wider text-[#8C5A3C] font-bold shrink-0 sm:w-28 pt-0.5">
        {label}
      </span>
      <span className={`text-[12px] leading-relaxed ${highlight ? "text-[#991B1B] font-semibold" : "text-[#2C1810]"}`}>
        {value}
      </span>
    </div>
  );
}
