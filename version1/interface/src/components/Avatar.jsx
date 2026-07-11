import { motion } from "framer-motion";

const avatarMap = {
  judge: "/avatars/judge.svg",
  prosecutor: "/avatars/judge.svg",
  defense: "/avatars/judge.svg",
  accused: "/avatars/judge.svg",
};

export default function Avatar({ role, name, active, message }) {
  // Drive States directly from MootCourt LLM logic
  const isThinking = active && !message;
  const isSpeaking = active && !!message;

  return (
    <div className="relative flex flex-col items-center group w-32">

      {/* CLOUD ICON (Replaces text bubble for immersion) */}
      {(isSpeaking || isThinking) && (
        <div className="absolute -top-[50px] md:-top-[60px] -right-[5px] md:-right-[20px] z-50 pointer-events-none transition-all duration-500">
          <img
             src="/avatars/cloud.svg"
             alt="Simulation Cloud"
             className={`w-[60px] md:w-[80px] h-auto drop-shadow-xl transition-all duration-300 origin-bottom-left ${
                isThinking ? "animate-[pulse_2s_ease-in-out_infinite] opacity-80 scale-95" : "opacity-100 scale-110"
             }`}
          />
        </div>
      )}

      {/* CHARACTER AVATAR IMAGE */}
      <img
        src={avatarMap[role]}
        alt={name}
        className={`h-16 md:h-24 w-auto object-contain transition-all duration-300 ${
            active 
            ? "drop-shadow-[0_0_10px_rgba(197,160,89,0.8)] scale-105" 
            : "opacity-80 scale-100"
        }`}
      />

      {/* NAME TAG (Professional Plaque Style) */}
      <div className="bg-wood-deep/90 border-[0.5px] border-white/20 text-white rounded md:rounded-md shadow-lg px-2 md:px-3 py-1 md:py-1.5 mt-1 md:mt-2 transition-all duration-300">
        <span className="text-[7px] md:text-[9px] font-mono tracking-widest font-black uppercase block drop-shadow-md whitespace-nowrap text-center text-white/90">
          {name}
        </span>
      </div>
      
    </div>
  );
}
