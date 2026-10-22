import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import LexiGraphChoiceModal from "./LexiGraphChoiceModal";

// Container variant for staggering cards
const gridVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
};

// Individual card entry variant
const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function WorkspaceUtilitiesSection() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const navigate = useNavigate();

  const tools = [
    { 
      title: "Evidence Analyzer", 
      desc: "Instantly scan and index discovery folders, identifying procedural inconsistencies across multiple witness testimonies.", 
      link: "/evidence-analyzer" 
    },
    { 
      title: "LexiGraph Intelligence", 
      desc: "Query IPC & BNS graph nodes, retrieve Supreme Court precedents, and generate Cypher statement execution graphs.", 
      openModal: true 
    },
    { 
      title: "Upload & Query", 
      desc: "Interact directly with dense case briefs, pleading files, and administrative records through a semantic conversational panel." 
    },
    { 
      title: "Legal Drafting Desk", 
      desc: "Generate legal templates, custom complaints, written declarations, and structured affidavits in standard court layouts." 
    },
    { 
      title: "Contract Analysis", 
      desc: "Isolate complex contract clauses, highlight latent liabilities, and receive risk assessments mapped to federal law." 
    },
    { 
      title: "Document Comparison", 
      desc: "Verify semantic changes and track modifications between pleading drafts with color-coded structural diffs." 
    },
    { 
      title: "Case Law Search", 
      desc: "Query databases containing supreme, state, and district rulings to identify winning precedents on similar facts." 
    },
    { 
      title: "Docket Management", 
      desc: "Organize complete case indices, track trial phases, archive past proceedings, and manage active trial summons." 
    }
  ];

  return (
    <>
      <section 
        id="workspace" 
        className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white"
      >
        <div className="max-w-6xl mx-auto">
          {/* Section Heading */}
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="text-center mb-16"
          >
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
              BEYOND THE TRIAL CHAMBERS
            </span>
            <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
              Supporting Workspace Utilities
            </h2>
            <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
              Powerful tools designed to assist your team in between simulated court proceedings. Extract records, search case law, and verify facts.
            </p>
          </motion.div>

          {/* Tools Grid */}
          <motion.div
            variants={gridVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-40px" }}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
          >
            {tools.map((tool, i) => {
              const isClickable = Boolean(tool.link || tool.openModal);

              return (
                <motion.div
                  key={i}
                  variants={cardVariants}
                  whileHover={
                    isClickable
                      ? { y: -4, transition: { duration: 0.25, ease: "easeOut" } }
                      : { y: -2, transition: { duration: 0.25, ease: "easeOut" } }
                  }
                  whileTap={isClickable ? { scale: 0.985 } : undefined}
                  onClick={() => {
                    if (tool.openModal) setIsModalOpen(true);
                    else if (tool.link) navigate(tool.link);
                  }}
                  className={`bg-white p-6 border border-surface-border relative flex flex-col justify-between group transition-all duration-300 rounded-sm ${
                    isClickable 
                      ? 'cursor-pointer hover:border-gold hover:shadow-md' 
                      : 'hover:border-wood-dark/20'
                  }`}
                >
                  {/* Subtle top indicator bar on clickable items */}
                  {isClickable && (
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />
                  )}

                  <div>
                    <h3 className="font-heading text-base font-bold text-wood-dark mb-2 group-hover:text-gold transition-colors">
                      {tool.title}
                    </h3>
                    <p className="font-body text-[11px] text-textMuted leading-relaxed mb-6">
                      {tool.desc}
                    </p>
                  </div>

                  {/* Status / Action Footer */}
                  <div className="pt-2">
                    {isClickable ? (
                      <div className="flex items-center gap-1 text-[#D4AF37] font-mono text-[9px] uppercase tracking-wider font-bold">
                        <span>LAUNCH DEMO</span>
                        <motion.span
                          className="inline-block"
                          initial={{ x: 0, y: 0 }}
                          whileHover={{ x: 2, y: -2 }}
                          transition={{ type: "spring", stiffness: 400, damping: 20 }}
                        >
                          <ArrowUpRight size={12} strokeWidth={2.5} />
                        </motion.span>
                      </div>
                    ) : (
                      <span className="font-mono text-[9px] uppercase tracking-wider font-bold text-gold/80 block">
                        READY SYSTEM ACCESS
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </section>

      <LexiGraphChoiceModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
      />
    </>
  );
}