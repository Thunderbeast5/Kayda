// import { CheckCircle2, Volume2 } from "lucide-react";
// import { useEffect, useRef } from "react";

// export default function ChatPanel({ messages, userRole, speakText }) {
//   const chatEndRef = useRef(null);

//   useEffect(() => {
//     chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
//   }, [messages]);

//   return (
//     <div className="flex-1 overflow-y-auto bg-surface-paperMain px-3 py-4 md:px-6 md:py-6 space-y-4 shadow-[inset_0_4px_25px_rgba(0,0,0,0.03)] w-full relative z-0 scroll-smooth flex flex-col items-center">
//       <div className="w-full max-w-4xl space-y-4 transition-all duration-[350ms] ease-in-out">
//         {messages.length === 0 && (
//           <div className="h-[250px] flex flex-col items-center justify-center text-primaryBrown/50 opacity-80 z-10 relative">
//             <p className="font-heading text-xl font-bold tracking-[0.2em] uppercase text-primaryBrown/60">Official Trial Transcript</p>
//             <p className="font-serif text-sm mt-2 opacity-80 italic">Proceedings have not commenced.</p>
//           </div>
//         )}

//         {messages.map((msg, i) => {
//           const isUser = msg.agentId === userRole;
//           const isProsecutor = msg.agentId === "prosecutor";
//           const isJudge = msg.agentId === "judge";
//           const isDefense = msg.agentId === "defense";
          
//           let displaySpeaker = msg.speaker;
//           if (isUser) {
//              displaySpeaker = `[YOU - ${msg.speaker.toUpperCase()}]`;
//           } else {
//              displaySpeaker = `[AI - ${msg.speaker.toUpperCase()}]`;
//           }

//           const borderColor = isProsecutor 
//             ? "border-l-[#1E3A8A]" // Blue
//             : isDefense 
//               ? "border-l-[#991B1B]" // Red
//               : "border-l-gold"; // Gold

//           return (
//             <div key={i} className={`bg-white border-l-[6px] ${borderColor} rounded-r-xl rounded-bl-md shadow-[0_5px_15px_rgba(0,0,0,0.04)] border-y border-r border-surface-border p-4 md:p-5 relative max-w-[90%] md:max-w-[85%] ${isUser ? 'ml-auto' : 'mr-auto'} z-10 transition-all hover:shadow-[0_8px_25px_rgba(0,0,0,0.06)]`}>

//               {/* Header Identity */}
//               <div className="flex justify-between items-start mb-3 border-b border-surface-border pb-2">
//                 <span className={`font-bold flex items-center gap-3 text-[11px] uppercase tracking-[0.15em] font-body px-3 py-1.5 rounded-sm ${isUser ? 'bg-primaryBrown text-white shadow-sm' : 'text-wood-dark bg-[#F5F5F0]'}`}>
//                   <div className={`w-2 h-2 rounded-full ${isProsecutor ? 'bg-[#1E3A8A]' : isJudge ? 'bg-gold' : isDefense ? 'bg-[#991B1B]' : 'bg-white'}`} />
//                   {displaySpeaker}
//                 </span>
                
//                 <div className="flex gap-2 items-center">
//                   {msg.citations?.length > 0 && (
//                     <span className="flex items-center gap-1.5 text-[10px] uppercase font-black tracking-widest bg-[#F0FDF4] text-[#166534] border border-[#166534]/30 px-2.5 py-1 rounded shadow-[0_2px_4px_rgba(22,101,52,0.05)]">
//                       <CheckCircle2 size={12} strokeWidth={3} className="text-[#166534]" /> LexiGraph Linked
//                     </span>
//                   )}
//                   {speakText && (
//                     <button
//                       onClick={() => speakText(msg.text, msg.agentId)}
//                       className="p-1 bg-white border border-surface-border rounded-md text-primaryBrown hover:bg-gold/10 hover:text-gold hover:border-gold/30 transition-all flex items-center justify-center cursor-pointer"
//                       title="Speak Message"
//                     >
//                       <Volume2 size={12} />
//                     </button>
//                   )}
//                 </div>
//               </div>

//               {/* Transcript Text - Explicitly forced to serif for legal document feel */}
//               <p className="mt-2 font-serif text-[14px] md:text-[16px] leading-relaxed text-textPrimary tracking-tight">
//                  "{msg.text}"
//               </p>

//               {/* Evidence Sub-Panel */}
//               {msg.citations?.length > 0 && (
//                 <div className="mt-4 flex gap-3 flex-wrap items-center pt-3 bg-surface-paperLight -mx-4 md:-mx-5 -mb-4 md:-mb-5 px-4 md:px-5 pb-3 border-t border-surface-border rounded-br-xl">
//                   <span className="text-[11px] tracking-widest text-primaryBrown font-bold uppercase font-body flex items-center gap-1.5 opacity-80">
//                      🔗 Case Links:
//                   </span>
//                   {msg.citations.map((c, idx) => (
//                     <span
//                       key={idx}
//                       className="bg-white border border-surface-border text-primaryBrown px-3.5 py-1.5 text-[12px] font-mono rounded shadow-sm hover:border-[#1E3A8A] hover:text-[#1E3A8A] hover:bg-semantic-infoBg hover:shadow-md transition-all cursor-pointer select-none font-bold"
//                       title="Click to view LexiGraph Entity"
//                     >
//                       {c}
//                     </span>
//                   ))}
//                 </div>
//               )}
//             </div>
//           );
//         })}
//       </div>
//       <div ref={chatEndRef} />
//     </div>
//   );
// }

import { CheckCircle2, Volume2, User, Bot, Scale, Shield, Gavel } from "lucide-react";
import { useEffect, useRef } from "react";

export default function ChatPanel({ messages, userRole, speakText }) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto bg-[#FAF9F7] px-4 py-6 md:px-8 space-y-6 w-full scroll-smooth">
      <div className="w-full max-w-4xl mx-auto space-y-8 transition-all duration-300">
        
        {/* Empty State */}
        {messages.length === 0 && (
          <div className="h-[300px] flex flex-col items-center justify-center text-[#2C1810]/40 mt-10">
            <div className="w-16 h-16 rounded-full bg-white shadow-sm flex items-center justify-center mb-5">
              <Scale size={28} className="text-[#D4AF37]" />
            </div>
            <p className="font-heading text-xl md:text-2xl font-bold tracking-tight text-[#2C1810]/60">
              Court is now in session
            </p>
            <p className="font-body text-sm mt-2 opacity-80">
              The AI courtroom is ready. Send a message to begin proceedings.
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          const isUser = msg.agentId === userRole;
          const isProsecutor = msg.agentId === "prosecutor";
          const isJudge = msg.agentId === "judge";
          const isDefense = msg.agentId === "defense";

          // Icon selection based on AI role
          let Icon = Bot;
          if (isProsecutor) Icon = Scale;
          else if (isJudge) Icon = Gavel;
          else if (isDefense) Icon = Shield;

          // Dynamic Bubble Styling for distinct AI personas
          let bubbleStyle = "bg-white text-[#2C1810] border border-[#2C1810]/10 rounded-tl-sm"; // Default AI fallback
          if (isUser) {
            bubbleStyle = "bg-[#2C1810] text-[#FAF9F7] rounded-tr-sm";
          } else if (isProsecutor) {
            bubbleStyle = "bg-blue-50 text-[#2C1810] border border-blue-200/60 rounded-tl-sm";
          } else if (isJudge) {
            bubbleStyle = "bg-amber-50/70 text-[#2C1810] border border-amber-200/60 rounded-tl-sm";
          } else if (isDefense) {
            bubbleStyle = "bg-rose-50 text-[#2C1810] border border-rose-200/60 rounded-tl-sm";
          }

          return (
            <div key={i} className={`flex w-full gap-3 md:gap-4 ${isUser ? "justify-end" : "justify-start"} animate-fadeIn`}>
              
              {/* AI Avatar */}
              {!isUser && (
                <div className="w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-full bg-white border border-[#D4AF37]/30 flex items-center justify-center shadow-sm mt-1">
                  <Icon size={18} className={isProsecutor ? "text-blue-700" : isJudge ? "text-amber-600" : isDefense ? "text-red-700" : "text-[#8C5A3C]"} />
                </div>
              )}

              {/* Message Content Container */}
              <div className={`flex flex-col gap-1.5 max-w-[85%] md:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
                
                {/* Header (Speaker Name & Verification Badge) */}
                <div className="flex items-center gap-3 px-1.5">
                  <span className="text-xs font-semibold text-[#5D4037] capitalize">
                    {msg.speaker} {isUser ? "(You)" : ""}
                  </span>
                  {msg.citations?.length > 0 && !isUser && (
                    <span className="flex items-center gap-1 text-[9px] uppercase font-bold tracking-wider bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full border border-emerald-200">
                      <CheckCircle2 size={10} strokeWidth={3} /> Verified
                    </span>
                  )}
                </div>

                {/* Chat Bubble with Dynamic Colors */}
                <div className={`relative px-5 py-3.5 md:py-4 md:px-6 rounded-3xl shadow-sm text-[14px] md:text-[15px] leading-relaxed font-body ${bubbleStyle}`}>
                  {msg.text}
                </div>

                {/* Bottom Actions Bar (TTS & Citations) */}
                <div className={`flex flex-wrap items-center gap-2 mt-1 px-1.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
                  
                  {speakText && (
                    <button
                      onClick={() => speakText(msg.text, msg.agentId)}
                      className="p-1.5 rounded-full text-[#5D4037]/60 hover:text-[#2C1810] hover:bg-black/5 transition-colors cursor-pointer"
                      title="Read aloud"
                    >
                      <Volume2 size={15} />
                    </button>
                  )}

                  {msg.citations?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((c, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 text-[10px] font-mono font-medium rounded-full bg-white border border-[#2C1810]/15 text-[#5D4037] hover:border-[#D4AF37] hover:text-[#8C5A3C] transition-colors cursor-pointer select-none shadow-sm"
                          title="View LexiGraph Entity"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

              </div>

              {/* User Avatar */}
              {isUser && (
                <div className="w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-full bg-gradient-to-br from-[#D4AF37] to-[#8C5A3C] flex items-center justify-center mt-1 shadow-sm">
                  <User size={18} className="text-white" />
                </div>
              )}

            </div>
          );
        })}
      </div>
      
      {/* Invisible element to scroll to */}
      <div ref={chatEndRef} className="h-4" />
    </div>
  );
}