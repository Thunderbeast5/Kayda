export default function TrialLifecycleSection() {
  const steps = [
    { step: "01", title: "Create the Docket", text: "Upload the underlying facts, charge sheets, indictments, and discoverable materials. The system OCRs the documents and structures the case files." },
    { step: "02", title: "Select Council Role", text: "Choose to play as Public Prosecutor, Defense Counsel, or the presiding Judge. Or, designate AI agents to play all three roles while you audit the chamber." },
    { step: "03", title: "Commence Proceedings", text: "The conversational interface initializes. You or the AI opposing counsel present oral arguments. Opposing agents raise objections based on the legal record." },
    { step: "04", title: "Judicial Decision", text: "After completing cross-examination and oral statements, the Judge Agent evaluates the filings and transcripts to deliver a detailed written judgment." },
    { step: "05", title: "Obtain Trial Audit", text: "Export complete trial transcripts, receive analytical feedback on objection timing, argument structure, and get a legal guidance checklist." }
  ];

  return (
    <section className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            WORKFLOW METRICS
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            The Trial Lifecycle
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            How to initiate a simulated court case, define the counsel parameters, and obtain official analytics.
          </p>
        </div>

        <div className="space-y-8 relative before:absolute before:left-4 before:top-2 before:bottom-2 before:w-px before:bg-surface-border">
          {steps.map((lif, i) => (
            <div key={i} className="flex gap-6 relative items-start pl-8 group">
              <div className="absolute left-0 w-8 h-8 rounded-full bg-white border border-surface-border flex items-center justify-center text-xs font-mono font-bold text-gold group-hover:border-gold transition-colors">
                {lif.step}
              </div>
              <div>
                <h3 className="font-heading text-lg font-bold text-wood-dark mb-1">
                  {lif.title}
                </h3>
                <p className="font-body text-xs text-textMuted leading-relaxed max-w-2xl">
                  {lif.text}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
