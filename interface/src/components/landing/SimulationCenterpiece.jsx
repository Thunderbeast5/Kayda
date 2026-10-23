import { memo, useEffect, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { Pause, Play, RotateCcw, Scale, Gavel, Briefcase } from "lucide-react";
import CourtroomStage from "../CourtroomStage";

// Memoised so the heavy stage (9 images + filters) only re-renders when the
// speaker or seat changes — not on every new message / typing tick.
const Stage = memo(CourtroomStage);

const AGENTS = {
  prosecutor: { label: "Prosecutor", fullLabel: "Public Prosecutor", color: "#1E3A8A", Icon: Scale },
  judge: { label: "Judge", fullLabel: "Hon'ble Judge", color: "#B8965A", Icon: Gavel },
  defense: { label: "Defense", fullLabel: "Defense Counsel", color: "#991B1B", Icon: Briefcase },
};
const ROLL_CALL = ["prosecutor", "judge", "defense"];

const EASE = [0.22, 1, 0.36, 1];

export default function SimulationCenterpiece({
  simMessages = [],
  setSimMessages,
  setCurrentSimIndex,
  isTyping,
  isPlaying,
  setIsPlaying,
  activeSpeaker,
  setActiveSpeaker,
  userRole = null, // "judge" | "prosecutor" | "defense" to mark the user's seat
}) {
  const scrollRef = useRef(null);

  // Auto-scroll court record to the latest entry (single rAF-friendly call)
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [simMessages.length]);

  // Index + message of the latest spoken (non-system) line
  const lastIndex = useMemo(() => {
    for (let i = simMessages.length - 1; i >= 0; i--) {
      if (simMessages[i].type !== "system") return i;
    }
    return -1;
  }, [simMessages]);

  const spokenCount = useMemo(
    () => simMessages.reduce((n, m) => (m.type === "system" ? n : n + 1), 0),
    [simMessages]
  );

  return (
    <section
      id="simulation"
      className="py-14 sm:py-20 md:py-32 px-4 sm:px-6 md:px-12 border-b border-surface-border bg-white"
    >
      <div className="max-w-5xl mx-auto">
        {/* Header Intro */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: EASE }}
          className="text-center mb-10 sm:mb-14 md:mb-16"
        >
          <span className="font-mono text-[9px] sm:text-[10px] md:text-xs uppercase tracking-[0.25em] md:tracking-[0.3em] text-gold font-bold mb-2 block">
            REAL-TIME ORCHESTRATION SHOWN LIVE
          </span>
          <h2 className="font-heading text-2xl sm:text-3xl md:text-5xl text-wood-dark tracking-tight mb-3 md:mb-4">
            The AI Courtroom Simulation
          </h2>
          <p className="font-body text-xs sm:text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed px-2">
            Watch multiple AI entities coordinate, raise legal arguments, and rule dynamically.
            This is not static text generation—it is an ecosystem in constant adversarial motion.
          </p>
        </motion.div>

        {/* SIMULATOR WINDOW CONTAINER */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.85, ease: EASE }}
          className="border border-surface-border bg-white shadow-xl md:shadow-2xl relative rounded-md overflow-hidden"
        >
          {/* Window Bar */}
          <div className="bg-wood-dark px-3 sm:px-4 py-2.5 sm:py-3.5 flex items-center justify-between border-b border-wood-deep gap-2">
            <div className="flex items-center gap-2.5 sm:gap-4 min-w-0">
              <div className="flex gap-1 sm:gap-1.5 shrink-0">
                <div className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-red-800/60" />
                <div className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-yellow-600/60" />
                <div className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-green-800/60" />
              </div>
              <span className="font-mono text-[9px] sm:text-[10px] tracking-wider text-[#FAF8F5]/80 truncate">
                <span className="hidden sm:inline">SESSION DOCKET: </span>#402-B // CHAMBER_SIM
              </span>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="text-white/70 hover:text-white transition-all duration-150 hover:scale-110 active:scale-90 cursor-pointer p-1"
                title={isPlaying ? "Pause Simulation" : "Play Simulation"}
                aria-label={isPlaying ? "Pause Simulation" : "Play Simulation"}
              >
                {isPlaying ? <Pause size={13} className="sm:w-3.5 sm:h-3.5" /> : <Play fill="currentColor" size={13} className="sm:w-3.5 sm:h-3.5" />}
              </button>

              <button
                onClick={() => {
                  setSimMessages([]);
                  setCurrentSimIndex(0);
                  setActiveSpeaker(null);
                }}
                className="text-white/70 hover:text-white transition-all duration-200 hover:-rotate-45 active:scale-90 cursor-pointer p-1"
                title="Reset Case Simulation"
                aria-label="Reset Case Simulation"
              >
                <RotateCcw size={13} className="sm:w-3.5 sm:h-3.5" />
              </button>
            </div>
          </div>

          {/* ───────── LIVE COURTROOM STAGE ───────── */}
          <div className="relative isolate bg-wood-dark overflow-hidden">
            <Stage activeSpeaker={activeSpeaker} lastMessage={null} userRole={userRole} />

            {/* Static vignette */}
            <div className="pointer-events-none absolute inset-0 z-[55] bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(30,18,10,0.28)_100%)]" />

            {/* Live badge */}
            <div className="pointer-events-none absolute left-2 top-2 sm:left-3 sm:top-3 z-[60] flex items-center gap-1.5 sm:gap-2 rounded bg-black/70 px-2 sm:px-2.5 py-0.5 sm:py-1">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isPlaying ? "bg-red-500 animate-pulse" : "bg-white/40"
                }`}
              />
              <span className="font-mono text-[7px] sm:text-[8px] md:text-[9px] font-bold uppercase tracking-[0.15em] sm:tracking-[0.2em] text-white/90">
                {isPlaying ? "Live" : "Paused"}
              </span>
            </div>

            {/* Case Info Badge */}
            <div className="pointer-events-none absolute right-2 top-2 sm:right-3 sm:top-3 z-[60] rounded bg-black/70 px-2 sm:px-2.5 py-0.5 sm:py-1 max-w-[55%] truncate">
              <span className="font-mono text-[7px] sm:text-[8px] md:text-[9px] uppercase tracking-[0.12em] sm:tracking-[0.2em] text-gold truncate block">
                <span className="sm:hidden">State v. Accused</span>
                <span className="hidden sm:inline">State v. Accused · Sessions Court</span>
              </span>
            </div>

            {/* Paused veil */}
            <div
              onClick={() => !isPlaying && setIsPlaying(true)}
              className={`absolute inset-0 z-[58] flex items-center justify-center bg-wood-dark/50 transition-opacity duration-200 ${
                isPlaying ? "opacity-0 pointer-events-none" : "opacity-100 cursor-pointer"
              }`}
            >
              <div className="flex items-center gap-1.5 sm:gap-2 rounded-full border border-gold/50 bg-black/70 px-3 py-1.5 sm:px-4 sm:py-2">
                <Play size={10} className="text-gold sm:w-3 sm:h-3" fill="currentColor" />
                <span className="font-mono text-[8px] sm:text-[10px] uppercase tracking-[0.18em] sm:tracking-[0.25em] text-white/90">
                  Resume proceedings
                </span>
              </div>
            </div>
          </div>

          {/* ───────── ROLL CALL ───────── */}
          <div className="bg-[#FAF8F5] border-b border-surface-border">
            <div className="grid grid-cols-3 border-b border-surface-border/60">
              {ROLL_CALL.map((id) => {
                const a = AGENTS[id];
                const active = activeSpeaker === id;
                const Icon = a.Icon;
                return (
                  <div
                    key={id}
                    className={`relative flex items-center justify-center gap-1.5 sm:gap-2 px-1.5 sm:px-2 py-2 sm:py-2.5 transition-[opacity,background-color] duration-300 ${ active ? "bg-white" : "opacity-60" }`} > <span className="flex h-5 w-5 sm:h-6 sm:w-6 shrink-0 items-center justify-center rounded-full transition-colors duration-300" style={{ background: active ? `${a.color}1F` : "#F1EEE8",
                        color: active ? a.color : "#8A7E72",
                      }}
                    >
                      <Icon className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                    </span>
                    <div className="flex flex-col leading-tight text-left min-w-0">
                      <span className="font-heading font-bold text-[9px] sm:text-[10px] md:text-xs text-wood-dark truncate">
                        <span className="sm:hidden">{a.label}</span>
                        <span className="hidden sm:inline">{a.fullLabel}</span>
                      </span>
                      <span className="hidden md:block font-mono text-[8px] uppercase tracking-wider text-textMuted truncate">
                        {active ? (isTyping ? "Preparing…" : "Has floor") : "Idle"}
                      </span>
                    </div>

                    {/* Active bar */}
                    <span
                      className={`absolute bottom-0 inset-x-1.5 sm:inset-x-3 h-0.5 origin-center rounded-full transition-transform duration-300 ${ active ? "scale-x-100" : "scale-x-0" }`} style={{ background: a.color }} /> </div> ); })} </div> </div>  {/* ───────── COURT RECORD ───────── */} <div className="flex items-center justify-between bg-white px-4 sm:px-6 pt-3 sm:pt-4 pb-2"> <span className="font-mono text-[8px] sm:text-[9px] font-bold uppercase tracking-[0.2em] sm:tracking-[0.25em] text-wood-dark"> Court Record </span> <span className="font-mono text-[8px] sm:text-[9px] text-textMuted">{spokenCount} entries</span> </div>  <div ref={scrollRef} className="h-[220px] sm:h-[260px] overflow-y-auto px-3 sm:px-6 pb-4 sm:pb-6 pt-1 sm:pt-2 space-y-3 sm:space-y-4 bg-white select-none [contain:content]" > {simMessages.map((msg, i) => { if (msg.type === "system") { return ( <div key={`sys-${i}`} className="text-center py-1 sm:py-2">
                    <span className="font-mono text-[9px] sm:text-[10px] uppercase tracking-wider text-gold bg-gold/10 px-2.5 py-0.5 sm:px-3 sm:py-1 rounded inline-block">
                      {msg.text}
                    </span>
                  </div>
                );
              }

              const isProsecutor = msg.agentId === "prosecutor";
              const isDefense = msg.agentId === "defense";
              const isLatest = i === lastIndex;

              let sideBorder = "border-l-gold";
              let alignment = "mx-auto";
              if (isProsecutor) {
                sideBorder = "border-l-[#1E3A8A]";
                alignment = "mr-auto";
              } else if (isDefense) {
                sideBorder = "border-l-[#991B1B]";
                alignment = "ml-auto";
              }

              return (
                <motion.div
                  key={`msg-${i}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: EASE }} className={`bg-[#FAF8F5] border-l-4 ${sideBorder} p-3 sm:p-4 rounded-r shadow-sm border-y border-r border-surface-border w-[96%] sm:max-w-[85%] ${alignment} transition-opacity duration-300${
                    isLatest ? "ring-1 ring-gold/40" : "opacity-75"
                  }`}
                >
                  <div className="flex justify-between items-center mb-1 pb-1 border-b border-surface-border/40">
                    <span className="font-body font-bold text-[9px] sm:text-[10px] uppercase tracking-wider text-wood-dark">
                      {msg.speaker}
                    </span>
                    <span className="font-mono text-[7px] sm:text-[8px] text-textMuted font-bold">COURT FEED</span>
                  </div>
                  <p className="font-serif text-xs sm:text-sm text-textPrimary leading-relaxed">"{msg.text}"</p>
                </motion.div>
              );
            })}
          </div>

          {/* Bottom Status Bar */}
          <div className="bg-[#FAF8F5] border-t border-surface-border px-3 sm:px-4 py-2 sm:py-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-1 sm:gap-2 text-[9px] sm:text-xs font-mono text-textMuted">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="h-1.5 w-1.5 sm:h-2 sm:w-2 shrink-0 rounded-full bg-green-600" />
              <span className="truncate">SIMULATOR STATUS: REAL-TIME DEMONSTRATION</span>
            </div>
            <span className="text-[8px] sm:text-xs shrink-0 self-end sm:self-auto">DOCKET INDEX #402</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}