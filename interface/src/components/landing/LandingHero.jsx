import { motion } from "framer-motion";
import heroBg from "../../assets/hero1.png";
import heroTabBg from "../../assets/hero-tab.png";
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
      {/* Background Layer: Mobile Asset (< sm) */}
      <motion.div
        initial={{ scale: 1.05, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.4, ease: "easeOut" }}
        className="block sm:hidden absolute inset-0 pointer-events-none bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: `url(${heroMobBg})`,
          maskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
        }}
      />

      {/* Background Layer: Tablet Asset (sm to lg) */}
      <motion.div
        initial={{ scale: 1.06, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.5, ease: "easeOut" }}
        className="hidden sm:block lg:hidden absolute inset-0 pointer-events-none bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: `url(${heroTabBg})`,
          maskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
        }}
      />

      {/* Background Layer: Desktop Asset (>= lg) */}
      <motion.div
        initial={{ scale: 1.08, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 1.6, ease: "easeOut" }}
        className="hidden lg:block absolute inset-0 pointer-events-none bg-cover bg-center bg-no-repeat"
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
        className="relative z-10 min-h-[100svh] max-w-[1400px] mx-auto px-5 sm:px-8 md:px-12 lg:px-16 pt-24 sm:pt-28 md:pt-32 lg:pt-36 pb-8 sm:pb-12 md:pb-14 lg:pb-24 flex flex-col justify-between lg:justify-center"
      >
        {/* Top Area: Headline pinned below navbar on mobile & tab */}
        <div className="w-full">
          <motion.h1
            variants={itemVariants}
            className="font-heading text-[28px] xs:text-[32px] sm:text-[42px] md:text-[52px] lg:text-[62px] font-bold leading-[1.15] sm:leading-[1.1] md:leading-[1.08] tracking-tight sm:tracking-wide text-[#2C1810] mb-0 lg:mb-6 max-w-4xl"
          >
            <span className="block">Step Into the Courtroom.</span>
            <span className="block sm:block lg:inline italic font-normal tracking-[-0.02em]">
              Master the Art of Legal Practice.
            </span>
          </motion.h1>

          {/* Subtitle / Paragraph: Hidden on both Mobile & Tab (< lg), visible only on Desktop */}
          <motion.p
            variants={itemVariants}
            className="hidden lg:block text-[16px] text-[#5D4037] max-w-[520px] mb-10 leading-[1.7]"
          >
            The all-in-one conversational AI platform built for legal advocacy and
            document intelligence. Practice real-time arguments before specialized
            AI judges, analyze complex contracts in seconds, and draft bulletproof
            affidavits effortlessly.
          </motion.p>
        </div>

        {/* CTA Buttons: Anchored to the bottom on Mobile & Tab (< lg), centered layout on Desktop */}
        <motion.div
          variants={itemVariants}
          className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full sm:w-auto mt-auto lg:mt-0"
        >
          {/* Primary Button */}
          <motion.button
            whileHover={{ scale: 1.02, backgroundColor: "#3D2318" }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            onClick={() => scrollToSection("choose-role")}
            className="w-full sm:w-auto text-center px-6 sm:px-8 py-3.5 sm:py-4 bg-[#2C1810] text-[#FAF7F2] text-[11px] uppercase font-bold tracking-[0.14em] rounded border border-[#D4AF37] shadow-md hover:shadow-lg transition-shadow cursor-pointer touch-manipulation"
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
            className="w-full sm:w-auto text-center px-6 sm:px-8 py-3.5 sm:py-4 bg-transparent text-[#2C1810] text-[11px] uppercase font-medium tracking-[0.14em] rounded border border-[rgba(44,26,20,0.3)] transition-colors cursor-pointer touch-manipulation"
          >
            Explore Document Suite
          </motion.button>
        </motion.div>
      </motion.main>
    </div>
  );
}