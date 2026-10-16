export default function SummonsCtaSection({ scrollToSection }) {
  return (
    <section id="pricing" className="py-24 px-6 md:px-12 bg-white border-b border-surface-border flex items-center justify-center">
      <div className="max-w-4xl w-full border border-surface-border bg-[#FAF8F5] p-8 md:p-16 text-center shadow-xl relative overflow-hidden">
        <div className="absolute inset-0 opacity-[0.015] bg-[radial-gradient(#5D4037_1px,transparent_1px)] [background-size:16px_16px]"></div>
        
        <span className="font-mono text-[9px] md:text-[10px] uppercase tracking-[0.3em] text-gold font-bold mb-4 block">
          OFFICIAL DOCKET // SUMMONS TO APPEAR
        </span>
        <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
          You Have Been Summoned.
        </h2>
        <p className="font-body text-xs md:text-sm text-primaryBrown/80 leading-relaxed max-w-xl mx-auto mb-8">
          Step directly into the simulated courtroom chambers. Choose your advocate profile, state your grounds, and let the AI bench hear your argument.
        </p>
        <button 
          onClick={() => scrollToSection("choose-role")}
          className="bg-wood-dark text-white font-body text-xs uppercase tracking-widest px-10 py-4 shadow-md hover:bg-wood-light transition-all font-bold cursor-pointer"
        >
          Enter Courtroom Chambers
        </button>
      </div>
    </section>
  );
}
