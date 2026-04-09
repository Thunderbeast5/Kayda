import { CheckCircle2 } from "lucide-react";

export default function ChatPanel({ messages, userRole }) {
  return (
    <div className="flex-1 overflow-y-auto bg-surface-paperMain px-4 py-8 md:px-10 md:py-8 space-y-6 shadow-[inset_0_4px_25px_rgba(0,0,0,0.03)] w-full relative z-0 scroll-smooth">
      
      {messages.length === 0 && (
        <div className="h-full flex flex-col items-center justify-center text-primaryBrown/50 opacity-80 z-10 relative">
          <p className="font-heading text-xl font-bold tracking-[0.2em] uppercase text-primaryBrown/60">Official Trial Transcript</p>
          <p className="font-serif text-sm mt-2 opacity-80 italic">Proceedings have not commenced.</p>
        </div>
      )}

      {/* COURT IN SESSION VINTAGE DIVIDER */}
      {messages.length > 0 && (
        <div className="flex items-center justify-center pb-4 opacity-70 select-none sticky top-0 bg-gradient-to-b from-surface-paperMain via-surface-paperMain/90 to-transparent z-40 pt-2 backdrop-blur-[1px]">
           <div className="h-px bg-primaryBrown flex-1"></div>
           <div className="px-6 font-serif text-[11px] font-black tracking-[0.4em] uppercase text-primaryBrown">Court In Session</div>
           <div className="h-px bg-primaryBrown flex-1"></div>
        </div>
      )}

      {messages.map((msg, i) => {
        const isUser = msg.agentId === userRole;
        const isProsecutor = msg.agentId === "prosecutor";
        const isJudge = msg.agentId === "judge";
        const isDefense = msg.agentId === "defense";
        
        let displaySpeaker = msg.speaker;
        if (isUser) {
           displaySpeaker = `[YOU - ${msg.speaker.toUpperCase()}]`;
        } else {
           displaySpeaker = `[AI - ${msg.speaker.toUpperCase()}]`;
        }

        const borderColor = isProsecutor 
          ? "border-l-[#1E3A8A]" // Blue
          : isDefense 
            ? "border-l-[#991B1B]" // Red
            : "border-l-gold"; // Gold

        return (
          <div key={i} className={`bg-white border-l-[6px] ${borderColor} rounded-r-xl rounded-bl-md shadow-[0_5px_15px_rgba(0,0,0,0.04)] border-y border-r border-surface-border p-7 md:p-8 relative max-w-[85%] ${isUser ? 'ml-auto' : 'mr-auto'} z-10 transition-all hover:shadow-[0_8px_25px_rgba(0,0,0,0.06)]`}>

            {/* Header Identity */}
            <div className="flex justify-between items-start mb-5 border-b border-surface-border pb-4">
              <span className={`font-bold flex items-center gap-3 text-[11px] uppercase tracking-[0.15em] font-body px-3 py-1.5 rounded-sm ${isUser ? 'bg-primaryBrown text-white shadow-sm' : 'text-wood-dark bg-[#F5F5F0]'}`}>
                <div className={`w-2 h-2 rounded-full ${isProsecutor ? 'bg-[#1E3A8A]' : isJudge ? 'bg-gold' : isDefense ? 'bg-[#991B1B]' : 'bg-white'}`} />
                {displaySpeaker}
              </span>
              
              <div className="flex gap-4 items-center">
                {msg.citations?.length > 0 && (
                  <span className="flex items-center gap-1.5 text-[10px] uppercase font-black tracking-widest bg-[#F0FDF4] text-[#166534] border border-[#166534]/30 px-2.5 py-1 rounded shadow-[0_2px_4px_rgba(22,101,52,0.05)]">
                    <CheckCircle2 size={12} strokeWidth={3} className="text-[#166534]" /> LexiGraph Linked
                  </span>
                )}
              </div>
            </div>

            {/* Transcript Text - Explicitly forced to serif for legal document feel */}
            <p className="mt-2 font-serif text-[18px] md:text-[21px] leading-loose text-textPrimary tracking-tight">
               "{msg.text}"
            </p>

            {/* Evidence Sub-Panel */}
            {msg.citations?.length > 0 && (
              <div className="mt-8 flex gap-3 flex-wrap items-center pt-5 bg-surface-paperLight -mx-7 md:-mx-8 -mb-7 md:-mb-8 px-7 md:px-8 pb-5 border-t border-surface-border rounded-br-xl">
                <span className="text-[11px] tracking-widest text-primaryBrown font-bold uppercase font-body flex items-center gap-1.5 opacity-80">
                   🔗 Case Links:
                </span>
                {msg.citations.map((c, idx) => (
                  <span
                    key={idx}
                    className="bg-white border border-surface-border text-primaryBrown px-3.5 py-1.5 text-[12px] font-mono rounded shadow-sm hover:border-[#1E3A8A] hover:text-[#1E3A8A] hover:bg-semantic-infoBg hover:shadow-md transition-all cursor-pointer select-none font-bold"
                    title="Click to view LexiGraph Entity"
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
