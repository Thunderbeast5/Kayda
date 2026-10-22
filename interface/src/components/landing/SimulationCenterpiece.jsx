import { Pause, Play, RotateCcw, Scale, Hand, Briefcase } from "lucide-react";

export default function SimulationCenterpiece({
  simMessages,
  setSimMessages,
  setCurrentSimIndex,
  isTyping,
  isPlaying,
  setIsPlaying,
  activeSpeaker,
  setActiveSpeaker
}) {
  const avatars = [
    { id: "prosecutor", label: "Public Prosecutor", icon: <Scale size={20} /> },
    { id: "judge", label: "Hon'ble Judge", icon: <Hand size={20} /> },
    { id: "defense", label: "Defense Counsel", icon: <Briefcase size={20} /> }
  ];

  return (
    <section id="simulation" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            REAL-TIME ORCHESTRATION SHOWN LIVE
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            The AI Courtroom Simulation
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Watch multiple AI entities coordinate, raise legal arguments, and rule dynamically. This is not static text generation—it is an ecosystem in constant adversarial motion.
          </p>
        </div>

        {/* SIMULATOR WINDOW CONTAINER */}
        <div className="border border-surface-border bg-white shadow-2xl relative">
          
          {/* Window bar */}
          <div className="bg-wood-dark px-4 py-3.5 flex items-center justify-between border-b border-wood-deep">
            <div className="flex items-center gap-4">
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-800/60"></div>
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-600/60"></div>
                <div className="w-2.5 h-2.5 rounded-full bg-green-800/60"></div>
              </div>
              <span className="font-mono text-[10px] tracking-wider text-[#FAF8F5]/80">
                SESSION DOCKET: #402-B // CHAMBER_SIMULATOR
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button 
                onClick={() => setIsPlaying(!isPlaying)} 
                className="text-white/60 hover:text-white transition-colors cursor-pointer"
                title={isPlaying ? "Pause Simulation" : "Play Simulation"}
              >
                {isPlaying ? <Pause size={14} /> : <Play fill="currentColor" size={14} />}
              </button>
              <button 
                onClick={() => {
                  setSimMessages([]);
                  setCurrentSimIndex(0);
                  setActiveSpeaker(null);
                }} 
                className="text-white/60 hover:text-white transition-colors cursor-pointer"
                title="Reset Case Simulation"
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>

          {/* Simulated Avatars Header representing "ambient bench lighting" */}
          <div className="bg-[#FAF8F5] border-b border-surface-border px-6 py-6 grid grid-cols-3 gap-4 text-center">
            {avatars.map(av => (
              <div 
                key={av.id} 
                className={`flex flex-col items-center justify-center p-3 border transition-all duration-300 ${activeSpeaker === av.id ? 'border-gold bg-white shadow-sm scale-105' : 'border-transparent opacity-50'}`}
              >
                <div className={`p-2 rounded-full mb-1.5 ${activeSpeaker === av.id ? 'bg-gold/15 text-gold' : 'text-textMuted bg-gray-100'}`}>
                  {av.icon}
                </div>
                <span className="font-heading font-bold text-xs text-wood-dark">{av.label}</span>
                <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase mt-0.5">
                  {activeSpeaker === av.id ? "Acutely Speaking" : "Idle Court record"}
                </span>
              </div>
            ))}
          </div>

          {/* Dialogue screen */}
          <div className="h-[320px] overflow-y-auto p-6 space-y-4 bg-white select-none">
            {simMessages.map((msg, i) => {
              if (msg.type === "system") {
                return (
                  <div key={i} className="text-center py-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-gold bg-gold/10 px-3 py-1 rounded">
                      {msg.text}
                    </span>
                  </div>
                );
              }

              const isProsecutor = msg.agentId === "prosecutor";
              const isDefense = msg.agentId === "defense";

              let sideBorder = "border-l-gold";
              if (isProsecutor) sideBorder = "border-l-[#1E3A8A]";
              if (isDefense) sideBorder = "border-l-[#991B1B]";

              return (
                <div 
                  key={i} 
                  className={`bg-[#FAF8F5] border-l-4 ${sideBorder} p-4 rounded-r shadow-sm border-y border-r border-surface-border max-w-[85%] ${isProsecutor ? 'mr-auto' : isDefense ? 'ml-auto' : 'mx-auto'} animate-[fadeIn_0.3s_ease-out]`}
                >
                  <div className="flex justify-between items-center mb-1 pb-1 border-b border-surface-border/40">
                    <span className="font-body font-bold text-[10px] uppercase tracking-wider text-wood-dark">
                      {msg.speaker}
                    </span>
                    <span className="font-mono text-[8px] text-textMuted font-bold">COURT FEED</span>
                  </div>
                  <p className="font-serif text-sm text-textPrimary leading-relaxed">
                    "{msg.text}"
                  </p>
                </div>
              );
            })}
            {isTyping && (
              <div className="flex items-center gap-1.5 text-textMuted font-mono text-[9px] pl-2">
                <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce"></span>
                <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce [animation-delay:0.2s]"></span>
                <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce [animation-delay:0.4s]"></span>
                <span className="ml-1 uppercase tracking-wider">Agent preparing response...</span>
              </div>
            )}
          </div>

          {/* Bottom Status bar */}
          <div className="bg-[#FAF8F5] border-t border-surface-border px-4 py-3 flex items-center justify-between text-xs font-mono text-textMuted">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-600 animate-pulse"></div>
              <span>SIMULATOR STATUS: REAL-TIME SIMULATION DEMONSTRATION</span>
            </div>
            <span>DOCKET ARCHIVE INDEX #402</span>
          </div>
        </div>
      </div>
    </section>
  );
}
