import { X, Network, Lightbulb, GitCommit, BookOpen, AlertTriangle } from "lucide-react";

export default function CourtroomSidebar({
  sidebarOpen,
  setSidebarOpen,
  sidebarCollapsed,
  onExit,
  caseData,
  uploadStatus,
  uploadProgress,
  uploadedFileName,
  handleSidebarFileUpload,
  fileInputRef,
  inputText,
  activeSpeaker,
  status
}) {
  return (
    <>
      {/* MOBILE OVERLAY */}
      {sidebarOpen && (
        <div className="absolute inset-0 bg-black/40 z-40 md:hidden backdrop-blur-sm" onClick={() => setSidebarOpen(false)}></div>
      )}

      {/* LEFT PANEL */}
      <div className={`fixed md:relative top-0 left-0 h-full flex-shrink-0 flex flex-col gap-4 bg-white shadow-2xl md:shadow-xl transition-all duration-[350ms] ease-in-out z-50 ${
        sidebarCollapsed 
          ? 'w-0 p-0 lg:p-0 border-r-0 opacity-0 overflow-hidden pointer-events-none' 
          : 'w-[280px] md:w-[320px] lg:w-[360px] p-4 lg:p-6 border-r border-surface-border opacity-100 overflow-y-auto'
      } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
        
        <div className="flex justify-between items-center z-10 pb-2 border-b border-surface-border">
          <div>
            <h1 className="text-lg lg:text-[22px] font-heading font-extrabold text-wood-dark tracking-tight leading-snug cursor-pointer" onClick={onExit}>
              Kayda
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button className="md:hidden relative p-1.5 border border-transparent text-wood-dark cursor-pointer" onClick={() => setSidebarOpen(false)}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* CASE FILE OR UPLOAD STATUS */}
        {uploadStatus ? (
          <div className="bg-[#FAF8F5] border border-[#D4AF37]/30 rounded-lg p-4 mt-3 shadow-inner animate-[pulse_1.5s_infinite]">
            <div className="flex items-center gap-2 text-[#D4AF37] font-black text-[9px] uppercase tracking-widest mb-3">
              <div className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] animate-ping" />
              {uploadStatus === "uploading" ? "Firebase Uploading" : "AI Brief Parsing"}
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
            <p className="text-[10px] text-textMuted mt-1">
              {uploadStatus === "uploading" 
                ? `Progress: ${uploadProgress}% completed...` 
                : "Parsing case details and IPC sections..."}
            </p>
          </div>
        ) : (
          <div className="bg-white shadow-[0_2px_10px_rgba(0,0,0,0.05)] rounded-tr-xl rounded-b-xl border border-surface-border px-3.5 py-3 relative mt-3 h-auto z-10">
            <div className="absolute -top-[23px] left-[-1px] bg-white px-3 md:px-4 py-1.5 rounded-t-lg border-t border-l border-r border-surface-border text-[8px] md:text-[9px] font-black text-primaryBrown uppercase tracking-wider">
              Case File {caseData.fileId}
            </div>
            <h2 className="font-heading font-bold mb-2 text-[14px] md:text-[16px] leading-tight text-wood-dark">
              {caseData.title.split(" vs. ")[0]} <span className="text-[10px] md:text-xs italic font-normal">vs.</span> {caseData.title.split(" vs. ")[1] || ""}
            </h2>
            <ul className="text-[11px] md:text-xs space-y-2 text-textPrimary/90 font-mono">
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                <span className="font-bold text-textMuted uppercase text-[8px] md:text-[9px] tracking-widest">FIR No</span> <span>{caseData.firNo}</span>
              </li>
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                <span className="font-bold text-textMuted uppercase text-[8px] md:text-[9px] tracking-widest">Charge</span> 
                <span className="bg-white/60 px-1 rounded font-bold text-semantic-criticalText">{caseData.charge}</span>
              </li>
            </ul>
          </div>
        )}

        {/* LEXIGRAPH VISUALIZER */}
        <div className="bg-white p-3 md:p-4 rounded-lg shadow-sm border border-surface-border flex flex-col gap-2 relative z-10 w-full flex-shrink-0 mt-2">
          <div className="flex items-center gap-2 text-primaryBrown border-b border-surface-border pb-2">
            <Network size={14} strokeWidth={2.5} />
            <span className="font-heading font-extrabold text-[10px] md:text-[11px] uppercase tracking-[0.1em]">LexiGraph Evidence</span>
          </div>
          <div className="relative h-[90px] md:h-[110px] w-full bg-white rounded border border-dashed border-surface-border flex items-center justify-center overflow-hidden">
             
             {inputText.length > 5 || activeSpeaker ? (
               <div className="absolute flex flex-col items-center justify-center w-full h-full p-2 animate-[fadeIn_0.5s_ease-out]">
                  <div className="flex items-center w-full justify-center">
                    <div className="p-1 px-2 md:px-3 border-2 border-gold rounded-full bg-white text-[9px] md:text-[10px] font-bold text-wood-dark shadow-md z-10">IPC 379</div>
                    
                    <svg className="w-8 md:w-12 h-2 -mx-1 md:-mx-2 z-0 opacity-60" viewBox="0 0 100 20">
                      <path d="M0,10 L100,10" fill="none" stroke="#C5A059" strokeWidth="4" strokeDasharray="6,6" className="animate-[pulse_1s_linear_infinite]" />
                    </svg>
                    
                    <div className="p-1 px-2 md:px-3 border-2 border-[#8B0000] rounded-full bg-white text-[9px] md:text-[10px] font-bold text-[#8B0000] shadow-md z-10">Mens Rea</div>
                  </div>
                  
                  {inputText.length > 15 && (
                    <div className="flex items-center w-full justify-center animate-[fadeIn_1s_ease-out] relative">
                      <svg className="absolute w-2 h-6 md:h-8 -top-6 md:-top-8 left-[40%] z-0 opacity-40 shrink-0" viewBox="0 0 10 40">
                        <path d="M5,0 L5,40" fill="none" stroke="#1E88E5" strokeWidth="4" strokeDasharray="4,4" />
                      </svg>
                      <div className="mt-1 md:mt-2 p-1 px-2 md:px-3 ml-2 md:ml-4 border-2 border-[#1E88E5] rounded-full bg-white text-[8px] md:text-[9px] font-bold text-[#1E88E5] shadow-sm z-10">Intent Absent</div>
                    </div>
                  )}
               </div>
            ) : (
               <p className="text-[9px] md:text-[10px] text-textMuted font-mono bg-white/50 px-2 py-1 rounded">Awaiting reasoning...</p>
            )}

          </div>
        </div>

        {/* LEGAL COACH INTERVENTION */}
        {status === "running" && (
          <div className="bg-gradient-to-br from-[#E3F2FD] to-[#f4faff] border border-[#90CAF9] p-4 font-body rounded-lg shadow-sm mt-3 mb-auto animate-[fadeIn_0.5s_ease-out]">
            <div className="flex items-center gap-2 text-[#0D47A1] font-black text-[9px] md:text-[10.5px] uppercase tracking-widest mb-3">
              <Lightbulb size={14} className="fill-[#90CAF9]" /> Legal Guidance
            </div>
            <div className="text-[11px] md:text-[12px] text-[#0D47A1] leading-relaxed space-y-3">
              <p className="font-bold border-b border-blue-200 pb-1 text-[10px] md:text-xs">You should:</p>
              <div className="space-y-2">
                <p className="flex items-start gap-1 md:gap-2 font-medium">
                  <GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500 hidden md:block" /> 
                  <span>Challenge intent interpretation under <span className="font-bold underline decoration-2 decoration-[#1E88E5] text-blue-800 rounded px-0.5">Section 378</span>.</span>
                </p>
                <p className="flex items-start gap-1 md:gap-2 font-medium"><GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500 hidden md:block" /> Emphasize lack of evidence.</p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-auto pt-6 pb-4 flex flex-col gap-2">
          {status === "running" && (
            <div className="flex flex-col gap-2 mb-2 p-3 bg-[#FAF8F5] border border-surface-border rounded-lg animate-[fadeIn_0.3s_ease-out]">
              <span className="font-mono text-[8px] uppercase tracking-widest text-[#8C5A3C] font-bold mb-1 block">Courtroom Actions</span>
              <button 
                type="button" 
                onClick={() => alert("Consulting Legal Database...\nNo contradictions found at this stage.")}
                className="w-full flex items-center justify-center gap-1.5 text-[9px] uppercase font-bold tracking-widest text-[#0D47A1] bg-[#E3F2FD] px-3 py-2 rounded border border-[#90CAF9] hover:bg-[#90CAF9]/20 transition-all cursor-pointer"
              >
                <BookOpen size={12} />
                <span>Consult Legal Database</span>
              </button>
              <button 
                type="button" 
                onClick={() => alert("Objection Raised!\nThe Court has noted your objection. The Judge will rule shortly.")}
                className="w-full flex items-center justify-center gap-1.5 text-[9px] uppercase font-bold tracking-widest text-white bg-[#D32F2F] px-3 py-2 rounded border border-[#B71C1C] hover:bg-[#B71C1C]/90 transition-all cursor-pointer"
              >
                <AlertTriangle size={12} fill="currentColor" className="text-white" />
                Raise Objection
              </button>
            </div>
          )}

          <button 
            onClick={onExit}
            className="border border-surface-border text-wood-dark font-body text-xs uppercase tracking-widest px-4 py-3 hover:bg-[#FAF8F5] transition-all font-bold text-center w-full cursor-pointer"
          >
            Exit to Chambers
          </button>
        </div>
      </div>
    </>
  );
}
