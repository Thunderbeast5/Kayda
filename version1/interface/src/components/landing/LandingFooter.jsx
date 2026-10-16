import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { 
  ShieldCheck, 
  Lock, 
  Scale, 
  Award, 
  CheckCircle2, 
  ArrowRight, 
  Send, 
  Check, 
  X, 
  ExternalLink, 
  Activity, 
  Server, 
  FileText 
} from "lucide-react";

export default function LandingFooter({ scrollToSection }) {
  const navigate = useNavigate();
  
  // Newsletter state
  const [email, setEmail] = useState("");
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState("");

  // Modal dialog states
  const [activeModal, setActiveModal] = useState(null); // 'pricing' | 'privacy' | 'terms' | 'security' | null

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
            NEWSLETTER / COMPLIANCE UPDATE SUBSCRIPTION BANNER
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
            STRUCTURED MULTI-COLUMN SITEMAP
           ========================================================================= */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-10 lg:gap-8 mb-14 text-left">
          
          {/* Column 1: Platform / Brand Identity */}
          <div className="lg:col-span-2 pr-0 lg:pr-6">
            <div className="flex items-center gap-2.5 mb-3">
              <span className="w-7 h-7 rounded-sm bg-[#2E1A17] border border-[#C5A059]/50 flex items-center justify-center text-[#C5A059] shadow-sm">
                <Scale className="w-4 h-4" />
              </span>
              <span className="font-heading font-black text-2xl text-[#FAF8F5] tracking-tight">
                Kayda
              </span>
            </div>
            <span className="font-mono text-[9px] tracking-[0.2em] text-[#C5A059] uppercase block mb-3 font-semibold">
              CONVERSATIONAL TRIAL REALITY // COGNITIVE LAW SYSTEM
            </span>
            <p className="font-body text-xs text-[#D7CCC8]/85 leading-relaxed mb-5 max-w-md">
              A high-precision cognitive litigation simulator for advocates, institutions, and judicial researchers. Test arguments against reactive multi-agent benches anchored in Indian Penal Code, BNS, and Supreme Court precedent graphs.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => handleNav("choose-role")}
                className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-mono bg-[#2E1A17] hover:bg-[#5D4037] border border-[#C5A059]/40 text-[#FAF8F5] px-3 py-1.5 rounded-sm transition-colors cursor-pointer"
              >
                <span>Launch Court Chambers</span>
                <ArrowRight className="w-3 h-3 text-[#C5A059]" />
              </button>
              <button
                onClick={() => setActiveModal("pricing")}
                className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-mono bg-transparent hover:bg-[#2E1A17] border border-[#757575]/50 text-[#D7CCC8] hover:text-[#FAF8F5] px-3 py-1.5 rounded-sm transition-colors cursor-pointer"
              >
                <span>Pricing Plans</span>
              </button>
            </div>
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

          {/* Column 4: Agent Directory & Institutional Plans */}
          <div>
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#C5A059] font-bold mb-4 pb-1.5 border-b border-[#5D4037]/60">
              Agent Directory & Plans
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
              <li>
                <button 
                  onClick={() => setActiveModal("pricing")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group text-[#C5A059] font-semibold"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Pricing Plans & Tiers</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => setActiveModal("pricing")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Chambers Enterprise License</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => setActiveModal("security")}
                  className="hover:text-[#C5A059] transition-colors cursor-pointer flex items-center gap-1.5 group"
                >
                  <span className="text-[#C5A059] opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">›</span>
                  <span>Data Governance & SLA</span>
                </button>
              </li>
            </ul>
          </div>

        </div>

        {/* =========================================================================
            ENHANCED TRUST & SECURITY BADGES & PRIVACY ROW
           ========================================================================= */}
        <div className="bg-[#2E1A17]/50 border border-[#5D4037]/70 px-5 py-4 rounded-sm flex flex-col lg:flex-row items-center justify-between gap-4 mb-10">
          <div className="flex flex-wrap items-center justify-center lg:justify-start gap-4 text-[11px] font-body text-[#D7CCC8]">
            <span className="font-mono text-[9px] uppercase tracking-wider text-[#C5A059] font-bold">
              SECURITY STANDARDS:
            </span>
            <div className="flex items-center gap-1.5 bg-[#1D110F] px-2.5 py-1 rounded-sm border border-[#5D4037]">
              <ShieldCheck className="w-3.5 h-3.5 text-[#C5A059]" />
              <span className="font-mono text-[10px]">SOC-2 TYPE II AUDITED</span>
            </div>
            <div className="flex items-center gap-1.5 bg-[#1D110F] px-2.5 py-1 rounded-sm border border-[#5D4037]">
              <Lock className="w-3.5 h-3.5 text-[#C5A059]" />
              <span className="font-mono text-[10px]">AES-256 ENCRYPTED ISOLATION</span>
            </div>
            <div className="flex items-center gap-1.5 bg-[#1D110F] px-2.5 py-1 rounded-sm border border-[#5D4037]">
              <Scale className="w-3.5 h-3.5 text-[#C5A059]" />
              <span className="font-mono text-[10px]">ATTORNEY PRIVILEGE VAULT</span>
            </div>
            <div className="flex items-center gap-1.5 bg-[#1D110F] px-2.5 py-1 rounded-sm border border-[#5D4037]">
              <Award className="w-3.5 h-3.5 text-[#C5A059]" />
              <span className="font-mono text-[10px]">ISO 27001 ALIGNED</span>
            </div>
          </div>

          <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-[#A1887F]">
            <button 
              onClick={() => setActiveModal("terms")} 
              className="hover:text-[#C5A059] transition-colors cursor-pointer underline decoration-[#5D4037] underline-offset-4"
            >
              Terms of Protocol
            </button>
            <span>•</span>
            <button 
              onClick={() => setActiveModal("privacy")} 
              className="hover:text-[#C5A059] transition-colors cursor-pointer underline decoration-[#5D4037] underline-offset-4"
            >
              Privacy Ledger
            </button>
          </div>
        </div>

        {/* =========================================================================
            FINE GOLD-ACCENTED HORIZONTAL DIVIDER RULE
           ========================================================================= */}
        <div className="relative my-10">
          <div className="h-px w-full bg-gradient-to-r from-transparent via-[#C5A059] to-transparent opacity-60" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#3E2723] px-4">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rotate-45 bg-[#C5A059]" />
              <span className="font-mono text-[8px] md:text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold">
                SOVEREIGN TRIAL PROTOCOL // ADMINISTRATIVE METADATA
              </span>
              <span className="w-1.5 h-1.5 rotate-45 bg-[#C5A059]" />
            </div>
          </div>
        </div>

        {/* =========================================================================
            ADMINISTRATIVE METADATA, CERTIFICATION & LIVE SYSTEM STATUS INDICATOR
           ========================================================================= */}
        <div className="pt-4 flex flex-col md:flex-row justify-between items-center text-[#D7CCC8]/80 font-mono text-[9px] uppercase tracking-wider gap-4">
          
          <div className="text-center md:text-left">
            <span>© 2026 KAYDA INC. ALL COURT TRANSCRIPTS SECURED UNDER PRIVACY ACT &amp; ADVOCATES PROTOCOL.</span>
          </div>

          <div className="flex flex-wrap items-center justify-center md:justify-end gap-3.5">
            {/* Live System Status Indicator Pill */}
            <div 
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#2E1A17] border border-emerald-500/40 shadow-[0_0_12px_rgba(16,185,129,0.2)]"
              title="Real-time Node Status: IPC/BNS Knowledge Mesh Operational, Cognitive Latency 24ms"
            >
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="font-mono text-[9px] tracking-wider text-emerald-300 font-bold">
                All Cognitive Nodes Operational
              </span>
            </div>

            {/* System Certification Code */}
            <span className="bg-[#2E1A17] px-2.5 py-1 rounded-sm border border-[#5D4037] text-[#C5A059] font-bold">
              RECORDED LOG SYSTEM INDEX CERTIFICATION #94-B
            </span>
          </div>

        </div>

      </div>

      {/* =========================================================================
          INTERACTIVE MODALS: PRICING PLANS, PRIVACY LEDGER, TERMS, SECURITY
         ========================================================================= */}
      {activeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#FAF8F5] border-2 border-[#C5A059] text-[#212121] max-w-2xl w-full p-6 md:p-8 rounded-sm shadow-2xl relative max-h-[90vh] overflow-y-auto">
            
            {/* Close Button */}
            <button 
              onClick={() => setActiveModal(null)}
              className="absolute top-4 right-4 p-2 text-[#757575] hover:text-[#212121] transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Modal: Pricing Plans */}
            {activeModal === "pricing" && (
              <div>
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-1">
                  OFFICIAL INSTITUTIONAL SCHEDULE // LICENSURE
                </span>
                <h3 className="font-heading text-2xl text-[#3E2723] mb-2 font-bold">
                  Kayda Licensure &amp; Pricing Plans
                </h3>
                <p className="font-body text-xs text-[#5D4037] mb-6">
                  Transparent courtroom simulator tier access for independent advocates, litigation chambers, and law schools.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  {/* Tier 1 */}
                  <div className="border border-[#D7CCC8] p-4 bg-white flex flex-col justify-between">
                    <div>
                      <span className="font-mono text-[9px] text-[#757575] uppercase">Advocate Solo</span>
                      <h4 className="font-heading text-lg font-bold text-[#3E2723] mt-1">₹1,999<span className="text-xs font-normal text-[#757575]">/mo</span></h4>
                      <p className="font-body text-[11px] text-[#5D4037] mt-2 mb-4">
                        Full trial simulations with standard AI Bench. 50 cross-examinations per month.
                      </p>
                      <ul className="space-y-1.5 font-body text-[10px] text-[#212121]">
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> BNS &amp; IPC Statues</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Voice &amp; Text Argument</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Evidence Analyzer</li>
                      </ul>
                    </div>
                    <button 
                      onClick={() => { setActiveModal(null); handleNav("choose-role"); }}
                      className="mt-4 w-full bg-[#3E2723] hover:bg-[#5D4037] text-white font-body text-[10px] uppercase tracking-wider py-2 font-bold cursor-pointer transition-colors"
                    >
                      Start Free Trial
                    </button>
                  </div>

                  {/* Tier 2 */}
                  <div className="border-2 border-[#C5A059] p-4 bg-white relative flex flex-col justify-between shadow-md">
                    <span className="absolute -top-2.5 right-3 bg-[#C5A059] text-[#2E1A17] font-mono text-[8px] uppercase tracking-widest font-black px-2 py-0.5">
                      Recommended
                    </span>
                    <div>
                      <span className="font-mono text-[9px] text-[#C5A059] uppercase font-bold">Chambers Suite</span>
                      <h4 className="font-heading text-lg font-bold text-[#3E2723] mt-1">₹9,999<span className="text-xs font-normal text-[#757575]">/mo</span></h4>
                      <p className="font-body text-[11px] text-[#5D4037] mt-2 mb-4">
                        Multi-seat chambers licensing, custom evidentiary briefing, and live Cypher graph queries.
                      </p>
                      <ul className="space-y-1.5 font-body text-[10px] text-[#212121]">
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> 5 Counsel Seats</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Unlimited Simulations</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Custom Precedent Mesh</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Dedicated Latency Node</li>
                      </ul>
                    </div>
                    <button 
                      onClick={() => { setActiveModal(null); handleNav("choose-role"); }}
                      className="mt-4 w-full bg-[#C5A059] hover:bg-[#D4AF37] text-[#2E1A17] font-body text-[10px] uppercase tracking-wider py-2 font-bold cursor-pointer transition-colors"
                    >
                      Select Chambers
                    </button>
                  </div>

                  {/* Tier 3 */}
                  <div className="border border-[#D7CCC8] p-4 bg-white flex flex-col justify-between">
                    <div>
                      <span className="font-mono text-[9px] text-[#757575] uppercase">Institutional &amp; Univ</span>
                      <h4 className="font-heading text-lg font-bold text-[#3E2723] mt-1">Custom</h4>
                      <p className="font-body text-[11px] text-[#5D4037] mt-2 mb-4">
                        Law faculty bulk student licensing, moot court competition scoring, on-premise data isolation.
                      </p>
                      <ul className="space-y-1.5 font-body text-[10px] text-[#212121]">
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Unlimited Law Students</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Moot Court Tournament Mode</li>
                        <li className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#C5A059]" /> Custom Jurist Agents</li>
                      </ul>
                    </div>
                    <button 
                      onClick={() => { setActiveModal(null); handleNav("pricing"); }}
                      className="mt-4 w-full bg-[#5D4037] hover:bg-[#3E2723] text-white font-body text-[10px] uppercase tracking-wider py-2 font-bold cursor-pointer transition-colors"
                    >
                      Consult Registry
                    </button>
                  </div>
                </div>

                <div className="bg-[#FAF8F5] border border-[#D7CCC8] p-3 text-center">
                  <span className="font-mono text-[9px] uppercase tracking-wider text-[#757575]">
                    All plans include encrypted counsel workspace isolation and zero-training client confidentiality.
                  </span>
                </div>
              </div>
            )}

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

            {/* Modal: Security Standards */}
            {activeModal === "security" && (
              <div>
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-1">
                  INSTITUTIONAL AUDIT // SECURITY COMPLIANCE
                </span>
                <h3 className="font-heading text-2xl text-[#3E2723] mb-4 font-bold">
                  Security Standards &amp; SLA Controls
                </h3>
                <div className="space-y-3 font-body text-xs text-[#5D4037] leading-relaxed">
                  <p>
                    <strong>• SOC-2 Type II Certified:</strong> Third-party verified controls for security, availability, and procedural confidentiality.
                  </p>
                  <p>
                    <strong>• 99.98% Service Uptime SLA:</strong> High-availability deployment across distributed neural inference nodes guaranteeing uninterrupted courtroom simulation.
                  </p>
                  <p>
                    <strong>• ISO 27001 Information Security Management:</strong> Robust data handling controls mapped to rigorous international safety standards.
                  </p>
                </div>
                <div className="mt-6 flex justify-end">
                  <button 
                    onClick={() => setActiveModal(null)}
                    className="bg-[#3E2723] text-white px-5 py-2 font-body text-xs uppercase tracking-wider font-bold cursor-pointer"
                  >
                    Close Specifications
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