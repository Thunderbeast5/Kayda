export default function WorkspaceUtilitiesSection() {
  const tools = [
    { title: "Evidence Analyzer", desc: "Instantly scan and index discovery folders, identifying procedural inconsistencies across multiple witness testimonies.", link: true, href: "#/evidence-analyzer" },
    { title: "LexiGraph Explorer", desc: "Generate visual network graphs connecting legal actors, corporate bodies, transaction dates, and cited dockets.", link: true, href: "#/lexigraph-explorer" },
    { title: "Upload & Query", desc: "Interact directly with dense case briefs, pleading files, and administrative records through a semantic conversational panel." },
    { title: "Legal Drafting Desk", desc: "Generate legal templates, custom complaints, written declarations, and structured affidavits in standard court layouts." },
    { title: "Contract Analysis", desc: "Isolate complex contract clauses, highlight latent liabilities, and receive risk assessments mapped to federal law." },
    { title: "Document Comparison", desc: "Verify semantic changes and track modifications between pleading drafts with color-coded structural diffs." },
    { title: "Case Law Search", desc: "Query databases containing supreme, state, and district rulings to identify winning precedents on similar facts." },
    { title: "Docket Management", desc: "Organize complete case indices, track trial phases, archive past proceedings, and manage active trial sumons." }
  ];

  return (
    <section id="workspace" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
            BEYOND THE TRIAL CHAMBERS
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            Supporting Workspace Utilities
          </h2>
          <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
            Powerful tools designed to assist your team in between simulated court proceedings. Extract records, search case law, and verify facts.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {tools.map((tool, i) => (
            <div 
              key={i} 
              className={`bg-white p-6 border border-surface-border relative group hover:border-gold hover:shadow-sm transition-all duration-300 ${tool.link ? 'cursor-pointer' : ''}`}
              onClick={() => tool.link && tool.href && (window.location.hash = tool.href)}
            >
              <h3 className="font-heading text-base font-bold text-wood-dark mb-2">
                {tool.title}
              </h3>
              <p className="font-body text-[11px] text-textMuted leading-relaxed mb-6">
                {tool.desc}
              </p>
              <span className={`font-mono text-[9px] uppercase tracking-wider font-bold block ${tool.link ? 'text-[#D4AF37] group-hover:underline' : 'text-gold'}`}>
                {tool.link ? 'LAUNCH DEMO ➔' : 'READY SYSTEM ACCESS'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
