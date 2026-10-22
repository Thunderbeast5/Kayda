import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Pause, Play, RotateCcw, Scale, Hand, Briefcase } from "lucide-react";

export default function SimulationCenterpiece({
  simMessages = [],
  setSimMessages,
  setCurrentSimIndex,
  isTyping,
  isPlaying,
  setIsPlaying,
  activeSpeaker,
  setActiveSpeaker,
}) {
  const scrollRef = useRef(null);

  // Auto-scroll to latest dialogue or typing indicator
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [simMessages, isTyping]);

  const avatars = [
    { id: "prosecutor", label: "Public Prosecutor", icon: <Scale size={20} /> },
    { id: "judge", label: "Hon'ble Judge", icon: <Hand size={20} /> },
    { id: "defense", label: "Defense Counsel", icon: <Briefcase size={20} /> },
  ];

  return (
    <section
      id="simulation"
      className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white"
    >
      <div className="max-w-5xl mx-auto">
        {/* Header Intro */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-16"
        >
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            REAL-TIME ORCHESTRATION SHOWN LIVE
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            The AI Courtroom Simulation
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Watch multiple AI entities coordinate, raise legal arguments, and rule dynamically.
            This is not static text generation—it is an ecosystem in constant adversarial motion.
          </p>
        </motion.div>

        {/* SIMULATOR WINDOW CONTAINER */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
          className="border border-surface-border bg-white shadow-2xl relative rounded-md overflow-hidden"
        >
          {/* Window Bar */}
          <div className="bg-wood-dark px-4 py-3.5 flex items-center justify-between border-b border-wood-deep">
            <div className="flex items-center gap-4">
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-800/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-600/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-800/60" />
              </div>
              <span className="font-mono text-[10px] tracking-wider text-[#FAF8F5]/80">
                SESSION DOCKET: #402-B // CHAMBER_SIMULATOR
              </span>
            </div>

            {/* Play/Pause & Reset Controls */}
            <div className="flex items-center gap-3">
              <motion.button
                whileHover={{ scale: 1.15 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => setIsPlaying(!isPlaying)}
                className="text-white/70 hover:text-white transition-colors cursor-pointer p-1"
                title={isPlaying ? "Pause Simulation" : "Play Simulation"}
              >
                <AnimatePresence mode="wait" initial={false}>
                  {isPlaying ? (
                    <motion.span
                      key="pause"
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.15 }}
                    >
                      <Pause size={14} />
                    </motion.span>
                  ) : (
                    <motion.span
                      key="play"
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.15 }}
                    >
                      <Play fill="currentColor" size={14} />
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>

              <motion.button
                whileHover={{ scale: 1.15, rotate: -45 }}
                whileTap={{ scale: 0.9, rotate: -180 }}
                transition={{ type: "spring", stiffness: 350, damping: 20 }}
                onClick={() => {
                  setSimMessages([]);
                  setCurrentSimIndex(0);
                  setActiveSpeaker(null);
                }}
                className="text-white/70 hover:text-white transition-colors cursor-pointer p-1"
                title="Reset Case Simulation"
              >
                <RotateCcw size={14} />
              </motion.button>
            </div>
          </div>

          {/* Simulated Avatars Header */}
          <div className="bg-[#FAF8F5] border-b border-surface-border px-6 py-6 grid grid-cols-3 gap-4 text-center">
            {avatars.map((av) => {
              const isActive = activeSpeaker === av.id;

              return (
                <div
                  key={av.id}
                  className={`relative flex flex-col items-center justify-center p-3 rounded transition-all duration-300 ${
                    isActive
                      ? "bg-white shadow-sm scale-102 border border-gold/40"
                      : "opacity-50 hover:opacity-75 border border-transparent"
                  }`}
                >
                  <motion.div
                    animate={isActive ? { scale: [1, 1.08, 1] } : { scale: 1 }}
                    transition={
                      isActive
                        ? { repeat: Infinity, duration: 2.2, ease: "easeInOut" }
                        : { duration: 0.2 }
                    }
                    className={`p-2 rounded-full mb-1.5 transition-colors duration-300 ${
                      isActive
                        ? "bg-gold/15 text-gold"
                        : "text-textMuted bg-gray-100"
                    }`}
                  >
                    {av.icon}
                  </motion.div>

                  <span className="font-heading font-bold text-xs text-wood-dark">
                    {av.label}
                  </span>
                  <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase mt-0.5">
                    {isActive ? "Actively Speaking" : "Idle Court Record"}
                  </span>

                  {/* Active highlight bar */}
                  {isActive && (
                    <motion.div
                      layoutId="activeSpeakerIndicator"
                      className="absolute bottom-0 inset-x-4 h-0.5 bg-gold rounded-full"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Dialogue Screen */}
          <div
            ref={scrollRef}
            className="h-[340px] overflow-y-auto p-6 space-y-4 bg-white select-none scroll-smooth"
          >
            <AnimatePresence initial={false}>
              {simMessages.map((msg, i) => {
                if (msg.type === "system") {
                  return (
                    <motion.div
                      key={`sys-${i}`}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.35 }}
                      className="text-center py-2"
                    >
                      <span className="font-mono text-[10px] uppercase tracking-wider text-gold bg-gold/10 px-3 py-1 rounded inline-block">
                        {msg.text}
                      </span>
                    </motion.div>
                  );
                }

                const isProsecutor = msg.agentId === "prosecutor";
                const isDefense = msg.agentId === "defense";

                let sideBorder = "border-l-gold";
                let initialX = 0;
                let alignment = "mx-auto";

                if (isProsecutor) {
                  sideBorder = "border-l-[#1E3A8A]";
                  initialX = -20;
                  alignment = "mr-auto";
                } else if (isDefense) {
                  sideBorder = "border-l-[#991B1B]";
                  initialX = 20;
                  alignment = "ml-auto";
                }

                return (
                  <motion.div
                    key={`msg-${i}`}
                    layout
                    initial={{ opacity: 0, x: initialX, y: 12 }}
                    animate={{ opacity: 1, x: 0, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{
                      duration: 0.45,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                    className={`bg-[#FAF8F5] border-l-4 ${sideBorder} p-4 rounded-r shadow-sm border-y border-r border-surface-border max-w-[85%] ${alignment}`}
                  >
                    <div className="flex justify-between items-center mb-1 pb-1 border-b border-surface-border/40">
                      <span className="font-body font-bold text-[10px] uppercase tracking-wider text-wood-dark">
                        {msg.speaker}
                      </span>
                      <span className="font-mono text-[8px] text-textMuted font-bold">
                        COURT FEED
                      </span>
                    </div>
                    <p className="font-serif text-sm text-textPrimary leading-relaxed">
                      "{msg.text}"
                    </p>
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {/* Typing Indicator */}
            {isTyping && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-2 text-textMuted font-mono text-[9px] pl-2 py-1"
              >
                <div className="flex items-center gap-1">
                  {[0, 0.18, 0.36].map((delay, idx) => (
                    <motion.span
                      key={idx}
                      animate={{ y: [0, -4, 0] }}
                      transition={{
                        repeat: Infinity,
                        duration: 0.8,
                        ease: "easeInOut",
                        delay,
                      }}
                      className="w-1.5 h-1.5 rounded-full bg-gold inline-block"
                    />
                  ))}
                </div>
                <span className="ml-1 uppercase tracking-wider">
                  Agent preparing response...
                </span>
              </motion.div>
            )}
          </div>

          {/* Bottom Status Bar */}
          <div className="bg-[#FAF8F5] border-t border-surface-border px-4 py-3 flex items-center justify-between text-xs font-mono text-textMuted">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-600" />
              </span>
              <span>SIMULATOR STATUS: REAL-TIME SIMULATION DEMONSTRATION</span>
            </div>
            <span>DOCKET ARCHIVE INDEX #402</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}