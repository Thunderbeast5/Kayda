export default function LandingFooter({ scrollToSection }) {
  return (
    <footer className="bg-white py-12 px-6 md:px-12 border-t border-surface-border text-center md:text-left">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="text-center md:text-left">
          <span className="font-heading font-black text-xl text-wood-dark tracking-tight block">
            Kayda
          </span>
          <span className="font-mono text-[9px] tracking-wider text-textMuted uppercase mt-1 block">
            CONVERSATIONAL TRIAL REALITY // COGNITIVE LAW SYSTEM
          </span>
        </div>
        <div className="flex flex-wrap justify-center gap-6 font-body text-[10px] uppercase tracking-wider text-textMuted">
          <button onClick={() => scrollToSection("choose-role")} className="hover:text-wood-dark cursor-pointer">Moot Court</button>
          <button onClick={() => scrollToSection("workspace")} className="hover:text-wood-dark cursor-pointer">Workspace</button>
          <button onClick={() => scrollToSection("agents")} className="hover:text-wood-dark cursor-pointer">Agents</button>
          <a href="#" className="hover:text-wood-dark">Terms of Protocol</a>
          <a href="#" className="hover:text-wood-dark">Privacy Ledger</a>
        </div>
      </div>
      <div className="max-w-6xl mx-auto border-t border-surface-border/50 mt-8 pt-8 flex flex-col md:flex-row justify-between items-center text-textMuted font-mono text-[8px] uppercase tracking-wider gap-4">
        <span>© 2026 KAYDA INC. ALL COURT TRANSCRIPTS SECURED UNDER PRIVACY ACT.</span>
        <span>RECORDED LOG SYSTEM INDEX CERTIFICATION #94-B</span>
      </div>
    </footer>
  );
}
