import { ChevronDown } from "lucide-react";

export default function FaqSection({ openFaqIndex, toggleFaq }) {
  const faqs = [
    {
      q: "Is my case discovery material private?",
      a: "Yes. All uploaded files, indictments, and trial transcripts are kept inside a sandboxed environment. We maintain SOC2 Type II compliance standards, and your client discovery files are never used to train generalized LLMs."
    },
    {
      q: "How does the Judge Agent rule on objections?",
      a: "The Judge Agent checks submissions against penal codes, civil procedure rules, and evidence rules. The objection is sustaining or overruling using real case citations indexed by the Research Agent, keeping proceedings procedurally accurate."
    },
    {
      q: "Can I export courtroom transcripts for real trial prep?",
      a: "Absolutely. Court transcripts can be exported in standardized PDF format, formatted with margin guidelines and numbered line markers to match official court reporters."
    },
    {
      q: "Can I customize the opponent agent's argumentative tone?",
      a: "Yes. When building your trial docket, you can adjust opposing counsel settings to represent various advocacy strategies, ranging from highly aggressive cross-examination to strictly cooperative procedural testing."
    }
  ];

  return (
    <section id="faq" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            RESOLVING CONCERNS
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            Frequently Asked Questions
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Transparent answers regarding data isolation, citation veracity, and simulated court settings.
          </p>
        </div>

        <div className="space-y-4">
          {faqs.map((faq, i) => (
            <div key={i} className="border border-surface-border">
              <button 
                onClick={() => toggleFaq(i)}
                className="w-full p-4 flex items-center justify-between text-left font-heading font-bold text-sm text-wood-dark hover:bg-[#FAF8F5] transition-colors cursor-pointer"
              >
                <span>{faq.q}</span>
                <ChevronDown className={`text-gold shrink-0 transition-transform duration-300 ${openFaqIndex === i ? 'rotate-180' : ''}`} size={16} />
              </button>
              {openFaqIndex === i && (
                <div className="p-4 border-t border-surface-border bg-[#FAF8F5]/30">
                  <p className="font-body text-xs text-textMuted leading-relaxed">
                    {faq.a}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
