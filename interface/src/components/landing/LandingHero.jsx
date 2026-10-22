import { motion } from "framer-motion";
import heroBg from "../../assets/hero1.png";

// Animation variants for clean, staggered entry
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.18,
      delayChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.85,
      ease: [0.22, 1, 0.36, 1], // Custom smooth ease-out curve
    },
  },
};

export default function LandingHero({ scrollToSection }) {
  return (
    <div className="relative w-full overflow-hidden bg-[#FAF8F5]">
      {/* Background Layer with subtle zoom-out reveal */}
      <motion.div
        initial={{ scale: 1.08, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.6, ease: "easeOut" }}
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `url(${heroBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
          maskImage: "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage: "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
        }}
      />

      <motion.main
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="relative z-10 pt-32 px-6 md:px-14 max-w-[1400px] mx-auto min-h-screen flex flex-col justify-center pb-24"
      >
       
        

        {/* Main Headline */}
        <motion.h1
          variants={itemVariants}
          className="font-heading text-[46px] md:text-[58px] lg:text-[64px] font-bold leading-[1.05] tracking-wide text-[#2C1810] mb-6"
        >
          Step Into the Courtroom. <br />
          <span className="italic font-normal tracking-[-0.02em]">
            Master the Art of Legal Practice.
          </span>
        </motion.h1>

        {/* Subtitle / Paragraph */}
        <motion.p
          variants={itemVariants}
          className="text-[15px] md:text-[16px] text-[#5D4037] max-w-[500px] mb-10 leading-[1.7]"
        >
          The all-in-one conversational AI platform built for legal advocacy and
          document intelligence. Practice real-time arguments before specialized
          AI judges, analyze complex contracts in seconds, and draft bulletproof
          affidavits effortlessly.
        </motion.p>

        {/* CTA Buttons */}
        <motion.div
          variants={itemVariants}
          className="flex flex-col sm:flex-row gap-4"
        >
          {/* Primary Button */}
          <motion.button
            whileHover={{ scale: 1.025, backgroundColor: "#3D2318" }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={() => scrollToSection("choose-role")}
            className="px-8 py-4 bg-[#2C1810] text-[#FAF7F2] text-[11px] uppercase font-bold tracking-[0.14em] rounded border border-[#D4AF37] shadow-md hover:shadow-lg transition-shadow cursor-pointer"
          >
            Begin Simulation
          </motion.button>

          {/* Secondary Button */}
          <motion.button
            whileHover={{ 
              scale: 1.025, 
              backgroundColor: "rgba(44, 26, 20, 0.07)",
              borderColor: "rgba(44, 26, 20, 0.6)" 
            }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={() => scrollToSection("workspace")}
            className="px-8 py-4 bg-transparent text-[#2C1810] text-[11px] uppercase font-medium tracking-[0.14em] rounded border border-[rgba(44,26,20,0.3)] transition-colors cursor-pointer"
          >
            Explore Document Suite
          </motion.button>
        </motion.div>
      </motion.main>
    </div>
  );
}