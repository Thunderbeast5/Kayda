import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Send, Check, X, Lock } from "lucide-react";
import logo from "../../assets/12.svg";

export default function LandingFooter({ scrollToSection }) {
  const navigate = useNavigate();

  // Newsletter state
  const [email, setEmail] = useState("");
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState("");

  // Modal dialog states (retained for Terms & Privacy links)
  const [activeModal, setActiveModal] = useState(null); // 'privacy' | 'terms' | null

  const handleSubscribe = (e) => {
    e.preventDefault();
    if (!email || !email.includes("@")) {
      setSubscriptionError("Please provide a valid institutional email address.");
      return;
    }
    setSubscriptionError("");
    setIsSubscribed(true);
  };

  const handleNav = (target) => {
    if (typeof target === "string" && target.startsWith("/")) {
      navigate(target);
    } else if (typeof target === "string") {
      if (scrollToSection) {
        scrollToSection(target);
      } else {
        const el = document.getElementById(target);
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  return (
    <footer className="bg-[#3E2723] text-[#FAF8F5] pt-16 pb-12 px-6 md:px-12 border-t-2 border-[#C5A059]/40 relative overflow-hidden">
      {/* Background ambient pattern */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#C5A059_1px,transparent_1px)] [background-size:20px_20px]" />

      <div className="max-w-7xl mx-auto relative z-10">
        {/* =========================================================================
            NEWSLETTER / COMPLIANCE UPDATE SUBSCRIPTION BANNER (UNTOUCHED)
           ========================================================================= */}
        <div className="bg-[#2E1A17]/85 border border-[#C5A059]/30 p-6 md:p-8 rounded-sm mb-16 shadow-2xl relative backdrop-blur-sm">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
            <div className="max-w-xl">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#C5A059]" />
                <span className="font-mono text-[9px] md:text-[10px] uppercase tracking-[0.25em] text-[#C5A059] font-bold">
                  LEGAL TECHNOLOGY BRIEFS // STATUTORY DISPATCHES
                </span>
              </div>
              <h3 className="font-heading text-xl md:text-2xl text-[#FAF8F5] tracking-tight mb-2">
                Subscribe to Institutional Legal Tech Updates
              </h3>
              <p className="font-body text-xs md:text-sm text-[#D7CCC8]/80 leading-relaxed">
                Receive curated fortnightly regulatory analyses, IPC/BNS neural indexing updates, and multi-agent trial simulation benchmark reports.
              </p>
            </div>

            <div className="w-full lg:w-auto lg:min-w-[420px]">
              {isSubscribed ? (
                <div className="flex items-center gap-3 bg-emerald-950/60 border border-emerald-500/40 p-3.5 rounded-sm text-emerald-200">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                    <Check className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div>
                    <p className="font-body text-xs font-semibold">Institutional Dispatch Confirmed</p>
                    <p className="font-mono text-[10px] text-emerald-300/80">
                      Dispatches will be delivered to <span className="underline">{email}</span>.
                    </p>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSubscribe} className="space-y-2">
                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (subscriptionError) setSubscriptionError("");
                      }}
                      placeholder="counsel@firm-name.com or institutional email"
                      className="bg-[#1D110F] border border-[#5D4037] text-xs text-[#FAF8F5] placeholder-[#8D6E63] focus:border-[#C5A059] focus:ring-1 focus:ring-[#C5A059]/40 px-3.5 py-2.5 rounded-sm flex-1 outline-none transition-all font-body"
                    />
                    <button
                      type="submit"
                      className="bg-[#C5A059] hover:bg-[#D4AF37] text-[#2E1A17] font-body text-xs uppercase tracking-wider font-bold px-5 py-2.5 rounded-sm transition-all duration-200 flex items-center justify-center gap-1.5 shrink-0 cursor-pointer shadow-md hover:shadow-lg"
                    >
                      <span>Subscribe</span>
                      <Send className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {subscriptionError && (
                    <p className="text-[10px] font-mono text-red-400">{subscriptionError}</p>
                  )}
                  <p className="text-[9px] font-mono text-[#A1887F] flex items-center gap-1.5">
                    <Lock className="w-2.5 h-2.5 text-[#C5A059]" />
                    Attorney-Client privilege standards strictly enforced. Zero external commercial sharing.
                  </p>
                </form>
              )}
            </div>
          </div>
        </div>

        {/* =========================================================================
            STRUCTURED SITEMAP
           ========================================================================= */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-8 mb-12 text-left">
          
          {/* Column 1: Brand Identity */}
          <div className="pr-0 lg:pr-4">
            <div className="flex items-center mb-3">
              <img src={logo} alt="Kayda Logo" className="w-14 h-auto" />
              <span className="font-heading text-2xl font-bold tracking-tight text-[#FAF8F5] -ml-[16px] mt-0.5">
                ayda
              </span>
            </div>
            <span className="font-mono text-[9px] tracking-[0.2em] text-[#C5A059] uppercase block mb-3 font-semibold">
              CONVERSATIONAL TRIAL REALITY // COGNITIVE LAW SYSTEM
            </span>
            <p className="font-body text-xs text-[#D7CCC8]/85 leading-relaxed max-w-sm">
              A high-precision cognitive litigation simulator for advocates, institutions, and judicial researchers. Test arguments against reactive multi-agent benches anchored in Indian Penal Code, BNS, and Supreme Court precedent graphs.
            </p>
          </div>

          {/* Column 2: Moot Court Simulation */}
          <div>
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#C5A059] font-bold mb-4 pb-1.5 border-b border-[#5D4037]/60">
              Moot Court Chambers
            </h4>
            <ul className="space-y-2.5 font-body text-xs text-[#D7CCC8]">
              <li>
                <button 
                  onClick={() => handleNav("choose-role")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Defense Counsel Station</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("choose-role")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Prosecution Bar</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("choose-role")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Judicial Observer Seat</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("simulation")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Live Centerpiece Simulation</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("faq")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Trial Lifecycle Protocol</span>
                </button>
              </li>
            </ul>
          </div>

          {/* Column 3: Workspace Utilities */}
          <div>
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#C5A059] font-bold mb-4 pb-1.5 border-b border-[#5D4037]/60">
              Workspace Utilities
            </h4>
            <ul className="space-y-2.5 font-body text-xs text-[#D7CCC8]">
              <li>
                <button 
                  onClick={() => handleNav("/evidence-analyzer")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Evidence Analyzer</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("/lexigraph-agent")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>LexiGraph Intelligence</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("/text2cypher")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Text-to-Cypher Explorer</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("workspace")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Legal Drafting Desk</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("workspace")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Precedent Knowledge Graph</span>
                </button>
              </li>
            </ul>
          </div>

          {/* Column 4: Agent Directory */}
          <div>
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#C5A059] font-bold mb-4 pb-1.5 border-b border-[#5D4037]/60">
              Agent Directory
            </h4>
            <ul className="space-y-2.5 font-body text-xs text-[#D7CCC8]">
              <li>
                <button 
                  onClick={() => handleNav("agents")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Judicial Council Bench</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleNav("agents")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Senior Defense Advocates</span>
                </button>
              </li>
            </ul>
          </div>

        </div>

        {/* Minimal clean divider */}
        <div className="h-px w-full bg-[#5D4037]/50 my-8" />

        {/* =========================================================================
            BOTTOM BAR: COPYRIGHT & LEGAL LINKS
           ========================================================================= */}
        <div className="flex flex-col sm:flex-row justify-between items-center text-[#D7CCC8]/70 font-mono text-[9px] uppercase tracking-wider gap-4">
          <p>© 2026 KAYDA INC. ALL COURT TRANSCRIPTS SECURED UNDER PRIVACY ACT &amp; ADVOCATES PROTOCOL.</p>
          <div className="flex items-center gap-4 text-[10px] text-[#A1887F]">
            <button 
              onClick={() => setActiveModal("terms")} 
              className="hover:text-[#C5A059] transition-colors cursor-pointer"
            >
              Terms of Protocol
            </button>
            <span>•</span>
            <button 
              onClick={() => setActiveModal("privacy")} 
              className="hover:text-[#C5A059] transition-colors cursor-pointer"
            >
              Privacy Ledger
            </button>
          </div>
        </div>

      </div>

      {/* =========================================================================
          LEGAL MODALS (TERMS & PRIVACY)
         ========================================================================= */}
      {activeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-[#FAF8F5] border-2 border-[#C5A059] text-[#212121] max-w-xl w-full p-6 md:p-8 rounded-sm shadow-2xl relative max-h-[90vh] overflow-y-auto">
            
            <button 
              onClick={() => setActiveModal(null)}
              className="absolute top-4 right-4 p-2 text-[#757575] hover:text-[#212121] transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Modal: Privacy Ledger */}
            {activeModal === "privacy" && (
              <div>
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-1">
                  PRIVACY PROTOCOL // DATA GOVERNANCE
                </span>
                <h3 className="font-heading text-2xl text-[#3E2723] mb-4 font-bold">
                  Privileged Counsel Data Isolation Ledger
                </h3>
                <div className="space-y-3 font-body text-xs text-[#5D4037] leading-relaxed">
                  <p>
                    <strong>1. Zero Data Retention on Discovery:</strong> Client filings, testimony transcripts, and draft evidence uploaded to Kayda are processed in ephemeral isolated memory contexts and never used to train public models.
                  </p>
                  <p>
                    <strong>2. End-to-End Cryptographic Isolation:</strong> All trial audio streams and written arguments are encrypted in transit via TLS 1.3 and at rest with AES-256 GCM keys held within your dedicated tenant space.
                  </p>
                  <p>
                    <strong>3. Statutory Attorney-Client Privilege Compliance:</strong> The platform architecture adheres to the Indian Evidence Act / BSA privilege doctrines and institutional bar association confidentiality bylaws.
                  </p>
                </div>
                <div className="mt-6 flex justify-end">
                  <button 
                    onClick={() => setActiveModal(null)}
                    className="bg-[#3E2723] text-white px-5 py-2 font-body text-xs uppercase tracking-wider font-bold cursor-pointer"
                  >
                    Close Ledger
                  </button>
                </div>
              </div>
            )}

            {/* Modal: Terms of Protocol */}
            {activeModal === "terms" && (
              <div>
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-1">
                  PROCEDURAL RULES // DISCIPLINARY CODE
                </span>
                <h3 className="font-heading text-2xl text-[#3E2723] mb-4 font-bold">
                  Terms of Courtroom Protocol
                </h3>
                <div className="space-y-3 font-body text-xs text-[#5D4037] leading-relaxed">
                  <p>
                    <strong>1. Simulated Court Disclaimer:</strong> The Kayda cognitive bench operates as an educational and procedural preparation simulator. AI bench rulings do not constitute formal legal counsel or binding decrees of actual courts.
                  </p>
                  <p>
                    <strong>2. Courtroom Decorum &amp; Ethics:</strong> Users engaging in oral arguments and testimony examination must adhere to standard judicial etiquette and professional standards of advocacy.
                  </p>
                  <p>
                    <strong>3. Precedent Graph Integrity:</strong> Citations referenced during argument are checked against official IPC, BNS, and Supreme Court records through the LexiGraph neural database.
                  </p>
                </div>
                <div className="mt-6 flex justify-end">
                  <button 
                    onClick={() => setActiveModal(null)}
                    className="bg-[#3E2723] text-white px-5 py-2 font-body text-xs uppercase tracking-wider font-bold cursor-pointer"
                  >
                    Acknowledge Protocol
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </footer>
  );
}