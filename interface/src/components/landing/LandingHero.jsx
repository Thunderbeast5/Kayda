import { motion } from "framer-motion";
import heroBg from "../../assets/hero1.png";
import heroMobBg from "../../assets/hero-mob.png";

// Animation variants for clean, staggered entry
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.16,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.75,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function LandingHero({ scrollToSection }) {
  return (
    <div className="relative w-full overflow-hidden bg-[#FAF8F5]">
      {/* Background Layer: Mobile Asset (< md) */}
      <motion.div
        initial={{ scale: 1.05, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.4, ease: "easeOut" }}
        className="block md:hidden absolute inset-0 pointer-events-none bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: `url(${heroMobBg})`,
          maskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 70%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 70%, rgba(0,0,0,0) 100%)",
        }}
      />

      {/* Background Layer: Desktop/Tablet Asset (>= md) */}
      <motion.div
        initial={{ scale: 1.08, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.6, ease: "easeOut" }}
        className="hidden md:block absolute inset-0 pointer-events-none bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: `url(${heroBg})`,
          maskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
        }}
      />

      <motion.main
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="relative z-10 min-h-[100svh] max-w-[1400px] mx-auto px-5 sm:px-8 md:px-12 lg:px-16 pt-28 sm:pt-32 md:pt-36 pb-16 sm:pb-20 md:pb-24 flex flex-col justify-center"
      >
        {/* Main Headline */}
        <motion.h1
          variants={itemVariants}
          className="font-heading text-[32px] sm:text-[40px] md:text-[50px] lg:text-[62px] font-bold leading-[1.12] sm:leading-[1.08] tracking-tight sm:tracking-wide text-[#2C1810] mb-4 sm:mb-6 max-w-4xl"
        >
          Step Into the Courtroom.{" "}
          <span className="block sm:inline md:block lg:inline italic font-normal tracking-[-0.02em]">
            Master the Art of Legal Practice.
          </span>
        </motion.h1>

        {/* Subtitle / Paragraph */}
        <motion.p
          variants={itemVariants}
          className="text-[14px] sm:text-[15px] md:text-[16px] text-[#5D4037] max-w-[460px] md:max-w-[520px] mb-8 sm:mb-10 leading-[1.65] sm:leading-[1.7]"
        >
          The all-in-one conversational AI platform built for legal advocacy and
          document intelligence. Practice real-time arguments before specialized
          AI judges, analyze complex contracts in seconds, and draft bulletproof
          affidavits effortlessly.
        </motion.p>

        {/* CTA Buttons */}
        <motion.div
          variants={itemVariants}
          className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full sm:w-auto"
        >
          {/* Primary Button */}
          <motion.button
            whileHover={{ scale: 1.02, backgroundColor: "#3D2318" }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={() => scrollToSection("choose-role")}
            className="w-full sm:w-auto text-center px-6 sm:px-8 py-3.5 sm:py-4 bg-[#2C1810] text-[#FAF7F2] text-[11px] uppercase font-bold tracking-[0.14em] rounded border border-[#D4AF37] shadow-md hover:shadow-lg transition-shadow cursor-pointer"
          >
            Begin Simulation
          </motion.button>

          {/* Secondary Button */}
          <motion.button
            whileHover={{
              scale: 1.02,
              backgroundColor: "rgba(44, 26, 20, 0.07)",
              borderColor: "rgba(44, 26, 20, 0.6)",
            }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={() => scrollToSection("workspace")}
            className="w-full sm:w-auto text-center px-6 sm:px-8 py-3.5 sm:py-4 bg-transparent text-[#2C1810] text-[11px] uppercase font-medium tracking-[0.14em] rounded border border-[rgba(44,26,20,0.3)] transition-colors cursor-pointer"
          >
            Explore Document Suite
          </motion.button>
        </motion.div>
      </motion.main>
    </div>
  );
}