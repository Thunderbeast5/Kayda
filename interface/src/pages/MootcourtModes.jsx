import { useState } from "react";
import StandardNavbar from "../components/StandardNavbar";
import CourtroomInterface from "../components/courtroom/CourtroomInterface";

// Precision Judicial Vectors (No Emojis)
const Icons = {
  Prosecution: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  ),
  Defense: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <circle cx="12" cy="11" r="3" />
    </svg>
  ),
  Observer: () => (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
};

export default function RoleSelectionPage() {
  const [selectedRole, setSelectedRole] = useState(null);

  const handleSelectRole = (role) => {
    setSelectedRole(role);
  };

  if (selectedRole) {
    return (
      <CourtroomInterface
        userRole={selectedRole}
        onExit={() => setSelectedRole(null)}
      />
    );
  }

  return (
    <div className="h-screen w-screen bg-gradient-to-b from-[#FAF9F7] via-[#F6F2EC] to-[#EFEAE2] font-body text-[#2C1810] flex flex-col overflow-hidden">
      <StandardNavbar />

      <main className="flex-1 max-w-6xl w-full mx-auto p-6 flex flex-col justify-center min-h-0">
        <div className="flex flex-col items-center text-center">
          
          {/* Header */}
          <div className="mb-10">
            <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-2">
              Procedural Capacity
            </span>
            <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight text-[#2C1810]">
              Designate Your Standing
            </h1>
            <p className="font-body text-xs md:text-sm text-[#5D4037]/80 max-w-lg mx-auto mt-2 leading-relaxed">
              Select an authorized capacity to enter the court session directly.
            </p>
          </div>

          {/* Three Clean Role Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
            
            {/* Prosecutor */}
            <div
              onClick={() => handleSelectRole("prosecutor")}
              className="group cursor-pointer bg-white/80 backdrop-blur-md border border-[#D4AF37]/30 hover:border-[#8C2D19] rounded-2xl p-8 flex flex-col items-center text-center transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_16px_36px_rgba(140,45,25,0.12)] relative overflow-hidden"
            >
              <div className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#8C2D19] group-hover:bg-[#8C2D19] group-hover:text-[#FAF9F7] flex items-center justify-center mb-6 transition-all duration-300 shadow-sm">
                <Icons.Prosecution />
              </div>
              <span className="font-mono text-[9px] uppercase tracking-widest text-[#8C2D19] font-bold mb-1">
                The Accusation
              </span>
              <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                Public Prosecutor
              </h2>
              <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                Establish liability, tender discovery briefs, and pursue judicial conviction.
              </p>
            </div>

            {/* Defense */}
            <div
              onClick={() => handleSelectRole("defense")}
              className="group cursor-pointer bg-white/80 backdrop-blur-md border border-[#D4AF37]/30 hover:border-[#D4AF37] rounded-2xl p-8 flex flex-col items-center text-center transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_16px_36px_rgba(212,175,55,0.16)] relative overflow-hidden"
            >
              <div className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#2C1810] group-hover:bg-[#2C1810] group-hover:text-[#D4AF37] flex items-center justify-center mb-6 transition-all duration-300 shadow-sm">
                <Icons.Defense />
              </div>
              <span className="font-mono text-[9px] uppercase tracking-widest text-[#8C6D1F] font-bold mb-1">
                The Defense
              </span>
              <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                Defense Counsel
              </h2>
              <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                Challenge evidentiary integrity, raise objections, and advocate for dismissal.
              </p>
            </div>

            {/* Observer */}
            <div
              onClick={() => handleSelectRole("observer")}
              className="group cursor-pointer bg-white/80 backdrop-blur-md border border-[#D4AF37]/30 hover:border-[#5D4037] rounded-2xl p-8 flex flex-col items-center text-center transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_16px_36px_rgba(44,24,16,0.12)] relative overflow-hidden"
            >
              <div className="w-16 h-16 rounded-full bg-[#FAF8F5] border border-[#D4AF37]/30 text-[#5D4037] group-hover:bg-[#2C1810] group-hover:text-[#D4AF37] flex items-center justify-center mb-6 transition-all duration-300 shadow-sm">
                <Icons.Observer />
              </div>
              <span className="font-mono text-[9px] uppercase tracking-widest text-[#5D4037] font-bold mb-1">
                The Gallery
              </span>
              <h2 className="font-heading text-xl font-bold text-[#2C1810] mb-2">
                Court Observer
              </h2>
              <p className="font-body text-xs text-[#5D4037]/75 leading-relaxed">
                Monitor open proceedings, audit evidence logs, and review legal argumentation.
              </p>
            </div>

          </div>

        </div>
      </main>
    </div>
  );
}