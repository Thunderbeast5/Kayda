import { motion } from "framer-motion";

// Container for orchestrating the vertical timeline steps
const timelineContainerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.14,
      delayChildren: 0.15,
    },
  },
};

// Motion variant for each sequential step
const stepItemVariants = {
  hidden: { opacity: 0, x: -16 },
  visible: {
    opacity: 1,
    x: 0,
    transition: {
      duration: 0.55,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function TrialLifecycleSection() {
  const steps = [
    {
      step: "01",
      title: "Create the Docket",
      text: "Upload the underlying facts, charge sheets, indictments, and discoverable materials. The system OCRs the documents and structures the case files."
    },
    {
      step: "02",
      title: "Select Council Role",
      text: "Choose to play as Public Prosecutor, Defense Counsel, or the presiding Judge. Or, designate AI agents to play all three roles while you audit the chamber."
    },
    {
      step: "03",
      title: "Commence Proceedings",
      text: "The conversational interface initializes. You or the AI opposing counsel present oral arguments. Opposing agents raise objections based on the legal record."
    },
    {
      step: "04",
      title: "Judicial Decision",
      text: "After completing cross-examination and oral statements, the Judge Agent evaluates the filings and transcripts to deliver a detailed written judgment."
    },
    {
      step: "05",
      title: "Obtain Trial Audit",
      text: "Export complete trial transcripts, receive analytical feedback on objection timing, argument structure, and get a legal guidance checklist."
    }
  ];

  return (
    <section className="py-14 sm:py-20 md:py-28 lg:py-32 px-4 sm:px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5] overflow-hidden">
      <div className="max-w-5xl mx-auto">
        {/* Section Heading */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-10 sm:mb-14 md:mb-20"
        >
          <span className="font-mono text-[9px] sm:text-[10px] md:text-xs uppercase tracking-[0.22em] sm:tracking-[0.3em] text-gold font-bold mb-2 block">
            WORKFLOW METRICS
          </span>
          <h2 className="font-heading text-2xl sm:text-3xl md:text-4xl lg:text-5xl text-wood-dark tracking-tight mb-3 sm:mb-4 px-2">
            The Trial Lifecycle
          </h2>
          <p className="font-body text-xs sm:text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed px-2">
            How to initiate a simulated court case, define the counsel parameters, and obtain official analytics.
          </p>
        </motion.div>

        {/* Timeline Wrapper */}
        <div className="relative pl-0 sm:pl-2 md:pl-6 max-w-3xl mx-auto">
          {/* Background Track (Muted Line) */}
          <div className="absolute left-[15px] sm:left-[19px] md:left-[35px] top-4 bottom-4 w-px bg-surface-border/60" />

          {/* Animated Gold Fill Track */}
          <motion.div
            initial={{ scaleY: 0 }}
            whileInView={{ scaleY: 1 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
            style={{ originY: 0 }}
            className="absolute left-[15px] sm:left-[19px] md:left-[35px] top-4 bottom-4 w-px bg-gradient-to-b from-gold via-gold/70 to-transparent"
          />

          {/* Sequential Step Items */}
          <motion.div
            variants={timelineContainerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-40px" }}
            className="space-y-7 sm:space-y-9 md:space-y-11"
          >
            {steps.map((lif, i) => (
              <motion.div
                key={i}
                variants={stepItemVariants}
                whileHover={{ x: 3 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="flex relative items-start pl-11 sm:pl-14 md:pl-16 group cursor-default"
              >
                {/* Step Circle Pin */}
                <motion.div
                  whileHover={{ scale: 1.1, rotate: 2 }}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                  className="absolute left-0 top-0.5 sm:top-0 w-[30px] h-[30px] sm:w-[38px] sm:h-[38px] md:w-10 md:h-10 rounded-full bg-white border border-surface-border group-hover:border-gold flex items-center justify-center text-[10px] sm:text-xs font-mono font-bold text-gold shadow-sm group-hover:shadow-md transition-all duration-300 z-10 shrink-0"
                >
                  {lif.step}
                </motion.div>

                {/* Step Body */}
                <div className="min-w-0 pt-0.5 sm:pt-1">
                  <h3 className="font-heading text-base sm:text-lg md:text-xl font-bold text-wood-dark mb-1 group-hover:text-gold transition-colors duration-200">
                    {lif.title}
                  </h3>
                  <p className="font-body text-xs sm:text-[13px] md:text-sm text-textMuted leading-relaxed">
                    {lif.text}
                  </p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}