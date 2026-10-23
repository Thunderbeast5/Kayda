import { motion } from "framer-motion";
import { 
  Scale, 
  Gavel, 
  Shield, 
  FileSearch, 
  GitFork, 
  BookOpen, 
  FileSpreadsheet, 
  ArrowRight 
} from "lucide-react";

// Container variant for staggering grid cards
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.05,
    },
  },
};

// Card entry animation
const cardVariants = {
  hidden: { opacity: 0, y: 18 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function JudicialCouncilSection({ scrollToSection }) {
  const agents = [
    {
      title: "Prosecutor Agent",
      role: "Oral Advocacy & Charge Construction",
      desc: "Synthesizes hostile arguments and coordinates the state’s evidentiary submissions to test the defense’s positions under adversarial pressure.",
      icon: <Scale className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
    {
      title: "Defense Agent",
      role: "Client Defense & Cross-Examination",
      desc: "Locates legal discrepancies in the prosecution's docket, challenges witness statements, and raises critical procedural objections.",
      icon: <Shield className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
    {
      title: "Judge Agent",
      role: "Procedural Adjudication",
      desc: "Governs courtroom protocol, reviews motion records, adjudicates objections under the relevant penal codes, and delivers structured written judgments.",
      icon: <Gavel className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
    {
      title: "Evidence Analyzer Agent",
      role: "Discovery Discovery & Analysis",
      desc: "Examines heavy case files, extracts relevant facts, indexes exhibits, and highlights inconsistent statements made by witnesses during the trial.",
      icon: <FileSearch className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
    {
      title: "LexiGraph Agent",
      role: "Semantic Legal Graphing",
      desc: "Connects actors, dates, transactions, and jurisdictions from case materials, tracing a comprehensive visual timeline of facts for the litigation team.",
      icon: <GitFork className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
    {
      title: "Research Agent",
      role: "Precedent & Case Law Search",
      desc: "Performs low-latency indexing of appellate database files, state archives, and historic judgments to fetch winning precedents dynamically.",
      icon: <BookOpen className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />,
    },
  ];

  return (
    <section
      id="agents"
      className="py-14 sm:py-20 md:py-28 lg:py-32 px-4 sm:px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5] overflow-hidden"
    >
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-10 sm:mb-14 md:mb-16"
        >
          <span className="font-mono text-[9px] sm:text-[10px] md:text-xs uppercase tracking-[0.22em] sm:tracking-[0.3em] text-gold font-bold mb-2 block">
            THE CONVERSATIONAL ECOSYSTEM
          </span>
          <h2 className="font-heading text-2xl sm:text-3xl md:text-4xl lg:text-5xl text-wood-dark tracking-tight mb-3 sm:mb-4 px-2">
            The Judicial Council
          </h2>
          <p className="font-body text-xs sm:text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed px-2">
            Meet the specialized legal intelligences built to coordinate, challenge, and adjudicate within the Kayda simulated environment.
          </p>
        </motion.div>

        {/* Agents Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-30px" }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5 md:gap-6"
        >
          {agents.map((ag, i) => (
            <motion.div
              key={i}
              variants={cardVariants}
              whileHover={{
                y: -3,
                boxShadow: "0 10px 25px -5px rgba(44, 24, 16, 0.08)",
              }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="bg-white p-4.5 sm:p-5 md:p-6 border border-surface-border relative group rounded-sm flex flex-col justify-between"
            >
              {/* Subtle gold line accent on hover */}
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />

              <div>
                <motion.div
                  whileHover={{ rotate: 4 }}
                  transition={{ type: "spring", stiffness: 300 }}
                  className="w-9 h-9 sm:w-10 sm:h-10 border border-gold/40 flex items-center justify-center text-gold mb-3.5 sm:mb-4 group-hover:bg-gold/10 group-hover:border-gold transition-colors shrink-0"
                >
                  {ag.icon}
                </motion.div>

                <h3 className="font-heading text-base sm:text-lg font-bold text-wood-dark mb-1">
                  {ag.title}
                </h3>
                <span className="font-mono text-[8px] sm:text-[9px] uppercase tracking-wider text-primaryBrown font-bold mb-2.5 sm:mb-3 block leading-snug">
                  {ag.role}
                </span>
                <p className="font-body text-xs sm:text-[13px] text-textMuted leading-relaxed">
                  {ag.desc}
                </p>
              </div>
            </motion.div>
          ))}

          {/* 7th Agent (Full Width Footer Card) */}
          <motion.div
            variants={cardVariants}
            whileHover={{
              y: -3,
              boxShadow: "0 12px 28px -6px rgba(44, 24, 16, 0.08)",
            }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="bg-white p-4.5 sm:p-5 md:p-6 border border-surface-border relative group sm:col-span-2 lg:col-span-3 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 sm:gap-6 rounded-sm"
          >
            {/* Top border reveal */}
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />

            <div className="flex flex-col sm:flex-row items-start gap-3.5 sm:gap-4 w-full md:w-auto">
              <motion.div
                whileHover={{ rotate: 6 }}
                transition={{ type: "spring", stiffness: 300 }}
                className="w-9 h-9 sm:w-10 sm:h-10 border border-gold/40 flex items-center justify-center text-gold shrink-0 group-hover:bg-gold/10 group-hover:border-gold transition-colors"
              >
                <FileSpreadsheet className="w-4 h-4 sm:w-[18px] sm:h-[18px]" strokeWidth={1.5} />
              </motion.div>

              <div className="min-w-0">
                <h3 className="font-heading text-base sm:text-lg font-bold text-wood-dark mb-1">
                  Document Intelligence Agent
                </h3>
                <span className="font-mono text-[8px] sm:text-[9px] uppercase tracking-wider text-primaryBrown font-bold mb-2 block">
                  OCR & Semantic Clause Extraction
                </span>
                <p className="font-body text-xs sm:text-[13px] text-textMuted leading-relaxed max-w-3xl">
                  Parses unformatted litigation briefs, scans handwritten reports, recovers structural layouts, and transforms dense legal scans into semantically searchable databases.
                </p>
              </div>
            </div>

            {/* Action Button */}
            <motion.button
              whileHover="hovered"
              whileTap={{ scale: 0.98 }}
              onClick={() => scrollToSection("workspace")}
              className="w-full sm:w-auto font-body text-[10px] sm:text-[11px] uppercase tracking-wider font-bold text-wood-dark flex items-center justify-center md:justify-start gap-2 cursor-pointer shrink-0 py-2.5 px-3.5 rounded border border-surface-border md:border-transparent hover:bg-wood-dark/5 transition-colors touch-manipulation"
            >
              <span>Explore Workspace Support</span>
              <motion.span
                variants={{
                  hovered: { x: 4 },
                }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
              >
                <ArrowRight size={13} />
              </motion.span>
            </motion.button>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}