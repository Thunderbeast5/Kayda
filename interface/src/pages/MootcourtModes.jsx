import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import StandardNavbar from "../components/StandardNavbar";
import CourtroomInterface from "../components/courtroom/CourtroomInterface";

// Precision Judicial Vectors (No Emojis)
const Icons = {
  Prosecution: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  ),
  Defense: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <circle cx="12" cy="11" r="3" />
    </svg>
  ),
  Observer: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
};

const pageContainerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.08,
    },
  },
  exit: {
    opacity: 0,
    scale: 0.98,
    transition: { duration: 0.3, ease: "easeInOut" },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.65,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function RoleSelectionPage() {
  const [selectedRole, setSelectedRole] = useState(null);

  const handleSelectRole = (role) => {
    setSelectedRole(role);
  };

  return (
    <AnimatePresence mode="wait">
      {selectedRole ? (
        <motion.div
          key="courtroom-screen"
          initial={{ opacity: 0, scale: 0.99 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="h-screen w-screen overflow-hidden"
        >
          <CourtroomInterface
            userRole={selectedRole}
            onExit={() => setSelectedRole(null)}
          />
        </motion.div>
      ) : (
        <motion.div
          key="selection-screen"
          variants={pageContainerVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          className="h-screen w-screen bg-gradient-to-b from-[#FAF9F7] via-[#F6F2EC] to-[#EFEAE2] font-body text-[#2C1810] flex flex-col overflow-hidden"
        >
          <StandardNavbar />

          <main className="flex-1 max-w-6xl w-full mx-auto p-6 flex flex-col justify-center min-h-0">
            <div className="flex flex-col items-center text-center">
              
              {/* Header Intro */}
              <motion.div variants={itemVariants} className="mb-10">
                <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-[#C5A059] font-bold inline-flex items-center gap-1.5 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#C5A059] animate-pulse" />
                  AI vs Human · Procedural Standing
                </span>
                <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight text-[#2C1810]">
                  Select Your Role
                </h1>
                <p className="font-body text-xs md:text-sm text-[#5D4037]/80 max-w-lg mx-auto mt-2 leading-relaxed">
                  Engage in an AI vs Human trial before the bench. Choose your procedural standing to face the AI opposing counsel.
                </p>
              </motion.div>

              {/* Three Clean Role Cards */}
              <motion.div
                variants={itemVariants}
                className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full"
              >
                {/* 1. Prosecutor */}
                <motion.div
                  whileHover={{
                    y: -6,
                    boxShadow: "0 20px 40px -10px rgba(140, 45, 25, 0.16)",
                  }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  onClick={() => handleSelectRole("prosecutor")}
                  className="group cursor-pointer bg-white/85 backdrop-blur-md border border-[#D4AF37]/35 hover:border-[#8C2D19] rounded-2xl p-8 flex flex-col items-center text-center relative overflow-hidden transition-colors"
                >
                  <div className="absolute top-3 right-3 px-2 py-0.5 rounded text-[8px] font-mono font-bold uppercase tracking-wider bg-[#8C2D19]/10 text-[#8C2D19] border border-[#8C2D19]/20">
                    You vs AI Defense
                  </div>

                  <motion.div
                    whileHover={{ scale: 1.08, rotate: -2 }}
                    transition={{ type: "spring", stiffness: 350, damping: 20 }}
                    className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#8C2D19] group-hover:bg-[#8C2D19] group-hover:text-[#FAF9F7] flex items-center justify-center mb-6 mt-2 transition-all duration-300 shadow-sm"
                  >
                    <Icons.Prosecution />
                  </motion.div>

                  <span className="font-mono text-[9px] uppercase tracking-widest text-[#8C2D19] font-bold mb-1">
                    The Accusation
                  </span>
                  <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Public Prosecutor
                  </h2>
                  <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                    Establish liability, tender discovery briefs, and pursue judicial conviction against the AI Defense Counsel.
                  </p>
                </motion.div>

                {/* 2. Defense */}
                <motion.div
                  whileHover={{
                    y: -6,
                    boxShadow: "0 20px 40px -10px rgba(212, 175, 55, 0.22)",
                  }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  onClick={() => handleSelectRole("defense")}
                  className="group cursor-pointer bg-white/85 backdrop-blur-md border border-[#D4AF37]/35 hover:border-[#D4AF37] rounded-2xl p-8 flex flex-col items-center text-center relative overflow-hidden transition-colors"
                >
                  <div className="absolute top-3 right-3 px-2 py-0.5 rounded text-[8px] font-mono font-bold uppercase tracking-wider bg-[#C5A059]/15 text-[#8C6D1F] border border-[#C5A059]/30">
                    You vs AI Prosecutor
                  </div>

                  <motion.div
                    whileHover={{ scale: 1.08, rotate: 2 }}
                    transition={{ type: "spring", stiffness: 350, damping: 20 }}
                    className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#2C1810] group-hover:bg-[#2C1810] group-hover:text-[#D4AF37] flex items-center justify-center mb-6 mt-2 transition-all duration-300 shadow-sm"
                  >
                    <Icons.Defense />
                  </motion.div>

                  <span className="font-mono text-[9px] uppercase tracking-widest text-[#8C6D1F] font-bold mb-1">
                    The Defense
                  </span>
                  <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Defense Counsel
                  </h2>
                  <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                    Challenge evidentiary integrity, raise procedural objections, and counter the AI Prosecutor's charges.
                  </p>
                </motion.div>

                {/* 3. Observer */}
                <motion.div
                  whileHover={{
                    y: -6,
                    boxShadow: "0 20px 40px -10px rgba(44, 24, 16, 0.16)",
                  }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  onClick={() => handleSelectRole("observer")}
                  className="group cursor-pointer bg-white/85 backdrop-blur-md border border-[#D4AF37]/35 hover:border-[#5D4037] rounded-2xl p-8 flex flex-col items-center text-center relative overflow-hidden transition-colors"
                >
                  <div className="absolute top-3 right-3 px-2 py-0.5 rounded text-[8px] font-mono font-bold uppercase tracking-wider bg-gray-100 text-gray-600 border border-gray-200">
                    AI vs AI Simulation
                  </div>

                  <motion.div
                    whileHover={{ scale: 1.08, rotate: -2 }}
                    transition={{ type: "spring", stiffness: 350, damping: 20 }}
                    className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#5D4037] group-hover:bg-[#2C1810] group-hover:text-[#D4AF37] flex items-center justify-center mb-6 mt-2 transition-all duration-300 shadow-sm"
                  >
                    <Icons.Observer />
                  </motion.div>

                  <span className="font-mono text-[9px] uppercase tracking-widest text-[#5D4037] font-bold mb-1">
                    The Gallery
                  </span>
                  <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                    Court Observer
                  </h2>
                  <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                    Monitor open proceedings, audit evidence logs, and review automated AI vs AI legal argumentation.
                  </p>
                </motion.div>
              </motion.div>

            </div>
          </main>
        </motion.div>
      )}
    </AnimatePresence>
  );
}