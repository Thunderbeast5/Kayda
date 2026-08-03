import { useState } from "react";
import { Scale, Shield, Gavel, Eye, Network } from "lucide-react";
import LexiGraphChoiceModal from "./LexiGraphChoiceModal";

export default function RoleSelector({ setUserRole, onEnterCourt }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const roles = [
    {
      id: "prosecutor",
      title: "Public Prosecutor",
      icon: <Scale className="text-[#5D4037] group-hover:text-[#D4AF37] transition-colors duration-500 w-7 h-7" strokeWidth={1.5} />,
      desc: "Construct the state's accusation, manage critical evidence, and argue for conviction.",
    },
    {
      id: "defense",
      title: "Defense Counsel",
      icon: <Shield className="text-[#5D4037] group-hover:text-[#D4AF37] transition-colors duration-500 w-7 h-7" strokeWidth={1.5} />,
      desc: "Advocate for the accused, contest evidence viability, and assert procedural rights.",
    },
    {
      id: "judge",
      title: "Judge",
      icon: <Gavel className="text-[#5D4037] group-hover:text-[#D4AF37] transition-colors duration-500 w-7 h-7" strokeWidth={1.5} />,
      desc: "Arbitrate objections, direct court proceedings, and deliver binding judgments.",
    },
    {
      id: "observer",
      title: "Observer",
      icon: <Eye className="text-[#5D4037] group-hover:text-[#D4AF37] transition-colors duration-500 w-7 h-7" strokeWidth={1.5} />,
      desc: "Monitor simulated proceedings, inspect agent reasoning, and audit trial dockets.",
    },
    {
      id: "lexigraph",
      title: "LexiGraph Agent",
      badge: "AI GRAPH",
      icon: <Network className="text-[#5D4037] group-hover:text-[#D4AF37] transition-colors duration-500 w-7 h-7" strokeWidth={1.5} />,
      desc: "Legal graph engine featuring Cypher query generation and GraphRAG legal retrieval.",
      action: () => setIsModalOpen(true)
    }
  ];

  return (
    <>
      <section 
        id="choose-role" 
        className="py-28 md:py-36 px-6 md:px-12 bg-gradient-to-b from-[#FAF8F5] to-[#F3EFE9] border-b border-[#E8E2D9]"
      >
        <div className="max-w-7xl mx-auto flex flex-col items-center">
          
          {/* Section Header */}
          <div className="text-center mb-16 md:mb-24">
            <div className="inline-flex items-center justify-center gap-2 mb-4">
              <span className="w-8 h-[1px] bg-[#C5A059]/50"></span>
              <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-[#C5A059] font-bold">
                Advocacy, Adjudication & Graph Intelligence
              </span>
              <span className="w-8 h-[1px] bg-[#C5A059]/50"></span>
            </div>
            
            <h2 className="font-heading text-3xl md:text-4xl lg:text-5xl font-bold text-[#2C1810] tracking-tight mb-5">
              Proceed as Counsel, Adjudicator<br className="hidden md:block" /> or Intelligence Engine
            </h2>
            <p className="font-body text-sm md:text-base text-[#5D4037]/80 max-w-2xl mx-auto leading-relaxed">
              Select your procedural capacity to initiate the simulation or access graph intelligence. 
              Each role grants specialized tools and perspectives within the environment.
            </p>
          </div>

          {/* Roles Grid (Converted to flex-wrap for better centering of 5 items) */}
          <div className="flex flex-wrap justify-center gap-6 md:gap-8 max-w-6xl w-full">
            {roles.map((role) => (
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
                className="group cursor-pointer flex flex-col items-center text-center bg-white/60 backdrop-blur-sm border border-[#E8E2D9] rounded-2xl p-8 md:p-10 transition-all duration-500 ease-out hover:-translate-y-2 hover:bg-white hover:border-[#D4AF37]/60 hover:shadow-[0_20px_40px_-15px_rgba(212,175,55,0.15)] relative overflow-hidden w-full sm:w-[calc(50%-16px)] lg:w-[calc(33.333%-22px)] max-w-[340px]"
              >
                {/* Premium Hover Gradient Effect */}
                <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#D4AF37]/[0.02] opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>

                {role.badge && (
                  <span className="absolute top-4 right-4 px-2.5 py-1 text-[9px] font-mono font-bold tracking-widest uppercase bg-[#2C1810] text-[#D4AF37] rounded-full shadow-sm z-10">
                    {role.badge}
                  </span>
                )}

                {/* Emblem Circle Wrapper */}
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-[#F5F2EC] to-[#E8E2D9] flex items-center justify-center mb-6 group-hover:scale-110 group-hover:from-[#D4AF37]/10 group-hover:to-[#D4AF37]/5 transition-all duration-500 shadow-inner z-10">
                  {role.icon}
                </div>

                {/* Role Label */}
                <h3 className="font-heading text-sm md:text-base tracking-[0.15em] font-bold uppercase text-[#2C1810] mb-3 group-hover:text-[#8C5A3C] transition-colors duration-500 z-10">
                  {role.title}
                </h3>
                
                {/* Description */}
                <p className="font-body text-[12px] md:text-[13px] text-[#5D4037]/70 leading-relaxed group-hover:text-[#2C1810]/80 transition-colors duration-500 z-10">
                  {role.desc}
                </p>

                {/* Bottom Border Accent line on hover */}
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-[#D4AF37] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
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