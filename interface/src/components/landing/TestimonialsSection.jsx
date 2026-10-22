export default function TestimonialsSection() {
  const testimonials = [
    {
      quote: "Kayda has completely transformed our pre-trial trial runs. We subjected our lead defense argument to their simulated court three times before trial. The AI Prosecutor exposed critical gaps in our evidence chain that we patched in time.",
      author: "Senior Litigation Partner",
      firm: "Chamber & Associates LLP"
    },
    {
      quote: "Running simulated cross-examinations against Kayda allows junior associates to build confidence and refine objection responses under dynamic courtroom protocol. It is mock trial preparation scaled for the modern firm.",
      author: "Director of Advocacy Training",
      firm: "National Institute of Legal Studies"
    },
    {
      quote: "Unlike basic chat tools that invent precedent, Kayda’s Research Agent and Judge Agent reference real citations. The platform does not hallucinate rulings—it evaluates arguments strictly on case law.",
      author: "Lead Legal Researcher",
      firm: "Appellate Strategy Group"
    }
  ];

  return (
    <section className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            ADMITTED TO THE COURT RECORD
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            Trial Partner Declarations
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Read how litigation partners, mock trial coordinators, and legal researchers prepare using Kayda.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((ts, i) => (
            <div key={i} className="bg-white p-6 border border-surface-border flex flex-col justify-between hover:shadow-sm transition-all duration-300">
              <p className="font-serif text-xs text-primaryBrown/90 italic leading-relaxed mb-6">
                "{ts.quote}"
              </p>
              <div>
                <h4 className="font-heading text-xs font-bold text-wood-dark">{ts.author}</h4>
                <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase block mt-0.5">{ts.firm}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
