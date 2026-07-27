import { Scale, Network, ArrowRight } from "lucide-react";

export default function JudicialCouncilSection({ scrollToSection }) {
  const agents = [
    {
      title: "Prosecutor Agent",
      role: "Oral Advocacy & Charge Construction",
      desc: "Synthesizes hostile arguments and coordinates the state’s evidentiary submissions to test the defense’s positions under adversarial pressure."
    },
    {
      title: "Defense Agent",
      role: "Client Defense & Cross-Examination",
      desc: "Locates legal discrepancies in the prosecution's docket, challenges witness statements, and raises critical procedural objections."
    },
    {
      title: "Judge Agent",
      role: "Procedural Adjudication",
      desc: "Governs courtroom protocol, reviews motion records, adjudicates objections under the relevant penal codes, and delivers structured written judgments."
    },
    {
      title: "Evidence Analyzer Agent",
      role: "Discovery Discovery & Analysis",
      desc: "Examines heavy case files, extracts relevant facts, indexes exhibits, and highlights inconsistent statements made by witnesses during the trial."
    },
    {
      title: "LexiGraph Agent",
      role: "Semantic Legal Graphing",
      desc: "Connects actors, dates, transactions, and jurisdictions from case materials, tracing a comprehensive visual timeline of facts for the litigation team."
    },
    {
      title: "Research Agent",
      role: "Precedent & Case Law Search",
      desc: "Performs low-latency indexing of appellate database files, state archives, and historic judgments to fetch winning precedents dynamically."
    }
  ];

  return (
    <section id="agents" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            THE CONVERSATIONAL ECOSYSTEM
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            The Judicial Council
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Meet the specialized legal intelligences built to coordinate, challenge, and adjudicate within the Kayda simulated environment.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((ag, i) => (
            <div key={i} className="bg-white p-6 border border-surface-border relative group hover:shadow-md hover:translate-y-[-2px] transition-all duration-300">
              <div className="w-10 h-10 border border-gold/40 flex items-center justify-center text-gold mb-4 group-hover:bg-gold/10 transition-colors">
                <Scale size={18} strokeWidth={1.5} />
              </div>
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
          ))}
          
          {/* The 7th Agent spans 3 cols on large screens */}
          <div className="bg-white p-6 border border-surface-border relative group hover:shadow-md hover:translate-y-[-2px] transition-all duration-300 lg:col-span-3 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 border border-gold/40 flex items-center justify-center text-gold shrink-0 mt-1 md:mt-0">
                <Network size={18} strokeWidth={1.5} />
              </div>
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
            <button 
              onClick={() => scrollToSection("workspace")} 
              className="font-body text-[10px] uppercase tracking-wider font-bold text-wood-dark hover:underline flex items-center gap-1.5 cursor-pointer shrink-0"
            >
              Explore Workspace Support <ArrowRight size={12} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
