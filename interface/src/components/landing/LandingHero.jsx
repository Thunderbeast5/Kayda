import heroBg from "../../assets/hero1.png";

export default function LandingHero({ scrollToSection }) {
  return (
    <div className="relative w-full overflow-hidden bg-[#FAF8F5]">
      {/* Background Image Layer with Mask */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{ 
          backgroundImage: `url(${heroBg})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
          maskImage: "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)",
          WebkitMaskImage: "linear-gradient(to bottom, rgba(0,0,0,1) 75%, rgba(0,0,0,0) 100%)"
        }}
      />

      <main className="relative z-10 pt-32 px-6 md:px-14 max-w-[1400px] mx-auto min-h-screen flex flex-col justify-center pb-24">
        <h1 className="font-heading text-[46px] md:text-[58px] lg:text-[64px] font-bold leading-[1.05] tracking-wide text-[#2C1810] mb-6">
          Step Into the Courtroom. <br/>
          <span className="italic font-normal tracking-[-0.02em]">Master the Art of Legal Practice.</span>
        </h1>
        <p className="text-[15px] md:text-[16px] text-[#5D4037] max-w-[500px] mb-10 leading-[1.7]">
          The all-in-one conversational AI platform built for legal advocacy and document intelligence. Practice real-time arguments before specialized AI judges, analyze complex contracts in seconds, and draft bulletproof affidavits effortlessly.
        </p>
        <div className="flex flex-col sm:flex-row gap-4">
          <button 
            onClick={() => scrollToSection("choose-role")}
            className="px-8 py-4 bg-[#2C1810] text-[#FAF7F2] text-[11px] uppercase font-bold tracking-[0.14em] rounded border border-[#D4AF37] hover:bg-[#3D2318] transition-colors shadow-sm cursor-pointer"
          >
            Begin Simulation
          </button>
          <button 
            onClick={() => scrollToSection("workspace")}
            className="px-8 py-4 bg-transparent text-[#2C1810] text-[11px] uppercase font-medium tracking-[0.14em] rounded border border-[rgba(44,26,20,0.3)] hover:bg-[rgba(44,26,20,0.04)] transition-colors cursor-pointer"
          >
            Explore Document Suite
          </button>
        </div>
      </main>
    </div>
  );
}
