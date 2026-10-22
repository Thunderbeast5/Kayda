import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

// Staggered sequence for summons contents
const cardContainerVariants = {
  hidden: { opacity: 0, y: 28, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.8,
      ease: [0.22, 1, 0.36, 1],
      staggerChildren: 0.12,
      delayChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.55,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function SummonsCtaSection({ scrollToSection }) {
  return (
    <section className="py-24 px-6 md:px-12 bg-white border-b border-surface-border flex items-center justify-center">
      <motion.div
        variants={cardContainerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-70px" }}
        className="max-w-4xl w-full border border-surface-border bg-[#FAF8F5] p-8 md:p-16 text-center shadow-xl relative overflow-hidden group rounded-sm"
      >
        {/* Subtle Background Pattern */}
        <div className="absolute inset-0 opacity-[0.025] bg-[radial-gradient(#5D4037_1px,transparent_1px)] [background-size:16px_16px] pointer-events-none" />

        {/* Legal Seal Corner Accents */}
        <div className="absolute top-3 left-3 w-3 h-3 border-t-2 border-l-2 border-gold/40 group-hover:border-gold transition-colors duration-300" />
        <div className="absolute top-3 right-3 w-3 h-3 border-t-2 border-r-2 border-gold/40 group-hover:border-gold transition-colors duration-300" />
        <div className="absolute bottom-3 left-3 w-3 h-3 border-b-2 border-l-2 border-gold/40 group-hover:border-gold transition-colors duration-300" />
        <div className="absolute bottom-3 right-3 w-3 h-3 border-b-2 border-r-2 border-gold/40 group-hover:border-gold transition-colors duration-300" />

        {/* Docket Header Tag */}
        <motion.div variants={itemVariants}>
          <span className="font-mono text-[9px] md:text-[10px] uppercase tracking-[0.3em] text-gold font-bold mb-4 inline-flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
            OFFICIAL DOCKET // SUMMONS TO APPEAR
          </span>
        </motion.div>

        {/* Heading */}
        <motion.h2
          variants={itemVariants}
          className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4"
        >
          You Have Been Summoned.
        </motion.h2>

        {/* Notice Description */}
        <motion.p
          variants={itemVariants}
          className="font-body text-xs md:text-sm text-primaryBrown/80 leading-relaxed max-w-xl mx-auto mb-9"
        >
          Step directly into the simulated courtroom chambers. Choose your advocate
          profile, state your grounds, and let the AI bench hear your argument.
        </motion.p>

        {/* CTA Button */}
        <motion.div variants={itemVariants}>
          <motion.button
            whileHover="hovered"
            whileTap={{ scale: 0.97 }}
            onClick={() => scrollToSection("choose-role")}
            className="inline-flex items-center gap-3 bg-wood-dark text-white font-body text-xs uppercase tracking-widest px-10 py-4 shadow-md hover:bg-wood-light transition-colors font-bold cursor-pointer rounded-sm border border-gold/30 hover:border-gold"
          >
            <span>Enter Courtroom Chambers</span>
            <motion.span
              variants={{
                hovered: { x: 4 },
              }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
            >
              <ArrowRight size={14} />
            </motion.span>
          </motion.button>
        </motion.div>
      </motion.div>
    </section>
  );
}