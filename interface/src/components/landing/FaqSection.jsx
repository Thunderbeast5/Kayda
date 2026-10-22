import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";

// Staggered container for FAQ items
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function FaqSection({ openFaqIndex, toggleFaq }) {
  const faqs = [
    {
      q: "Is my case discovery material private?",
      a: "Yes. All uploaded files, indictments, and trial transcripts are kept inside a sandboxed environment. We maintain SOC2 Type II compliance standards, and your client discovery files are never used to train generalized LLMs.",
    },
    {
      q: "How does the Judge Agent rule on objections?",
      a: "The Judge Agent checks submissions against penal codes, civil procedure rules, and evidence rules. The objection is sustained or overruled using real case citations indexed by the Research Agent, keeping proceedings procedurally accurate.",
    },
    {
      q: "Can I export courtroom transcripts for real trial prep?",
      a: "Absolutely. Court transcripts can be exported in standardized PDF format, formatted with margin guidelines and numbered line markers to match official court reporters.",
    },
    {
      q: "Can I customize the opponent agent's argumentative tone?",
      a: "Yes. When building your trial docket, you can adjust opposing counsel settings to represent various advocacy strategies, ranging from highly aggressive cross-examination to strictly cooperative procedural testing.",
    },
  ];

  return (
    <section
      id="faq"
      className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white"
    >
      <div className="max-w-3xl mx-auto">
        {/* Section Heading */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-16"
        >
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            RESOLVING CONCERNS
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            Frequently Asked Questions
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Transparent answers regarding data isolation, citation veracity, and simulated court settings.
          </p>
        </motion.div>

        {/* FAQs List */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-50px" }}
          className="space-y-4"
        >
          {faqs.map((faq, i) => {
            const isOpen = openFaqIndex === i;

            return (
              <motion.div
                key={i}
                variants={itemVariants}
                className={`border rounded-sm overflow-hidden transition-colors duration-300 ${
                  isOpen ? "border-gold/60 shadow-sm" : "border-surface-border"
                }`}
              >
                <button
                  type="button"
                  onClick={() => toggleFaq(i)}
                  className="w-full p-4.5 md:p-5 flex items-center justify-between text-left font-heading font-bold text-sm md:text-[15px] text-wood-dark hover:bg-[#FAF8F5] transition-colors cursor-pointer gap-4"
                >
                  <span className={isOpen ? "text-wood-dark" : "text-wood-dark/90"}>
                    {faq.q}
                  </span>

                  {/* Smooth rotating arrow icon */}
                  <motion.div
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ type: "spring", stiffness: 350, damping: 25 }}
                    className="text-gold shrink-0"
                  >
                    <ChevronDown size={17} />
                  </motion.div>
                </button>

                {/* Animated Accordion Content */}
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      key="content"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{
                        height: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
                        opacity: { duration: 0.25, delay: 0.05 },
                      }}
                      className="overflow-hidden"
                    >
                      <div className="p-4.5 md:p-5 border-t border-surface-border/60 bg-[#FAF8F5]/40">
                        <p className="font-body text-xs md:text-sm text-textMuted leading-relaxed">
                          {faq.a}
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}