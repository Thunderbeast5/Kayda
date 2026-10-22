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
      staggerChildren: 0.1,
      delayChildren: 0.05,
    },
  },
};

// Card entry animation
const cardVariants = {
  hidden: { opacity: 0, y: 22 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.65,
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
      icon: <Scale size={18} strokeWidth={1.5} />,
    },
    {
      title: "Defense Agent",
      role: "Client Defense & Cross-Examination",
      desc: "Locates legal discrepancies in the prosecution's docket, challenges witness statements, and raises critical procedural objections.",
      icon: <Shield size={18} strokeWidth={1.5} />,
    },
    {
      title: "Judge Agent",
      role: "Procedural Adjudication",
      desc: "Governs courtroom protocol, reviews motion records, adjudicates objections under the relevant penal codes, and delivers structured written judgments.",
      icon: <Gavel size={18} strokeWidth={1.5} />,
    },
    {
      title: "Evidence Analyzer Agent",
      role: "Discovery Discovery & Analysis",
      desc: "Examines heavy case files, extracts relevant facts, indexes exhibits, and highlights inconsistent statements made by witnesses during the trial.",
      icon: <FileSearch size={18} strokeWidth={1.5} />,
    },
    {
      title: "LexiGraph Agent",
      role: "Semantic Legal Graphing",
      desc: "Connects actors, dates, transactions, and jurisdictions from case materials, tracing a comprehensive visual timeline of facts for the litigation team.",
      icon: <GitFork size={18} strokeWidth={1.5} />,
    },
    {
      title: "Research Agent",
      role: "Precedent & Case Law Search",
      desc: "Performs low-latency indexing of appellate database files, state archives, and historic judgments to fetch winning precedents dynamically.",
      icon: <BookOpen size={18} strokeWidth={1.5} />,
    },
  ];

  return (
    <section
      id="agents"
      className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]"
    >
      <div className="max-w-6xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-16"
        >
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            THE CONVERSATIONAL ECOSYSTEM
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            The Judicial Council
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Meet the specialized legal intelligences built to coordinate, challenge, and adjudicate within the Kayda simulated environment.
          </p>
        </motion.div>

        {/* Agents Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-40px" }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {agents.map((ag, i) => (
            <motion.div
              key={i}
              variants={cardVariants}
              whileHover={{
                y: -4,
                boxShadow: "0 10px 25px -5px rgba(44, 24, 16, 0.08)",
              }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="bg-white p-6 border border-surface-border relative group rounded-sm flex flex-col justify-between"
            >
              {/* Subtle gold line accent on hover */}
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />

              <div>
                <motion.div
                  whileHover={{ rotate: 4 }}
                  transition={{ type: "spring", stiffness: 300 }}
                  className="w-10 h-10 border border-gold/40 flex items-center justify-center text-gold mb-4 group-hover:bg-gold/10 group-hover:border-gold transition-colors"
                >
                  {ag.icon}
                </motion.div>

                <h3 className="font-heading text-lg font-bold text-wood-dark mb-1">
                  {ag.title}
                </h3>
                <span className="font-mono text-[9px] uppercase tracking-wider text-primaryBrown font-bold mb-4 block">
                  {ag.role}
                </span>
                <p className="font-body text-xs text-textMuted leading-relaxed">
                  {ag.desc}
                </p>
              </div>
            </motion.div>
          ))}

          {/* 7th Agent (Full Width Footer Card) */}
          <motion.div
            variants={cardVariants}
            whileHover={{
              y: -4,
              boxShadow: "0 12px 28px -6px rgba(44, 24, 16, 0.08)",
            }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="bg-white p-6 border border-surface-border relative group lg:col-span-3 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 rounded-sm"
          >
            {/* Top border reveal */}
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />

            <div className="flex items-start gap-4">
              <motion.div
                whileHover={{ rotate: 6 }}
                transition={{ type: "spring", stiffness: 300 }}
                className="w-10 h-10 border border-gold/40 flex items-center justify-center text-gold shrink-0 mt-1 md:mt-0 group-hover:bg-gold/10 group-hover:border-gold transition-colors"
              >
                <FileSpreadsheet size={18} strokeWidth={1.5} />
              </motion.div>
              <div>
                <h3 className="font-heading text-lg font-bold text-wood-dark mb-1">
                  Document Intelligence Agent
                </h3>
                <span className="font-mono text-[9px] uppercase tracking-wider text-primaryBrown font-bold mb-2 block">
                  OCR & Semantic Clause Extraction
                </span>
                <p className="font-body text-xs text-textMuted leading-relaxed max-w-3xl">
                  Parses unformatted litigation briefs, scans handwritten reports, recovers structural layouts, and transforms dense legal scans into semantically searchable databases.
                </p>
              </div>
            </div>

            <motion.button
              whileHover="hovered"
              whileTap={{ scale: 0.97 }}
              onClick={() => scrollToSection("workspace")}
              className="font-body text-[10px] uppercase tracking-wider font-bold text-wood-dark flex items-center gap-2 cursor-pointer shrink-0 py-2 px-3 rounded hover:bg-wood-dark/5 transition-colors"
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