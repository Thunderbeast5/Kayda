import { X, Terminal, Network, ArrowRight, ShieldCheck, Database, Layers } from "lucide-react";
import logo from "../../assets/logo1.svg";

export default function LexiGraphChoiceModal({ isOpen, onClose, onSelectCypher, onSelectAgent }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#2C1810]/60 backdrop-blur-md animate-fadeIn">
      {/* Modal Card */}
      <div 
        className="relative w-full max-w-3xl bg-[#FAF9F7] border border-[#D4AF37]/50 rounded-2xl shadow-[0_20px_50px_rgba(44,24,16,0.3)] overflow-hidden p-8 md:p-10"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 text-[#5D4037] hover:text-[#2C1810] rounded-full hover:bg-[#2C1810]/5 transition-colors cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <img src={logo} alt="Kayda Emblem" className="w-10 h-auto" />
          <div>
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.25em] text-[#C5A059] font-bold block">
              INTELLIGENCE ENGINE SELECTION
            </span>
            <h2 className="font-heading text-2xl md:text-3xl font-bold text-[#2C1810] tracking-tight">
              Select LexiGraph Mode
            </h2>
          </div>
        </div>

        <p className="font-body text-xs md:text-sm text-[#5D4037]/80 mb-8 leading-relaxed">
          LexiGraph features two complementary engines: a deterministic Cypher query translator for Neo4j, and a hierarchical GraphRAG agent for statutory mapping and legal reasoning.
        </p>

        {/* Dual Option Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Option 1: Cypher Engine */}
          <div 
            onClick={() => {
              onClose();
              if (onSelectCypher) onSelectCypher();
              else window.location.hash = "#/text2cypher";
            }}
            className="group cursor-pointer flex flex-col justify-between bg-white border border-[#2C1810]/15 rounded-xl p-6 hover:border-[#D4AF37] hover:shadow-lg hover:-translate-y-1 transition-all duration-300 relative overflow-hidden"
          >
            <div className="absolute top-3 right-3 px-2 py-0.5 text-[9px] font-mono font-bold tracking-wider uppercase bg-[#D4AF37]/15 text-[#8C5A3C] border border-[#D4AF37]/30 rounded-full flex items-center gap-1">
              <Database className="w-2.5 h-2.5" /> Cypher Engine
            </div>

            <div>
              <div className="w-12 h-12 rounded-xl bg-[#2C1810]/5 flex items-center justify-center text-[#2C1810] mb-5 group-hover:bg-[#D4AF37]/15 group-hover:text-[#8C5A3C] transition-colors duration-300">
                <Terminal className="w-6 h-6" strokeWidth={1.75} />
              </div>

              <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-2 group-hover:text-[#8C5A3C] transition-colors">
                LexiGraph Cypher
              </h3>

              <p className="font-body text-xs text-[#5D4037]/80 leading-relaxed mb-6">
                Translate natural language legal queries into Neo4j Cypher queries. View generated Cypher statements, database record nodes, and query execution metrics.
              </p>
            </div>

            <div className="pt-4 border-t border-[#2C1810]/10 flex items-center justify-between text-xs font-mono font-bold uppercase tracking-wider text-[#8C5A3C] group-hover:text-[#2C1810]">
              <span>Launch Cypher Engine</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>

          {/* Option 2: GraphRAG Legal Agent */}
          <div 
            onClick={() => {
              onClose();
              if (onSelectAgent) onSelectAgent();
              else window.location.hash = "#/lexigraph-agent";
            }}
            className="group cursor-pointer flex flex-col justify-between bg-white border border-[#2C1810]/15 rounded-xl p-6 hover:border-[#D4AF37] hover:shadow-lg hover:-translate-y-1 transition-all duration-300 relative overflow-hidden"
          >
            <div className="absolute top-3 right-3 px-2 py-0.5 text-[9px] font-mono font-bold tracking-wider uppercase bg-[#8C5A3C]/15 text-[#8C5A3C] border border-[#8C5A3C]/30 rounded-full flex items-center gap-1">
              <Layers className="w-2.5 h-2.5" /> GraphRAG Agent
            </div>

            <div>
              <div className="w-12 h-12 rounded-xl bg-[#2C1810]/5 flex items-center justify-center text-[#2C1810] mb-5 group-hover:bg-[#D4AF37]/15 group-hover:text-[#8C5A3C] transition-colors duration-300">
                <Network className="w-6 h-6" strokeWidth={1.75} />
              </div>

              <h3 className="font-heading text-lg font-bold text-[#2C1810] mb-2 group-hover:text-[#8C5A3C] transition-colors">
                LexiGraph Legal Agent
              </h3>

              <p className="font-body text-xs text-[#5D4037]/80 leading-relaxed mb-6">
                Hierarchical GraphRAG retrieval with automatic IPC <span className="font-semibold text-[#8C5A3C]">⇄</span> BNS statutory section mapping, Supreme Court precedent discovery, and ingredient verification.
              </p>
            </div>

            <div className="pt-4 border-t border-[#2C1810]/10 flex items-center justify-between text-xs font-mono font-bold uppercase tracking-wider text-[#8C5A3C] group-hover:text-[#2C1810]">
              <span>Launch Legal Agent</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </div>

        {/* Footer Note */}
        <div className="mt-8 pt-4 border-t border-[#2C1810]/10 flex items-center justify-between text-[11px] text-[#5D4037]/70 font-mono">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-[#C5A059]" />
            Supports Indian Penal Code (IPC) & Bharatiya Nyaya Sanhita (BNS)
          </span>
          <button 
            onClick={onClose}
            className="hover:underline cursor-pointer text-[#2C1810]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
