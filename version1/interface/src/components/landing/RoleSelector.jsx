import { useState } from "react";
import { Scale, Shield, Gavel, Eye, Network } from "lucide-react";
import LexiGraphChoiceModal from "./LexiGraphChoiceModal";

export default function RoleSelector({ setUserRole, onEnterCourt }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const roles = [
    {
      id: "prosecutor",
      title: "Public Prosecutor",
      icon: <Scale className="text-[#2C1810] group-hover:text-[#D4AF37] transition-colors duration-300 w-7 h-7" strokeWidth={1.5} />,
      desc: "Construct the state's accusation, manage critical evidence, and argue for conviction.",
    },
    {
      id: "defense",
      title: "Defense Counsel",
      icon: <Shield className="text-[#2C1810] group-hover:text-[#D4AF37] transition-colors duration-300 w-7 h-7" strokeWidth={1.5} />,
      desc: "Advocate for the accused, contest evidence viability, and assert procedural rights.",
    },
    {
      id: "judge",
      title: "Judge",
      icon: <Gavel className="text-[#2C1810] group-hover:text-[#D4AF37] transition-colors duration-300 w-7 h-7" strokeWidth={1.5} />,
      desc: "Arbitrate objections, direct court proceedings, and deliver binding judgments.",
    },
    {
      id: "observer",
      title: "Observer",
      icon: <Eye className="text-[#2C1810] group-hover:text-[#D4AF37] transition-colors duration-300 w-7 h-7" strokeWidth={1.5} />,
      desc: "Monitor simulated proceedings, inspect agent reasoning, and audit trial dockets.",
    },
    {
      id: "lexigraph",
      title: "LexiGraph Agent",
      badge: "AI GRAPH",
      icon: <Network className="text-[#2C1810] group-hover:text-[#D4AF37] transition-colors duration-300 w-7 h-7" strokeWidth={1.5} />,
      desc: "Legal graph engine featuring Cypher query generation and GraphRAG legal retrieval.",
      action: () => setIsModalOpen(true)
    }
  ];

  return (
    <>
      <section id="choose-role" className="py-28 md:py-36 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
        <div className="max-w-7xl mx-auto flex flex-col items-center">
          <div className="text-center mb-16 md:mb-20">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-[#C5A059] font-bold mb-3 block">
              ADVOCACY, ADJUDICATION & GRAPH INTELLIGENCE
            </span>
            <h2 className="font-heading text-3xl md:text-4xl lg:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
              Proceed as Counsel, Adjudicator or Intelligence Engine
            </h2>
            <p className="font-body text-sm md:text-base text-[#5D4037]/80 max-w-xl mx-auto leading-relaxed">
              Select your procedural capacity to initiate the simulation or access graph intelligence.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 md:gap-8 max-w-6xl w-full justify-center">
            {roles.map(role => (
              <div 
                key={role.id}
                onClick={() => {
                  if (role.action) {
                    role.action();
                  } else {
                    setUserRole(role.id);
                    onEnterCourt();
                  }
                }}
                className="group cursor-pointer flex flex-col items-center select-none text-center bg-[#FAF9F7] border border-[#2C1810]/12 rounded-xl p-8 md:p-10 transition-all duration-300 transform hover:-translate-y-1 hover:border-[#D4AF37] hover:shadow-[0_8px_30px_rgba(212,175,55,0.06)] relative overflow-hidden"
              >
                {role.badge && (
                  <span className="absolute top-3 right-3 px-2 py-0.5 text-[9px] font-mono font-bold tracking-wider uppercase bg-[#D4AF37]/20 text-[#8C5A3C] border border-[#D4AF37]/40 rounded-full">
                    {role.badge}
                  </span>
                )}

                {/* Emblem Circle Wrapper */}
                <div className="w-16 h-16 rounded-full bg-[#2C1810]/5 flex items-center justify-center mb-6 group-hover:bg-[#D4AF37]/10 transition-colors duration-300">
                  {role.icon}
                </div>

                {/* Role Label */}
                <h3 className="font-heading text-xs md:text-sm tracking-[0.15em] font-bold uppercase text-[#2C1810] mb-2.5 transition-colors duration-300">
                  {role.title}
                </h3>
                
                {/* One Sentence Description */}
                <p className="font-body text-[11px] md:text-xs text-[#5D4037]/75 leading-relaxed max-w-[200px] group-hover:text-[#2C1810] transition-colors duration-300">
                  {role.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <LexiGraphChoiceModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
      />
    </>
  );
}
