import { motion } from "framer-motion";
import { Quote } from "lucide-react";

// Staggered reveal for the 3 testimonial cards
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.14,
      delayChildren: 0.1,
    },
  },
};

const cardVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.7,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

export default function TestimonialsSection() {
  const testimonials = [
    {
      quote:
        "Kayda has completely transformed our pre-trial trial runs. We subjected our lead defense argument to their simulated court three times before trial. The AI Prosecutor exposed critical gaps in our evidence chain that we patched in time.",
      author: "Senior Litigation Partner",
      firm: "Chamber & Associates LLP",
    },
    {
      quote:
        "Running simulated cross-examinations against Kayda allows junior associates to build confidence and refine objection responses under dynamic courtroom protocol. It is mock trial preparation scaled for the modern firm.",
      author: "Director of Advocacy Training",
      firm: "National Institute of Legal Studies",
    },
    {
      quote:
        "Unlike basic chat tools that invent precedent, Kayda’s Research Agent and Judge Agent reference real citations. The platform does not hallucinate rulings—it evaluates arguments strictly on case law.",
      author: "Lead Legal Researcher",
      firm: "Appellate Strategy Group",
    },
  ];

  return (
    <section className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
      <div className="max-w-5xl mx-auto">
        {/* Section Heading */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="text-center mb-16"
        >
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            ADMITTED TO THE COURT RECORD
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            Trial Partner Declarations
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Read how litigation partners, mock trial coordinators, and legal researchers prepare using Kayda.
          </p>
        </motion.div>

        {/* Testimonials Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-50px" }}
          className="grid grid-cols-1 md:grid-cols-3 gap-6"
        >
          {testimonials.map((ts, i) => (
            <motion.div
              key={i}
              variants={cardVariants}
              whileHover={{
                y: -4,
                boxShadow: "0 12px 24px -6px rgba(44, 24, 16, 0.08)",
              }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="bg-white p-7 border border-surface-border relative flex flex-col justify-between group rounded-sm transition-colors duration-300 hover:border-gold/50"
            >
              {/* Gold Top Accent Line on Hover */}
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-gold scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left" />

              {/* Decorative Subtle Quote Icon */}
              <div className="text-gold/25 group-hover:text-gold/40 transition-colors duration-300 mb-3">
                <Quote size={20} />
              </div>

              {/* Quote Body */}
              <p className="font-serif text-xs md:text-[13px] text-primaryBrown/90 italic leading-relaxed mb-6">
                "{ts.quote}"
              </p>

              {/* Author & Firm Meta */}
              <div className="pt-4 border-t border-surface-border/50">
                <h4 className="font-heading text-xs font-bold text-wood-dark tracking-wide">
                  {ts.author}
                </h4>
                <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase block mt-0.5">
                  {ts.firm}
                </span>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}