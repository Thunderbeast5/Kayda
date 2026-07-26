import { useState, useEffect, useRef } from "react";
import CourtroomStage from "../components/CourtroomStage";
import ChatPanel from "../components/ChatPanel";
import { 
  Network, 
  Briefcase, 
  Lightbulb, 
  Play, 
  Send, 
  Scale, 
  Hand, 
  BookOpen, 
  AlertTriangle, 
  GitCommit, 
  Menu, 
  X, 
  CheckCircle2, 
  ArrowRight, 
  ChevronDown, 
  ChevronLeft,
  ChevronRight,
  FileText, 
  Layers, 
  Search, 
  Shield, 
  Award, 
  Volume2, 
  VolumeX,
  Mic,
  Pause, 
  RotateCcw,
  Check,
  Compass,
  Gavel,
  Users,
  Eye
} from "lucide-react";

import heroBg from "../assets/hero1.png";
import logo from "../assets/logo1.svg";
import { getMockResponse } from "../data/mockTrialResponses";
import { uploadCaseFile } from "../firebase";

const centerpieceScript = [
  {
    type: "system",
    text: "[SYS LOG: SESSION ACTIVE // DOCKET 402-B // STATE V. SHARMA]"
  },
  {
    type: "speaker",
    agentId: "prosecutor",
    speaker: "Public Prosecutor",
    text: "May it please the Hon’ble Court. On the night of October 12th, the accused intentionally relocated the complainant's property without consent. The evidence establishes a clear case of theft under Section 379."
  },
  {
    type: "speaker",
    agentId: "defense",
    speaker: "Defense Counsel",
    text: "Objection, Your Honor! The prosecution has failed to establish the foundational requirement of dishonest intent (Mens Rea) at the time of the movement."
  },
  {
    type: "speaker",
    agentId: "judge",
    speaker: "Hon’ble Judge",
    text: "Sustained. The Public Prosecutor must establish direct evidence of intent before asserting theft. The defense's objection is noted."
  },
  {
    type: "system",
    text: "[SYS LOG: LEXIGRAPH LINKED // Precedent citation loaded: State of Maharashtra v. Vishwanath (1979)]"
  },
  {
    type: "speaker",
    agentId: "prosecutor",
    speaker: "Public Prosecutor",
    text: "Understood, Your Honor. We refer the Court to Exhibit C: the instant messaging transcript where the accused explicitly details a plan to retain the property."
  },
  {
    type: "speaker",
    agentId: "judge",
    speaker: "Hon’ble Judge",
    text: "Defense, how do you respond to the messaging transcript?"
  }
];

export default function HomePage() {
  const [activeScreen, setActiveScreen] = useState("landing"); // "landing" | "courtroom"
  const [userRole, setUserRole] = useState("defense"); // "prosecutor" | "defense" | "judge"
  
  if (activeScreen === "landing") {
    return (
      <LandingPage 
        userRole={userRole} 
        setUserRole={setUserRole} 
        onEnterCourt={() => setActiveScreen("courtroom")} 
      />
    );
  }

  return (
    <CourtroomInterface 
      userRole={userRole} 
      onExit={() => setActiveScreen("landing")} 
    />
  );
}

// LANDING PAGE COMPONENT
function LandingPage({ userRole, setUserRole, onEnterCourt }) {
  // Centerpiece Simulation State
  const [simMessages, setSimMessages] = useState([]);
  const [currentSimIndex, setCurrentSimIndex] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  
  // FAQ Accordion State
  const [openFaqIndex, setOpenFaqIndex] = useState(null);

  // Auto-scroll helper
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
  };

  // Centerpiece simulation effect
  useEffect(() => {
    if (!isPlaying) return;

    const currentMsg = centerpieceScript[currentSimIndex];
    if (!currentMsg) {
      // Pause at the end before restarting
      const timer = setTimeout(() => {
        setSimMessages([]);
        setCurrentSimIndex(0);
        setActiveSpeaker(null);
      }, 5000);
      return () => clearTimeout(timer);
    }

    setIsTyping(true);
    if (currentMsg.type === "system") {
      setActiveSpeaker(null);
      const timer = setTimeout(() => {
        setSimMessages(prev => [...prev, currentMsg]);
        setIsTyping(false);
        setCurrentSimIndex(prev => prev + 1);
      }, 2000);
      return () => clearTimeout(timer);
    } else {
      // Typewriter effect for agent dialogue
      setActiveSpeaker(currentMsg.agentId);
      let charIndex = 0;
      let typedText = "";
      
      // Initialize typed text box
      const tempMsg = { ...currentMsg, text: "" };
      setSimMessages(prev => [...prev, tempMsg]);
      
      const interval = setInterval(() => {
        if (charIndex < currentMsg.text.length) {
          typedText += currentMsg.text[charIndex];
          setSimMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = { ...currentMsg, text: typedText };
            return updated;
          });
          charIndex++;
        } else {
          clearInterval(interval);
          setIsTyping(false);
          const timer = setTimeout(() => {
            setCurrentSimIndex(prev => prev + 1);
          }, 2500);
        }
      }, 20); // typing speed
      
      return () => clearInterval(interval);
    }
  }, [currentSimIndex, isPlaying]);

  const toggleFaq = (index) => {
    setOpenFaqIndex(openFaqIndex === index ? null : index);
  };

  return (
    <div className="min-h-screen bg-white font-body text-textPrimary selection:bg-gold/30">

      {/* ══════════════════════════════════════════
          FLOATING LUXURY PILL NAV
      ══════════════════════════════════════════ */}
      <div className="fixed top-5 inset-x-0 z-50 flex justify-center px-6 pointer-events-none">
        <nav className="pointer-events-auto flex items-center justify-between w-full max-w-6xl px-7 py-3.5 rounded-full bg-[#FAF9F7]/80 backdrop-blur-md border border-[#D4AF37]/30 shadow-[0_10px_30px_rgba(44,24,16,0.08)]">
          
          {/* Logo + Emblem */}
          <div 
            className="flex items-center gap-3 cursor-pointer select-none"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          >
            <img src={logo} alt="Kayda Logo" className="w-6 h-auto" />
            <span className="font-heading text-xl font-bold tracking-tight text-[#2C1810]">Kayda</span>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center gap-8 text-[13px] font-semibold tracking-[0.08em] uppercase text-[#2C1810]/80">
            <button onClick={() => scrollToSection("choose-role")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1.5">
              Moot Court <span className="text-[10px] text-[#D4AF37]">✦</span>
            </button>
            <button onClick={() => { window.location.hash = '#/text2cypher'; }} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1">
              LexiGraph Cypher <span className="text-[10px] text-[#D4AF37]">✦</span>
            </button>
            <button onClick={() => { window.location.hash = '#/evidence-analyzer'; }} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1">
              Document Suite <span className="text-[10px] text-[#2C1810]/40">▾</span>
            </button>
            <button onClick={() => scrollToSection("drafting")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1">
              Drafting & Templates <span className="text-[10px] text-[#2C1810]/40">▾</span>
            </button>
            <button onClick={() => scrollToSection("pricing")} className="hover:text-[#8C5A3C] transition-colors">
              Pricing
            </button>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-5">
            <button className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#2C1810] hover:underline">
              Sign In
            </button>
            <button 
              onClick={() => scrollToSection("choose-role")}
              className="px-6 py-2.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(212,175,55,0.35)] transition-all duration-300"
            >
              Launch App
            </button>
          </div>
        </nav>
      </div>

      {/* ========================================== */}
      {/* DEMO HERO SECTION                          */}
      {/* ========================================== */}
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
          <h1 className="font-heading text-[46px] md:text-[58px] lg:text-[64px] font-bold leading-[1.05] tracking-[-0.02em] text-[#2C1810] mb-6">
            Step Into the Courtroom. <br/>
            <span className="italic font-normal">Master the Art of Legal Practice.</span>
          </h1>
          <p className="text-[15px] md:text-[16px] text-[#5D4037] max-w-[500px] mb-10 leading-[1.7]">
            The all-in-one conversational AI platform built for legal advocacy and document intelligence. Practice real-time arguments before specialized AI judges, analyze complex contracts in seconds, and draft bulletproof affidavits effortlessly.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <button 
              onClick={() => scrollToSection("choose-role")}
              className="px-8 py-4 bg-[#2C1810] text-[#FAF7F2] text-[11px] uppercase font-bold tracking-[0.14em] rounded border border-[#D4AF37] hover:bg-[#3D2318] transition-colors shadow-sm"
            >
              Begin Simulation
            </button>
            <button 
              onClick={() => scrollToSection("workspace")}
              className="px-8 py-4 bg-transparent text-[#2C1810] text-[11px] uppercase font-medium tracking-[0.14em] rounded border border-[rgba(44,26,20,0.3)] hover:bg-[rgba(44,26,20,0.04)] transition-colors"
            >
              Explore Document Suite
            </button>
          </div>
        </main>
      </div>



      {/* 2. CHOOSE YOUR ROLE SECTION */}
      <section id="choose-role" className="py-28 md:py-36 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
        <div className="max-w-6xl mx-auto flex flex-col items-center">
          <div className="text-center mb-16 md:mb-20">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-[#C5A059] font-bold mb-3 block">
              ADVOCACY OR ADJUDICATION
            </span>
            <h2 className="font-heading text-3xl md:text-4xl lg:text-5xl font-bold text-[#2C1810] tracking-tight mb-4">
              Proceed as Counsel or Adjudicator
            </h2>
            <p className="font-body text-sm md:text-base text-[#5D4037]/80 max-w-xl mx-auto leading-relaxed">
              Select your procedural capacity to initiate the simulation.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8 md:gap-10 max-w-5xl w-full justify-center">
            {[
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
              }
            ].map(role => (
              <div 
                key={role.id}
                onClick={() => {
                  setUserRole(role.id);
                  onEnterCourt();
                }}
                className="group cursor-pointer flex flex-col items-center select-none text-center bg-[#FAF9F7] border border-[#2C1810]/12 rounded-xl p-8 md:p-10 transition-all duration-300 transform hover:-translate-y-1 hover:border-[#D4AF37] hover:shadow-[0_8px_30px_rgba(212,175,55,0.06)]"
              >
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

      {/* 3. SIMULATION CENTERPIECE */}
      <section id="simulation" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
              REAL-TIME ORCHESTRATION SHOWN LIVE
            </span>
            <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
              The AI Courtroom Simulation
            </h2>
            <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
              Watch multiple AI entities coordinate, raise legal arguments, and rule dynamically. This is not static text generation—it is an ecosystem in constant adversarial motion.
            </p>
          </div>

          {/* SIMULATOR WINDOW CONTAINER */}
          <div className="border border-surface-border bg-white shadow-2xl relative">
            
            {/* Window bar */}
            <div className="bg-wood-dark px-4 py-3.5 flex items-center justify-between border-b border-wood-deep">
              <div className="flex items-center gap-4">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-800/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-yellow-600/60"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-green-800/60"></div>
                </div>
                <span className="font-mono text-[10px] tracking-wider text-[#FAF8F5]/80">
                  SESSION DOCKET: #402-B // CHAMBER_SIMULATOR
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button 
                  onClick={() => setIsPlaying(!isPlaying)} 
                  className="text-white/60 hover:text-white transition-colors"
                  title={isPlaying ? "Pause Simulation" : "Play Simulation"}
                >
                  {isPlaying ? <Pause size={14} /> : <Play fill="currentColor" size={14} />}
                </button>
                <button 
                  onClick={() => {
                    setSimMessages([]);
                    setCurrentSimIndex(0);
                    setActiveSpeaker(null);
                  }} 
                  className="text-white/60 hover:text-white transition-colors"
                  title="Reset Case Simulation"
                >
                  <RotateCcw size={14} />
                </button>
              </div>
            </div>

            {/* Simulated Avatars Header representing "ambient bench lighting" */}
            <div className="bg-[#FAF8F5] border-b border-surface-border px-6 py-6 grid grid-cols-3 gap-4 text-center">
              {[
                { id: "prosecutor", label: "Public Prosecutor", icon: <Scale size={20} /> },
                { id: "judge", label: "Hon'ble Judge", icon: <Hand size={20} /> },
                { id: "defense", label: "Defense Counsel", icon: <Briefcase size={20} /> }
              ].map(av => (
                <div 
                  key={av.id} 
                  className={`flex flex-col items-center justify-center p-3 border transition-all duration-300 ${activeSpeaker === av.id ? 'border-gold bg-white shadow-sm scale-105' : 'border-transparent opacity-50'}`}
                >
                  <div className={`p-2 rounded-full mb-1.5 ${activeSpeaker === av.id ? 'bg-gold/15 text-gold' : 'text-textMuted bg-gray-100'}`}>
                    {av.icon}
                  </div>
                  <span className="font-heading font-bold text-xs text-wood-dark">{av.label}</span>
                  <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase mt-0.5">
                    {activeSpeaker === av.id ? "Acutely Speaking" : "Idle Court record"}
                  </span>
                </div>
              ))}
            </div>

            {/* Dialogue screen */}
            <div className="h-[320px] overflow-y-auto p-6 space-y-4 bg-white select-none">
              {simMessages.map((msg, i) => {
                if (msg.type === "system") {
                  return (
                    <div key={i} className="text-center py-2">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-gold bg-gold/10 px-3 py-1 rounded">
                        {msg.text}
                      </span>
                    </div>
                  );
                }

                const isProsecutor = msg.agentId === "prosecutor";
                const isDefense = msg.agentId === "defense";
                const isJudge = msg.agentId === "judge";

                let sideBorder = "border-l-gold";
                if (isProsecutor) sideBorder = "border-l-[#1E3A8A]";
                if (isDefense) sideBorder = "border-l-[#991B1B]";

                return (
                  <div 
                    key={i} 
                    className={`bg-[#FAF8F5] border-l-4 ${sideBorder} p-4 rounded-r shadow-sm border-y border-r border-surface-border max-w-[85%] ${isProsecutor ? 'mr-auto' : isDefense ? 'ml-auto' : 'mx-auto'} animate-[fadeIn_0.3s_ease-out]`}
                  >
                    <div className="flex justify-between items-center mb-1 pb-1 border-b border-surface-border/40">
                      <span className="font-body font-bold text-[10px] uppercase tracking-wider text-wood-dark">
                        {msg.speaker}
                      </span>
                      <span className="font-mono text-[8px] text-textMuted font-bold">COURT FEED</span>
                    </div>
                    <p className="font-serif text-sm text-textPrimary leading-relaxed">
                      "{msg.text}"
                    </p>
                  </div>
                );
              })}
              {isTyping && (
                <div className="flex items-center gap-1.5 text-textMuted font-mono text-[9px] pl-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-gold animate-bounce [animation-delay:0.4s]"></span>
                  <span className="ml-1 uppercase tracking-wider">Agent preparing response...</span>
                </div>
              )}
            </div>

            {/* Bottom Status bar */}
            <div className="bg-[#FAF8F5] border-t border-surface-border px-4 py-3 flex items-center justify-between text-xs font-mono text-textMuted">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-600 animate-pulse"></div>
                <span>SIMULATOR STATUS: REAL-TIME SIMULATION DEMONSTRATION</span>
              </div>
              <span>DOCKET ARCHIVE INDEX #402</span>
            </div>
          </div>
        </div>
      </section>

      {/* 4. MEET THE AI AGENTS SECTION */}
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
            {[
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
            ].map((ag, i) => (
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
                className="font-body text-[10px] uppercase tracking-wider font-bold text-wood-dark hover:underline flex items-center gap-1.5"
              >
                Explore Workspace Support <ArrowRight size={12} />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* 5. LEGAL WORKSPACE SECTION */}
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
            {[
              { title: "Evidence Analyzer", desc: "Instantly scan and index discovery folders, identifying procedural inconsistencies across multiple witness testimonies.", link: true },
              { title: "LexiGraph Explorer", desc: "Generate visual network graphs connecting legal actors, corporate bodies, transaction dates, and cited dockets." },
              { title: "Upload & Query", desc: "Interact directly with dense case briefs, pleading files, and administrative records through a semantic conversational panel." },
              { title: "Legal Drafting Desk", desc: "Generate legal templates, custom complaints, written declarations, and structured affidavits in standard court layouts." },
              { title: "Contract Analysis", desc: "Isolate complex contract clauses, highlight latent liabilities, and receive risk assessments mapped to federal law." },
              { title: "Document Comparison", desc: "Verify semantic changes and track modifications between pleading drafts with color-coded structural diffs." },
              { title: "Case Law Search", desc: "Query databases containing supreme, state, and district rulings to identify winning precedents on similar facts." },
              { title: "Docket Management", desc: "Organize complete case indices, track trial phases, archive past proceedings, and manage active trial sumons." }
            ].map((tool, i) => (
              <div 
                key={i} 
                className={`bg-white p-6 border border-surface-border relative group hover:border-gold hover:shadow-sm transition-all duration-300 ${tool.link ? 'cursor-pointer' : ''}`}
                onClick={() => tool.link && (window.location.hash = '#/evidence-analyzer')}
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

      {/* 6. HOW KAYDA WORKS SECTION */}
      <section className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
              WORKFLOW METRICS
            </span>
            <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
              The Trial Lifecycle
            </h2>
            <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
              How to initiate a simulated court case, define the counsel parameters, and obtain official analytics.
            </p>
          </div>

          <div className="space-y-8 relative before:absolute before:left-4 before:top-2 before:bottom-2 before:w-px before:bg-surface-border">
            {[
              { step: "01", title: "Create the Docket", text: "Upload the underlying facts, charge sheets, indictments, and discoverable materials. The system OCRs the documents and structures the case files." },
              { step: "02", title: "Select Council Role", text: "Choose to play as Public Prosecutor, Defense Counsel, or the presiding Judge. Or, designate AI agents to play all three roles while you audit the chamber." },
              { step: "03", title: "Commence Proceedings", text: "The conversational interface initializes. You or the AI opposing counsel present oral arguments. Opposing agents raise objections based on the legal record." },
              { step: "04", title: "Judicial Decision", text: "After completing cross-examination and oral statements, the Judge Agent evaluates the filings and transcripts to deliver a detailed written judgment." },
              { step: "05", title: "Obtain Trial Audit", text: "Export complete trial transcripts, receive analytical feedback on objection timing, argument structure, and get a legal guidance checklist." }
            ].map((lif, i) => (
              <div key={i} className="flex gap-6 relative items-start pl-8 group">
                <div className="absolute left-0 w-8 h-8 rounded-full bg-white border border-surface-border flex items-center justify-center text-xs font-mono font-bold text-gold group-hover:border-gold transition-colors">
                  {lif.step}
                </div>
                <div>
                  <h3 className="font-heading text-lg font-bold text-wood-dark mb-1">
                    {lif.title}
                  </h3>
                  <p className="font-body text-xs text-textMuted leading-relaxed max-w-2xl">
                    {lif.text}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>



      {/* 8. TRUST & SOCIAL PROOF */}
      <section className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-[#FAF8F5]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
              ADMITTED TO THE COURT RECORD
            </span>
            <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
              Trial Partner Declarations
            </h2>
            <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
              Read how litigation partners, mock trial coordinators, and legal researchers prepare using Kayda.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                quote: "Kayda has completely transformed our pre-trial trial runs. We subjected our lead defense argument to their simulated court three times before trial. The AI Prosecutor exposed critical gaps in our evidence chain that we patched in time.",
                author: "Senior Litigation Partner",
                firm: "Chamber & Associates LLP"
              },
              {
                quote: "Running simulated cross-examinations against Kayda allows junior associates to build confidence and refine objection responses under dynamic courtroom protocol. It is mock trial preparation scaled for the modern firm.",
                author: "Director of Advocacy Training",
                firm: "National Institute of Legal Studies"
              },
              {
                quote: "Unlike basic chat tools that invent precedent, Kayda’s Research Agent and Judge Agent reference real citations. The platform does not hallucinate rulings—it evaluates arguments strictly on case law.",
                author: "Lead Legal Researcher",
                firm: "Appellate Strategy Group"
              }
            ].map((ts, i) => (
              <div key={i} className="bg-white p-6 border border-surface-border flex flex-col justify-between hover:shadow-sm transition-all duration-300">
                <p className="font-serif text-xs text-primaryBrown/90 italic leading-relaxed mb-6">
                  "{ts.quote}"
                </p>
                <div>
                  <h4 className="font-heading text-xs font-bold text-wood-dark">{ts.author}</h4>
                  <span className="font-mono text-[8px] tracking-wider text-textMuted uppercase block mt-0.5">{ts.firm}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 9. FAQ SECTION */}
      <section id="faq" className="py-24 md:py-32 px-6 md:px-12 border-b border-surface-border bg-white">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-16">
            <span className="font-mono text-[10px] md:text-xs uppercase tracking-[0.3em] text-gold font-bold mb-2 block">
              RESOLVING CONCERNS
            </span>
            <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
              Frequently Asked Questions
            </h2>
            <p className="font-body text-sm md:text-base text-primaryBrown/85 max-w-2xl mx-auto leading-relaxed">
              Transparent answers regarding data isolation, citation veracity, and simulated court settings.
            </p>
          </div>

          <div className="space-y-4">
            {[
              {
                q: "Is my case discovery material private?",
                a: "Yes. All uploaded files, indictments, and trial transcripts are kept inside a sandboxed environment. We maintain SOC2 Type II compliance standards, and your client discovery files are never used to train generalized LLMs."
              },
              {
                q: "How does the Judge Agent rule on objections?",
                a: "The Judge Agent checks submissions against penal codes, civil procedure rules, and evidence rules. The objection is sustaining or overruling using real case citations indexed by the Research Agent, keeping proceedings procedurally accurate."
              },
              {
                q: "Can I export courtroom transcripts for real trial prep?",
                a: "Absolutely. Court transcripts can be exported in standardized PDF format, formatted with margin guidelines and numbered line markers to match official court reporters."
              },
              {
                q: "Can I customize the opponent agent's argumentative tone?",
                a: "Yes. When building your trial docket, you can adjust opposing counsel settings to represent various advocacy strategies, ranging from highly aggressive cross-examination to strictly cooperative procedural testing."
              }
            ].map((faq, i) => (
              <div key={i} className="border border-surface-border">
                <button 
                  onClick={() => toggleFaq(i)}
                  className="w-full p-4 flex items-center justify-between text-left font-heading font-bold text-sm text-wood-dark hover:bg-[#FAF8F5] transition-colors"
                >
                  <span>{faq.q}</span>
                  <ChevronDown className={`text-gold shrink-0 transition-transform duration-300 ${openFaqIndex === i ? 'rotate-180' : ''}`} size={16} />
                </button>
                {openFaqIndex === i && (
                  <div className="p-4 border-t border-surface-border bg-[#FAF8F5]/30">
                    <p className="font-body text-xs text-textMuted leading-relaxed">
                      {faq.a}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 10. FINAL CTA (THE SUMMONS) */}
      <section className="py-24 px-6 md:px-12 bg-white border-b border-surface-border flex items-center justify-center">
        <div className="max-w-4xl w-full border border-surface-border bg-[#FAF8F5] p-8 md:p-16 text-center shadow-xl relative overflow-hidden">
          <div className="absolute inset-0 opacity-[0.015] bg-[radial-gradient(#5D4037_1px,transparent_1px)] [background-size:16px_16px]"></div>
          
          <span className="font-mono text-[9px] md:text-[10px] uppercase tracking-[0.3em] text-gold font-bold mb-4 block">
            OFFICIAL DOCKET // SUMMONS TO APPEAR
          </span>
          <h2 className="font-heading text-3xl md:text-5xl text-wood-dark tracking-tight mb-4">
            You Have Been Summoned.
          </h2>
          <p className="font-body text-xs md:text-sm text-primaryBrown/80 leading-relaxed max-w-xl mx-auto mb-8">
            Step directly into the simulated courtroom chambers. Choose your advocate profile, state your grounds, and let the AI bench hear your argument.
          </p>
          <button 
            onClick={() => scrollToSection("choose-role")}
            className="bg-wood-dark text-white font-body text-xs uppercase tracking-widest px-10 py-4 shadow-md hover:bg-wood-light transition-all font-bold"
          >
            Enter Courtroom Chambers
          </button>
        </div>
      </section>

      {/* 11. FOOTER */}
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
            <button onClick={() => scrollToSection("choose-role")} className="hover:text-wood-dark">Moot Court</button>
            <button onClick={() => scrollToSection("workspace")} className="hover:text-wood-dark">Workspace</button>
            <button onClick={() => scrollToSection("agents")} className="hover:text-wood-dark">Agents</button>
            <a href="#" className="hover:text-wood-dark">Terms of Protocol</a>
            <a href="#" className="hover:text-wood-dark">Privacy Ledger</a>
          </div>
        </div>
        <div className="max-w-6xl mx-auto border-t border-surface-border/50 mt-8 pt-8 flex flex-col md:flex-row justify-between items-center text-textMuted font-mono text-[8px] uppercase tracking-wider gap-4">
          <span>© 2026 KAYDA INC. ALL COURT TRANSCRIPTS SECURED UNDER PRIVACY ACT.</span>
          <span>RECORDED LOG SYSTEM INDEX CERTIFICATION #94-B</span>
        </div>
      </footer>

    </div>
  );
}

// COURTROOM INTERFACE COMPONENT
function CourtroomInterface({ userRole, onExit }) {
  const [messages, setMessages] = useState([]);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [status, setStatus] = useState("running"); 
  const [trialPhase, setTrialPhase] = useState("PROCEEDINGS INITIATION");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputText, setInputText] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const ttsEnabledRef = useRef(false);

  // PDF Case File Upload States
  const [caseData, setCaseData] = useState({
    fileId: "402-B",
    title: "State vs. Sharma",
    firNo: "2024/005",
    charge: "IPC 379",
    evidenceLinked: true
  });
  const [uploadStatus, setUploadStatus] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedFileName, setUploadedFileName] = useState("");

  const fileInputRef = useRef(null);

  // Speech-to-Text States
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognitionClass) {
        const rec = new SpeechRecognitionClass();
        rec.continuous = false;
        rec.interimResults = false;
        rec.lang = "en-IN";

        rec.onresult = (event) => {
          const transcript = event.results[0][0].transcript;
          if (transcript) {
            setInputText((prev) => {
              const spacing = prev ? " " : "";
              return prev + spacing + transcript;
            });
          }
        };

        rec.onerror = (e) => {
          console.error("Speech recognition error:", e);
          setIsListening(false);
        };

        rec.onend = () => {
          setIsListening(false);
        };

        recognitionRef.current = rec;
      }
    }
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("Speech-to-Text is not supported or permitted in this browser configuration. Please use Google Chrome.");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        console.error("Recognition start failed:", err);
      }
    }
  };

  const handleSidebarFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadedFileName(file.name);
    setUploadStatus("uploading");
    setUploadProgress(0);

    uploadCaseFile(file, (progress) => {
      setUploadProgress(progress);
    })
    .then((result) => {
      setUploadStatus("analyzing");
      
      setTimeout(() => {
        const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        const capitalize = (str) => str.replace(/\b\w/g, c => c.toUpperCase());
        
        const accuses = ["Karan Johar", "Rajesh Gupta", "Meera Sen", "Vikram Rathore", "Sanjay Mehta"];
        const selectedAccused = capitalize(cleanName.split(" ").slice(0, 2).join(" ")) || accuses[Math.floor(Math.random() * accuses.length)];
        const selectedCharge = cleanName.toLowerCase().includes("fraud") 
          ? "IPC 420" 
          : cleanName.toLowerCase().includes("assault") 
            ? "IPC 323" 
            : "IPC 379";
        
        const newCase = {
          fileId: Math.floor(Math.random() * 900 + 100).toString() + "-A",
          title: `State vs. ${selectedAccused}`,
          firNo: `2026/${Math.floor(Math.random() * 900 + 100)}`,
          charge: selectedCharge,
          evidenceLinked: true
        };

        setCaseData(newCase);
        setUploadStatus(null);
        
        setMessages([]);
        setActiveSpeaker("judge");
        setTrialPhase("PROCEEDINGS INITIATION");
        
        setTimeout(() => {
          handleEvent({
            agent_id: "judge",
            display_name: "Hon’ble Judge",
            full_text: `The court is now in session for the newly uploaded file. Case File ${newCase.fileId}: ${newCase.title}. Under charges of ${newCase.charge}, the Defense Counsel and Public Prosecutor may state their grounds.`,
            verified_citations: [],
          });
          
          setTimeout(() => {
            setActiveSpeaker("prosecutor");
            setTimeout(() => {
              handleEvent({
                agent_id: "prosecutor",
                display_name: "Public Prosecutor",
                full_text: `Your Honor, regarding the case of ${newCase.title}, the state submits that the evidence recovered from the accused's possession constitutes clear intent and action under ${newCase.charge}. We are prepared to proceed.`,
                verified_citations: [newCase.charge],
              });
              
              setTimeout(() => {
                setActiveSpeaker(null);
                setTrialPhase("DEFENSE REBUTTAL");
              }, 500);
            }, 800);
          }, 1000);

        }, 300);

      }, 1500);
    })
    .catch((err) => {
      console.error("Upload error:", err);
      setUploadStatus(null);
    });
  };

  useEffect(() => {
    ttsEnabledRef.current = ttsEnabled;
  }, [ttsEnabled]);

  useEffect(() => {
    // Disable body scroll when courtroom is active to prevent scrolling the landing page
    document.body.style.overflow = 'hidden';
    
    // Automatically trigger courtroom proceedings on mount
    startCasePractice();

    return () => {
      document.body.style.overflow = '';
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const speakText = (text, voiceRole) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel(); // stop current speech
    
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    
    // Find an English voice if available
    const englishVoice = voices.find(v => v.lang.startsWith("en-"));
    if (englishVoice) {
      utterance.voice = englishVoice;
    }
    
    if (voiceRole === "judge") {
      utterance.rate = 0.85;
      utterance.pitch = 0.95;
    } else if (voiceRole === "prosecutor") {
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
    } else if (voiceRole === "defense") {
      utterance.rate = 1.0;
      utterance.pitch = 1.05;
    }
    
    window.speechSynthesis.speak(utterance);
  };

  const roleNameMap = {
    prosecutor: "Public Prosecutor",
    defense: "Defense Counsel",
    judge: "Hon’ble Judge",
    observer: "Court Observer"
  };

  const handleEvent = (event) => {
    setActiveSpeaker(event.agent_id);
    setMessages((prev) => [
      ...prev,
      {
        speaker: event.display_name,
        text: event.full_text,
        citations: event.verified_citations,
        agentId: event.agent_id
      },
    ]);

    if (ttsEnabledRef.current) {
      speakText(event.full_text, event.agent_id);
    }
  };

  const startCasePractice = () => {
    setStatus("running");
    setSidebarOpen(false); // Close sidebar on mobile when started
    
    if (userRole === "defense") {
        setTrialPhase("PROSECUTION OPENING STATEMENT");
        setActiveSpeaker("judge");
        setTimeout(() => {
          handleEvent({
            agent_id: "judge",
            display_name: "Hon’ble Judge",
            full_text: "The court is in session. State vs. Rahul Sharma. Public Prosecutor, please present your opening framing of the charges.",
            verified_citations: [],
          });
          
          setTimeout(() => {
             setActiveSpeaker("prosecutor");
             setTimeout(() => {
                 handleEvent({
                    agent_id: "prosecutor",
                    display_name: "Public Prosecutor",
                    full_text: "May it please the Hon’ble Court, on the night of Oct 12th, the accused intentionally relocated the complainant's property without consent. The evidence definitively establishes theft under Section 379.",
                    verified_citations: ["IPC 379"],
                 });
                 setTimeout(() => {
                     setActiveSpeaker(null);
                     setTrialPhase("DEFENSE REBUTTAL");
                 }, 500);
             }, 800);
          }, 1000);

        }, 100);
    } else {
        setTrialPhase("AWAITING YOUR OPENING");
    }
  };

  const submitUserInput = (e) => {
    e.preventDefault();
    if (inputText.length < 20) {
      alert("COURT PROTOCOL VIOLATION:\n\nPlease provide a structured legal argument (minimum 20 characters).\nInformal or short phrases are not acceptable on the court record.");
      return;
    }
    
    const userRoleName = roleNameMap[userRole];
    
    setMessages(prev => [...prev, {
      speaker: userRoleName,
      text: inputText,
      citations: [],
      agentId: userRole
    }]);
    
    const query = inputText;
    setInputText("");
    
    // Call backend API
    fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:5001'}/api/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ query: query })
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        // Map agent names to display names
        const agentDisplayNames = {
          "Prosecutor": "Public Prosecutor",
          "Accused": "Defense Counsel"
        };
        
        setTimeout(() => {
          setActiveSpeaker(data.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense");
          setTrialPhase(`${data.agent.toUpperCase()} RESPONSE`);
          
          setTimeout(() => {
            handleEvent({
              agent_id: data.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense",
              display_name: agentDisplayNames[data.agent] || data.agent,
              full_text: data.response,
              verified_citations: []
            });
            
            setTimeout(() => {
              setActiveSpeaker(null);
              setTrialPhase("AWAITING RESPONSE");
            }, 2000);
          }, 500);
        }, 500);
      } else {
        alert("Error: " + (data.error || "Unknown error"));
        setActiveSpeaker(null);
      }
    })
    .catch(error => {
      console.warn("Backend unavailable, using demo mode:", error.message);

      // Offline fallback: use mock responses
      const mockData = getMockResponse(query, userRole);
      const agentDisplayNames = {
        "Prosecutor": "Public Prosecutor",
        "Accused": "Defense Counsel"
      };

      setTimeout(() => {
        setActiveSpeaker(mockData.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense");
        setTrialPhase(`${mockData.agent.toUpperCase()} RESPONSE (DEMO)`);

        setTimeout(() => {
          handleEvent({
            agent_id: mockData.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense",
            display_name: agentDisplayNames[mockData.agent] || mockData.agent,
            full_text: mockData.response,
            verified_citations: mockData.citations || []
          });

          setTimeout(() => {
            setActiveSpeaker(null);
            setTrialPhase("AWAITING RESPONSE");
          }, 2000);
        }, 500);
      }, 800);
    });
  };

  return (
    <div className="h-screen flex bg-surface-court text-textPrimary font-body overflow-hidden">

      {/* MOBILE OVERLAY */}
      {sidebarOpen && (
        <div className="absolute inset-0 bg-black/40 z-40 md:hidden backdrop-blur-sm" onClick={() => setSidebarOpen(false)}></div>
      )}

      {/* LEFT PANEL */}
      <div className={`fixed md:relative top-0 left-0 h-full flex-shrink-0 flex flex-col gap-4 bg-white shadow-2xl md:shadow-xl transition-all duration-[350ms] ease-in-out z-50 ${
        sidebarCollapsed 
          ? 'w-0 p-0 lg:p-0 border-r-0 opacity-0 overflow-hidden pointer-events-none' 
          : 'w-[280px] md:w-[320px] lg:w-[360px] p-4 lg:p-6 border-r border-surface-border opacity-100 overflow-y-auto'
      } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
        
        <div className="flex justify-between items-center z-10 pb-2 border-b border-surface-border">
            <div>
              <h1 className="text-lg lg:text-[22px] font-heading font-extrabold text-wood-dark tracking-tight leading-snug cursor-pointer" onClick={onExit}>
                Kayda
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <button className="md:hidden relative p-1.5 border border-transparent text-wood-dark" onClick={() => setSidebarOpen(false)}>
                 <X size={20} />
              </button>
            </div>
        </div>

        {/* CASE FILE OR UPLOAD STATUS */}
        {uploadStatus ? (
          <div className="bg-[#FAF8F5] border border-[#D4AF37]/30 rounded-lg p-4 mt-3 shadow-inner animate-[pulse_1.5s_infinite]">
            <div className="flex items-center gap-2 text-[#D4AF37] font-black text-[9px] uppercase tracking-widest mb-3">
              <div className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] animate-ping" />
              {uploadStatus === "uploading" ? "Firebase Uploading" : "AI Brief Parsing"}
            </div>
            <div className="w-full bg-gray-200 h-1 rounded-full overflow-hidden mb-2">
              <div 
                className="bg-gradient-to-r from-[#D4AF37] to-[#8C5A3C] h-full transition-all duration-150" 
                style={{ width: `${uploadStatus === "uploading" ? uploadProgress : 100}%` }}
              />
            </div>
            <p className="font-mono text-[9px] text-[#8C5A3C] font-bold truncate">
              {uploadedFileName}
            </p>
            <p className="text-[10px] text-textMuted mt-1">
              {uploadStatus === "uploading" 
                ? `Progress: ${uploadProgress}% completed...` 
                : "Parsing case details and IPC sections..."}
            </p>
          </div>
        ) : (
          <div className="bg-white shadow-[0_2px_10px_rgba(0,0,0,0.05)] rounded-tr-xl rounded-b-xl border border-surface-border px-3.5 py-3 relative mt-3 h-auto z-10">
            <div className="absolute -top-[23px] left-[-1px] bg-white px-3 md:px-4 py-1.5 rounded-t-lg border-t border-l border-r border-surface-border text-[8px] md:text-[9px] font-black text-primaryBrown uppercase tracking-wider">
              Case File {caseData.fileId}
            </div>
            <h2 className="font-heading font-bold mb-2 text-[14px] md:text-[16px] leading-tight text-wood-dark">
              {caseData.title.split(" vs. ")[0]} <span className="text-[10px] md:text-xs italic font-normal">vs.</span> {caseData.title.split(" vs. ")[1] || ""}
            </h2>
            <ul className="text-[11px] md:text-xs space-y-2 text-textPrimary/90 font-mono">
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                  <span className="font-bold text-textMuted uppercase text-[8px] md:text-[9px] tracking-widest">FIR No</span> <span>{caseData.firNo}</span>
              </li>
              <li className="flex justify-between border-b border-surface-border/40 pb-1">
                  <span className="font-bold text-textMuted uppercase text-[8px] md:text-[9px] tracking-widest">Charge</span> 
                  <span className="bg-white/60 px-1 rounded font-bold text-semantic-criticalText">{caseData.charge}</span>
              </li>
            </ul>
          </div>
        )}

        {/* LEXIGRAPH VISUALIZER */}
        <div className="bg-white p-3 md:p-4 rounded-lg shadow-sm border border-surface-border flex flex-col gap-2 relative z-10 w-full flex-shrink-0 mt-2">
          <div className="flex items-center gap-2 text-primaryBrown border-b border-surface-border pb-2">
            <Network size={14} strokeWidth={2.5} />
            <span className="font-heading font-extrabold text-[10px] md:text-[11px] uppercase tracking-[0.1em]">LexiGraph Evidence</span>
          </div>
          <div className="relative h-[90px] md:h-[110px] w-full bg-white rounded border border-dashed border-surface-border flex items-center justify-center overflow-hidden">
             
             {inputText.length > 5 || activeSpeaker ? (
               <div className="absolute flex flex-col items-center justify-center w-full h-full p-2 animate-[fadeIn_0.5s_ease-out]">
                  <div className="flex items-center w-full justify-center">
                      <div className="p-1 px-2 md:px-3 border-2 border-gold rounded-full bg-white text-[9px] md:text-[10px] font-bold text-wood-dark shadow-md z-10">IPC 379</div>
                      
                      <svg className="w-8 md:w-12 h-2 -mx-1 md:-mx-2 z-0 opacity-60" viewBox="0 0 100 20">
                         <path d="M0,10 L100,10" fill="none" stroke="#C5A059" strokeWidth="4" strokeDasharray="6,6" className="animate-[pulse_1s_linear_infinite]" />
                      </svg>
                      
                      <div className="p-1 px-2 md:px-3 border-2 border-[#8B0000] rounded-full bg-white text-[9px] md:text-[10px] font-bold text-[#8B0000] shadow-md z-10">Mens Rea</div>
                  </div>
                  
                  {inputText.length > 15 && (
                      <div className="flex items-center w-full justify-center animate-[fadeIn_1s_ease-out] relative">
                          <svg className="absolute w-2 h-6 md:h-8 -top-6 md:-top-8 left-[40%] z-0 opacity-40 shrink-0" viewBox="0 0 10 40">
                             <path d="M5,0 L5,40" fill="none" stroke="#1E88E5" strokeWidth="4" strokeDasharray="4,4" />
                          </svg>
                          <div className="mt-1 md:mt-2 p-1 px-2 md:px-3 ml-2 md:ml-4 border-2 border-[#1E88E5] rounded-full bg-white text-[8px] md:text-[9px] font-bold text-[#1E88E5] shadow-sm z-10">Intent Absent</div>
                      </div>
                  )}
               </div>
            ) : (
               <p className="text-[9px] md:text-[10px] text-textMuted font-mono bg-white/50 px-2 py-1 rounded">Awaiting reasoning...</p>
            )}

          </div>
        </div>

        {/* LEGAL COACH INTERVENTION */}
        {status === "running" && (
            <div className="bg-gradient-to-br from-[#E3F2FD] to-[#f4faff] border border-[#90CAF9] p-4 font-body rounded-lg shadow-sm mt-3 mb-auto animate-[fadeIn_0.5s_ease-out]">
                <div className="flex items-center gap-2 text-[#0D47A1] font-black text-[9px] md:text-[10.5px] uppercase tracking-widest mb-3">
                    <Lightbulb size={14} className="fill-[#90CAF9]" /> Legal Guidance
                </div>
                <div className="text-[11px] md:text-[12px] text-[#0D47A1] leading-relaxed space-y-3">
                    <p className="font-bold border-b border-blue-200 pb-1 text-[10px] md:text-xs">You should:</p>
                    <div className="space-y-2">
                        <p className="flex items-start gap-1 md:gap-2 font-medium">
                           <GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500 hidden md:block" /> 
                           <span>Challenge intent interpretation under <span className="font-bold underline decoration-2 decoration-[#1E88E5] text-blue-800 rounded px-0.5">Section 378</span>.</span>
                        </p>
                        <p className="flex items-start gap-1 md:gap-2 font-medium"><GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500 hidden md:block" /> Emphasize lack of evidence.</p>
                    </div>
                </div>
            </div>
        )}

        <div className="mt-auto pt-6 pb-4 flex flex-col gap-2">
          {status === "running" && (
            <div className="flex flex-col gap-2 mb-2 p-3 bg-[#FAF8F5] border border-surface-border rounded-lg animate-[fadeIn_0.3s_ease-out]">
              <span className="font-mono text-[8px] uppercase tracking-widest text-[#8C5A3C] font-bold mb-1 block">Courtroom Actions</span>
              <button 
                type="button" 
                onClick={() => alert("Consulting Legal Database...\nNo contradictions found at this stage.")}
                className="w-full flex items-center justify-center gap-1.5 text-[9px] uppercase font-bold tracking-widest text-[#0D47A1] bg-[#E3F2FD] px-3 py-2 rounded border border-[#90CAF9] hover:bg-[#90CAF9]/20 transition-all"
              >
                  <BookOpen size={12} />
                  <span>Consult Legal Database</span>
              </button>
              <button 
                type="button" 
                onClick={() => alert("Objection Raised!\nThe Court has noted your objection. The Judge will rule shortly.")}
                className="w-full flex items-center justify-center gap-1.5 text-[9px] uppercase font-bold tracking-widest text-white bg-[#D32F2F] px-3 py-2 rounded border border-[#B71C1C] hover:bg-[#B71C1C]/90 transition-all"
              >
                  <AlertTriangle size={12} fill="currentColor" className="text-white" />
                  Raise Objection
              </button>
            </div>
          )}

          <button 
            onClick={onExit}
            className="border border-surface-border text-wood-dark font-body text-xs uppercase tracking-widest px-4 py-3 hover:bg-[#FAF8F5] transition-all font-bold text-center w-full"
          >
            Exit to Chambers
          </button>
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="flex-1 flex flex-col relative w-full md:w-auto overflow-hidden bg-white transition-all duration-[350ms] ease-in-out">
        
        {/* Floating Sidebar Toggle Button (Desktop & Tablet) */}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="hidden md:flex absolute left-4 top-1/2 -translate-y-1/2 z-40 p-2.5 bg-white border border-surface-border shadow-md rounded-lg text-primaryBrown hover:bg-gold/10 hover:text-gold hover:scale-105 transition-all duration-[350ms] ease-in-out cursor-pointer group"
          title={sidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {sidebarCollapsed ? <ChevronRight size={16} className="group-hover:translate-x-0.5 transition-transform" /> : <ChevronLeft size={16} className="group-hover:-translate-x-0.5 transition-transform" />}
        </button>
        
        {/* MOBILE HEADER FOR RIGHT PANEL */}
        <div className="md:hidden flex justify-between items-center bg-white border-b border-surface-border p-3 z-30 shadow-[0_2px_10px_rgba(0,0,0,0.05)] relative shrink-0">
           <button onClick={() => setSidebarOpen(true)} className="p-1.5 bg-[#FAF8F5] rounded text-primaryBrown border border-surface-border">
              <Menu size={18} />
           </button>
           <h1 className="text-sm font-heading font-extrabold text-wood-dark" onClick={onExit}>Kayda</h1>
           <div className="flex items-center gap-2">
             <button
               onClick={() => setTtsEnabled(!ttsEnabled)}
               className="p-1.5 text-primaryBrown rounded"
               title={ttsEnabled ? "Mute Readout" : "Unmute Readout"}
             >
               {ttsEnabled ? <Volume2 size={18} className="text-gold" /> : <VolumeX size={18} />}
             </button>
             {status === "idle" && (
                <button onClick={() => setSidebarOpen(true)} className="text-[9px] font-bold uppercase tracking-widest text-primaryBrown bg-gold/20 px-2.5 py-1.5 rounded">Setup</button>
             )}
             {status !== "idle" && (
                <span className="text-[8px] font-black uppercase tracking-widest text-wood-dark border border-surface-border px-2 py-1 rounded bg-[#FAF8F5]">{trialPhase.substring(0, 10)}...</span>
             )}
           </div>
        </div>

        <CourtroomStage
          activeSpeaker={activeSpeaker}
          lastMessage={messages[messages.length - 1]}
          userRole={userRole}
        />
        
        <ChatPanel messages={messages} userRole={userRole} speakText={speakText} />

        {/* STRUCTURED LEGAL NOTEPAD / USER ACTION ZONE */}
        {status === "running" && (
            <div className="bg-transparent px-4 py-4 z-30 flex flex-col items-center justify-center w-full">
                {/* Active speaker status */}
                <div className="mb-2 text-center">
                    <span className={`text-[10px] font-bold uppercase tracking-widest ${activeSpeaker ? 'text-primaryBrown/50' : 'text-gold drop-shadow-md'} flex items-center justify-center gap-1.5 transition-colors`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${activeSpeaker ? 'bg-primaryBrown/30' : 'bg-gold animate-pulse'}`}></span>
                        {activeSpeaker ? 'Awaiting opposing counsel...' : 'You have the floor — present your argument'}
                    </span>
                </div>

                <form onSubmit={submitUserInput} className="w-full max-w-3xl">
                    <div className={`flex items-center gap-3 bg-white border border-[#2C1810]/15 rounded-full py-1.5 pl-4 pr-1.5 shadow-[0_4px_25px_rgba(0,0,0,0.06)] transition-all ${activeSpeaker ? 'opacity-70 bg-gray-50' : 'focus-within:border-gold focus-within:ring-2 focus-within:ring-gold/10'}`}>
                        
                        {/* Plus Action Button */}
                        <button 
                            type="button" 
                            className="text-[#2C1810]/50 hover:text-[#2C1810] transition-colors p-1 cursor-pointer"
                            title="Additional Options"
                            onClick={() => alert("Chamber Actions:\n\nUse the left sidebar to consult the legal database or raise formal objections.")}
                        >
                            <span className="text-xl font-light leading-none">+</span>
                        </button>

                        {/* Input Area */}
                        <input
                            type="text"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            disabled={activeSpeaker !== null}
                            placeholder={
                              activeSpeaker 
                                ? "Opposing counsel is presenting..." 
                                : isListening 
                                  ? "Listening... speak clearly into your mic..." 
                                  : "Ask anything / state your case..."
                            }
                            className="w-full bg-transparent border-none outline-none py-2 text-[14px] text-[#2C1810] placeholder-[#2C1810]/40"
                        />

                        {/* Speech-to-Text Microphone Button */}
                        <button
                          type="button"
                          onClick={toggleListening}
                          className={`p-1.5 rounded-full transition-all flex items-center justify-center shrink-0 cursor-pointer ${
                            isListening 
                              ? 'bg-red-500 text-white animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.5)]' 
                              : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
                          }`}
                          title={isListening ? "Stop listening" : "Speech-to-Text (Dictate)"}
                        >
                          <Mic size={16} />
                        </button>

                        {/* Text-to-Speech Voice Readout Toggle */}
                        <button
                          type="button"
                          onClick={() => setTtsEnabled(!ttsEnabled)}
                          className={`p-1.5 rounded-full transition-all flex items-center justify-center shrink-0 cursor-pointer ${
                            ttsEnabled 
                              ? 'text-gold hover:bg-gold/10' 
                              : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
                          }`}
                          title={ttsEnabled ? "Mute Readout" : "Unmute Readout"}
                        >
                          {ttsEnabled ? <Volume2 size={16} className="text-gold" /> : <VolumeX size={16} />}
                        </button>

                        {/* Send Button */}
                        <button
                            type="submit"
                            disabled={inputText.length < 20 || activeSpeaker !== null}
                            className={`p-2 rounded-full transition-all flex items-center justify-center shrink-0 border ${
                              inputText.length >= 20 && !activeSpeaker 
                                ? 'bg-[#2C1810] text-[#C5A059] border-[#C5A059] hover:bg-[#3D2318] hover:scale-105 shadow-sm' 
                                : 'bg-gray-100 text-gray-400 border-transparent cursor-not-allowed'
                            }`}
                            title="Submit to Record"
                        >
                            <Send size={14} />
                        </button>
                    </div>
                </form>
            </div>
        )}
      </div>
    </div>
  );
}