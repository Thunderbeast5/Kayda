import { useState } from "react";
import { 
  X, 
  Network, 
  Lightbulb, 
  GitCommit, 
  BookOpen, 
  AlertTriangle, 
  FileText, 
  FolderCheck, 
  Scale, 
  Check, 
  Calendar,
  Layers
} from "lucide-react";

export default function CourtroomSidebar({
  sidebarOpen,
  setSidebarOpen,
  sidebarCollapsed,
  onExit,
  caseData = {},
  onOpenCaseModal,
  uploadStatus,
  uploadProgress,
  uploadedFileName,
  latestMessage,
  status
}) {
  const [activeTab, setActiveTab] = useState("brief"); // "brief" | "facts" | "evidence" | "lexigraph"
  const [factFilter, setFactFilter] = useState("all"); // "all" | "allegation" | "procedural_event" | "court_finding"

  const facts = caseData.case_facts || [];
  const inventory = caseData.evidence_inventory || [];

  const filteredFacts = factFilter === "all" 
    ? facts 
    : facts.filter(f => (f.type || "allegation") === factFilter);

  // Determine legal regime based on charge / filing
  const isOldRegime = caseData.charge?.includes("438") || 
                      caseData.firNo?.includes("2020") || 
                      caseData.firNo?.includes("2021") || 
                      caseData.firNo?.includes("2022") || 
                      caseData.firNo?.includes("2023");

  return (
    <>
      {/* MOBILE OVERLAY */}
      {sidebarOpen && (
        <div 
          className="absolute inset-0 bg-black/40 z-40 md:hidden backdrop-blur-sm" 
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* LEFT PANEL */}
      <div className={`fixed md:relative top-0 left-0 h-full flex-shrink-0 flex flex-col gap-3 bg-white shadow-2xl md:shadow-xl transition-all duration-[350ms] ease-in-out z-50 ${
        sidebarCollapsed 
          ? 'w-0 p-0 lg:p-0 border-r-0 opacity-0 overflow-hidden pointer-events-none' 
          : 'w-[300px] md:w-[340px] lg:w-[380px] p-4 lg:p-5 border-r border-surface-border opacity-100 overflow-y-auto'
      } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
        
        {/* Brand Header */}
        <div className="flex justify-between items-center z-10 pb-2 border-b border-surface-border">
          <div>
            <h1 
              className="text-lg lg:text-[22px] font-heading font-extrabold text-wood-dark tracking-tight leading-snug cursor-pointer" 
              onClick={onExit}
            >
              Kayda
            </h1>
            <span className="text-[9px] font-mono text-[#8C5A3C] uppercase tracking-wider font-bold">
              Autonomous Courtroom Engine
            </span>
          </div>
          <div className="flex items-center gap-2">
            {onOpenCaseModal && (
              <button
                onClick={onOpenCaseModal}
                className="text-[9px] font-bold uppercase tracking-wider text-[#FAF8F5] bg-[#2C1810] hover:bg-[#8C5A3C] border border-[#D4AF37]/50 px-2.5 py-1 rounded transition-all cursor-pointer shadow-2xs flex items-center gap-1"
                title="Open Case Bank"
              >
                Cases
              </button>
            )}
            <button 
              className="md:hidden relative p-1.5 border border-transparent text-wood-dark cursor-pointer" 
              onClick={() => setSidebarOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* CASE FILE CARD */}
        {uploadStatus ? (
          <div className="bg-[#FAF8F5] border border-[#D4AF37]/30 rounded-lg p-4 mt-2 shadow-inner animate-[pulse_1.5s_infinite]">
            <div className="flex items-center gap-2 text-[#D4AF37] font-black text-[9px] uppercase tracking-widest mb-3">
              <div className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] animate-ping" />
              {uploadStatus === "uploading" ? "Document Uploading" : "Parsing Legal Brief..."}
            </div>
            <div className="w-full bg-gray-200 h-1 rounded-full overflow-hidden mb-2">
              <div 
                className="bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] h-full transition-all duration-150" 
                style={{ width: `${uploadStatus === "uploading" ? uploadProgress : 100}%` }}
              />
            </div>
            <p className="font-mono text-[9px] text-[#8C5A3C] font-bold truncate">
              {uploadedFileName}
            </p>
          </div>
        ) : (
          <div className="bg-white shadow-[0_2px_10px_rgba(0,0,0,0.05)] rounded-xl border border-surface-border p-3.5 relative mt-1">
            <div className="flex justify-between items-center mb-1">
              <span className="text-[8px] md:text-[9px] font-mono font-black text-primaryBrown uppercase tracking-wider bg-[#FAF8F5] px-2 py-0.5 rounded border border-[#2C1810]/10">
                Case #{caseData.fileId || "1"}
              </span>
              <span className="text-[8px] font-mono font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                RECORD VERIFIED
              </span>
            </div>

            <h2 className="font-heading font-bold my-1 text-[13px] md:text-[15px] leading-tight text-wood-dark">
              {caseData.title || "State of Bihar vs. Srikant Upadhyay"}
            </h2>

            <ul className="text-[11px] space-y-1.5 text-textPrimary/90 font-mono mt-2">
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                <span className="font-bold text-textMuted uppercase text-[8px] tracking-widest">FIR / Docket</span> 
                <span className="font-semibold">{caseData.firNo || "FIR 79/2020"}</span>
              </li>
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                <span className="font-bold text-textMuted uppercase text-[8px] tracking-widest">Charges</span> 
                <span className="font-bold text-semantic-criticalText text-right max-w-[190px] truncate" title={caseData.charge}>
                  {caseData.charge || "CrPC 438 / IPC 354B, 379"}
                </span>
              </li>
            </ul>

            {/* Legal Regime Indicator */}
            <div className="mt-2.5 pt-2 border-t border-[#2C1810]/10 flex items-center gap-1.5 text-[9.5px] font-mono">
              <Calendar size={12} className="text-[#8C5A3C] shrink-0" />
              <span className="font-bold text-[#8C5A3C]">
                {isOldRegime ? "Pre-July 1, 2024: CrPC § 438 / IPC" : "Post-July 1, 2024: BNSS § 482 / BNS"}
              </span>
            </div>
          </div>
        )}

        {/* TABS NAVIGATION */}
        <div className="flex border-b border-surface-border text-[10px] font-mono uppercase font-bold tracking-wider pt-1">
          <button
            onClick={() => setActiveTab("brief")}
            className={`flex-1 py-1.5 text-center cursor-pointer border-b-2 transition-all ${
              activeTab === "brief" 
                ? "border-[#D4AF37] text-[#2C1810] font-black bg-[#FAF8F5]" 
                : "border-transparent text-textMuted hover:text-[#2C1810]"
            }`}
          >
            Brief
          </button>
          <button
            onClick={() => setActiveTab("facts")}
            className={`flex-1 py-1.5 text-center cursor-pointer border-b-2 transition-all ${
              activeTab === "facts" 
                ? "border-[#D4AF37] text-[#2C1810] font-black bg-[#FAF8F5]" 
                : "border-transparent text-textMuted hover:text-[#2C1810]"
            }`}
          >
            Facts ({facts.length})
          </button>
          <button
            onClick={() => setActiveTab("evidence")}
            className={`flex-1 py-1.5 text-center cursor-pointer border-b-2 transition-all ${
              activeTab === "evidence" 
                ? "border-[#D4AF37] text-[#2C1810] font-black bg-[#FAF8F5]" 
                : "border-transparent text-textMuted hover:text-[#2C1810]"
            }`}
          >
            Evidence ({inventory.length})
          </button>
          <button
            onClick={() => setActiveTab("lexigraph")}
            className={`flex-1 py-1.5 text-center cursor-pointer border-b-2 transition-all ${
              activeTab === "lexigraph" 
                ? "border-[#D4AF37] text-[#2C1810] font-black bg-[#FAF8F5]" 
                : "border-transparent text-textMuted hover:text-[#2C1810]"
            }`}
          >
            LexiGraph
          </button>
        </div>

        {/* TAB 1: BRIEF & COACHING */}
        {activeTab === "brief" && (
          <div className="space-y-3 animate-fadeIn">
            {/* Live turn citations */}
            <div className="bg-white p-3 rounded-lg border border-surface-border flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5 text-primaryBrown border-b border-surface-border pb-1.5">
                <Network size={13} strokeWidth={2.5} />
                <span className="font-heading font-extrabold text-[10px] uppercase tracking-wider">
                  Active Turn Citations
                </span>
              </div>
              <div className="min-h-[50px] flex items-center justify-center py-1">
                {latestMessage?.citations?.length > 0 ? (
                  <div className="flex flex-wrap items-center justify-center gap-1.5">
                    {latestMessage.citations.map((c, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 border border-gold rounded-full bg-white text-[9px] font-bold font-mono text-wood-dark shadow-2xs"
                      >
                        § {c}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-[9px] text-textMuted font-mono">
                    {latestMessage ? "No citations in this turn" : "Awaiting courtroom arguments..."}
                  </p>
                )}
              </div>
            </div>

            {/* Legal Guidance */}
            <div className="bg-gradient-to-br from-[#E3F2FD] to-[#f4faff] border border-[#90CAF9] p-3.5 font-body rounded-lg shadow-2xs">
              <div className="flex items-center gap-2 text-[#0D47A1] font-black text-[9.5px] uppercase tracking-widest mb-2">
                <Lightbulb size={13} className="fill-[#90CAF9]" /> Legal Bench Principles
              </div>
              <div className="text-[11px] text-[#0D47A1] leading-relaxed space-y-2">
                <p className="flex items-start gap-1.5 font-medium">
                  <GitCommit size={13} className="mt-0.5 shrink-0 text-blue-500" />
                  <span><strong>Sec. 82 Proclamation:</strong> Prior non-bailable warrants and absconding bar anticipatory bail under <em>Srikant Upadhyay</em>.</span>
                </p>
                <p className="flex items-start gap-1.5 font-medium">
                  <GitCommit size={13} className="mt-0.5 shrink-0 text-blue-500" />
                  <span><strong>Paragraph 24 Exception:</strong> Extraordinary relief available only where coercive process was issued without jurisdiction or maliciously.</span>
                </p>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: FACTS */}
        {activeTab === "facts" && (
          <div className="space-y-2 animate-fadeIn">
            {/* Fact filter pills */}
            <div className="flex flex-wrap gap-1 text-[8px] font-mono uppercase">
              {["all", "allegation", "procedural_event", "court_finding"].map((f) => (
                <button
                  key={f}
                  onClick={() => setFactFilter(f)}
                  className={`px-2 py-0.5 rounded cursor-pointer border ${
                    factFilter === f 
                      ? "bg-[#2C1810] text-white border-[#2C1810]" 
                      : "bg-[#FAF8F5] text-slate-700 border-slate-200"
                  }`}
                >
                  {f.replace("_", " ")}
                </button>
              ))}
            </div>

            <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-1">
              {filteredFacts.length > 0 ? (
                filteredFacts.map((fact, idx) => {
                  const ftype = fact.type || "allegation";
                  let tagClass = "text-amber-800 bg-amber-50 border-amber-200";
                  if (ftype === "procedural_event") tagClass = "text-sky-800 bg-sky-50 border-sky-200";
                  else if (ftype === "court_finding") tagClass = "text-purple-800 bg-purple-50 border-purple-200";

                  return (
                    <div key={idx} className="p-2 rounded-lg bg-[#FAF9F7] border border-slate-200 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[9px] font-bold text-[#8C5A3C]">
                          {fact.id || `fact_${idx + 1}`}
                        </span>
                        <span className={`text-[8px] font-mono font-bold uppercase px-1 rounded border ${tagClass}`}>
                          {ftype.replace("_", " ")}
                        </span>
                      </div>
                      <p className="text-[11px] leading-snug text-[#2C1810]">
                        {fact.text || fact.value}
                      </p>
                      {fact.source && (
                        <span className="text-[9px] font-mono text-slate-400 block">
                          Source: {fact.source}
                        </span>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="text-[10px] text-textMuted font-mono py-6 text-center">
                  No facts match this filter category.
                </p>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: EVIDENCE INVENTORY */}
        {activeTab === "evidence" && (
          <div className="space-y-2 animate-fadeIn">
            <span className="text-[9px] font-mono uppercase tracking-wider text-textMuted block">
              Record Verification Status (Present vs Missing):
            </span>
            <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1">
              {inventory.length > 0 ? (
                inventory.map((item, idx) => {
                  const isPresent = item.status === "present";
                  return (
                    <div 
                      key={idx} 
                      className={`p-2 rounded-lg border flex items-start justify-between gap-2 text-xs ${
                        isPresent 
                          ? "bg-emerald-50/50 border-emerald-200" 
                          : "bg-slate-50 border-slate-200 opacity-80"
                      }`}
                    >
                      <div className="space-y-0.5">
                        <span className="font-mono font-bold text-[10px] text-[#2C1810] block">
                          {item.item || item.name}
                        </span>
                        <p className="text-[10px] text-[#5D4037] leading-snug">
                          {item.details || ""}
                        </p>
                      </div>
                      <span className={`text-[8px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border shrink-0 ${
                        isPresent 
                          ? "bg-emerald-100 text-emerald-800 border-emerald-300" 
                          : "bg-slate-200 text-slate-700 border-slate-300"
                      }`}>
                        {item.status}
                      </span>
                    </div>
                  );
                })
              ) : (
                <p className="text-[10px] text-textMuted font-mono py-6 text-center">
                  Evidence inventory awaiting extraction.
                </p>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: LEXIGRAPH */}
        {activeTab === "lexigraph" && (
          <div className="space-y-3 animate-fadeIn">
            <div className="bg-[#FAF8F5] p-3 rounded-lg border border-[#D4AF37]/40 space-y-2">
              <span className="font-heading text-[10px] font-bold uppercase tracking-wider text-[#2C1810] block">
                Statutes Retrieved & Verified:
              </span>
              <div className="flex flex-wrap gap-1">
                {(caseData.verdict?.statutes || ["CrPC 438", "CrPC 82", "CrPC 83", "CrPC 70(2)", "IPC 174", "IPC 354B"]).map((s, idx) => (
                  <span key={idx} className="px-2 py-0.5 text-[10px] font-mono font-bold bg-white rounded border border-[#D4AF37]/50 text-[#2C1810]">
                    § {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="bg-[#FAF8F5] p-3 rounded-lg border border-[#D4AF37]/40 space-y-2">
              <span className="font-heading text-[10px] font-bold uppercase tracking-wider text-[#2C1810] block">
                Precedents & Holdings Relied:
              </span>
              <div className="space-y-1 text-xs">
                {(caseData.verdict?.precedents || ["Srikant Upadhyay v. State of Bihar (2024 INSC 202)"]).map((p, idx) => (
                  <div key={idx} className="p-1.5 rounded bg-white border border-[#2C1810]/10 font-mono text-[10px] text-[#2C1810]">
                    📜 {p}
                  </div>
                ))}
                {(caseData.verdict?.holdings_relied || ["srikant_para8-9", "srikant_para19-20"]).map((h, idx) => (
                  <div key={idx} className="p-1.5 rounded bg-amber-50 border border-amber-200 font-mono text-[10px] text-amber-900">
                    ⚖ {h}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* FOOTER ACTIONS */}
        <div className="mt-auto pt-3 border-t border-surface-border flex flex-col gap-2">
          {onOpenCaseModal && (
            <button
              onClick={onOpenCaseModal}
              className="w-full flex items-center justify-center gap-1.5 text-[9.5px] uppercase font-bold tracking-wider text-[#2C1810] bg-[#FAF8F5] hover:bg-[#D4AF37]/20 border border-[#D4AF37]/60 px-3 py-2 rounded transition-all cursor-pointer shadow-2xs"
            >
              <FolderCheck size={13} className="text-[#8C5A3C]" />
              <span>Select Case / Load Transcript</span>
            </button>
          )}

          <button 
            onClick={onExit}
            className="border border-surface-border text-wood-dark font-body text-xs uppercase tracking-widest px-4 py-2.5 hover:bg-[#FAF8F5] transition-all font-bold text-center w-full cursor-pointer"
          >
            Exit to Chambers
          </button>
        </div>
      </div>
    </>
  );
}