import { 
  CheckCircle2, 
  Volume2, 
  User, 
  Bot, 
  Scale, 
  Shield, 
  Gavel, 
  FileText, 
  Network, 
  AlertTriangle, 
  Award, 
  ChevronDown, 
  ChevronUp,
  Bookmark,
  Check,
  X
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

// Lightweight legal markdown renderer for clean paragraph & bullet formatting
function FormattedLegalText({ text, isDark = false }) {
  if (!text) return null;

  // Split into lines
  const lines = text.split("\n");
  const elements = [];

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i].trim();
    if (!rawLine) {
      elements.push(<div key={i} className="h-2" />);
      continue;
    }

    // Heading 3 or 4
    if (rawLine.startsWith("### ") || rawLine.startsWith("#### ")) {
      const headingText = rawLine.replace(/^#{3,4}\s+/, "");
      elements.push(
        <h4 key={i} className={`font-heading font-bold text-[13px] md:text-[14px] uppercase tracking-wider mt-3 mb-1 border-b pb-1 ${
          isDark 
            ? "text-[#D4AF37] border-white/15" 
            : "text-[#2C1810] border-[#2C1810]/10"
        }`}>
          {headingText}
        </h4>
      );
      continue;
    }

    // Numbered list item: "1. ..."
    const numMatch = rawLine.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      elements.push(
        <div key={i} className="flex items-start gap-2.5 my-1.5 pl-1">
          <span className={`font-mono text-xs font-bold shrink-0 px-1.5 py-0.5 rounded ${
            isDark 
              ? "text-[#D4AF37] bg-white/10 border border-white/15" 
              : "text-[#8C5A3C] bg-[#8C5A3C]/10"
          }`}>
            {numMatch[1]}
          </span>
          <p className={`text-[13px] md:text-[14.5px] leading-relaxed ${
            isDark ? "text-white/95" : "text-[#2C1810]"
          }`}>
            <RenderInlineBold text={numMatch[2]} isDark={isDark} />
          </p>
        </div>
      );
      continue;
    }

    // Bullet list item: "- ..." or "* ..."
    if (rawLine.startsWith("- ") || rawLine.startsWith("* ")) {
      const bulletText = rawLine.substring(2);
      elements.push(
        <div key={i} className="flex items-start gap-2 my-1 pl-1">
          <span className={`w-1.5 h-1.5 rounded-full mt-2 shrink-0 ${isDark ? "bg-[#D4AF37]" : "bg-[#D4AF37]"}`} />
          <p className={`text-[13px] md:text-[14.5px] leading-relaxed ${
            isDark ? "text-white/95" : "text-[#2C1810]"
          }`}>
            <RenderInlineBold text={bulletText} isDark={isDark} />
          </p>
        </div>
      );
      continue;
    }

    // Normal paragraph
    elements.push(
      <p key={i} className={`text-[13px] md:text-[14.5px] leading-relaxed my-1 ${
        isDark ? "text-white/95" : "text-[#2C1810]"
      }`}>
        <RenderInlineBold text={rawLine} isDark={isDark} />
      </p>
    );
  }

  return <div className="space-y-1 font-body">{elements}</div>;
}

// Parses **bold text**
function RenderInlineBold({ text, isDark = false }) {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={index} className={`font-bold ${isDark ? "text-[#D4AF37]" : "text-[#1C120C]"}`}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        return part;
      })}
    </>
  );
}

// Component for Evidence Analyzer Output
function EvidenceAnalyzerCard({ msg }) {
  const [showAllFacts, setShowAllFacts] = useState(false);
  const facts = msg.facts || [];
  const inventory = msg.inventory || [];

  const displayedFacts = showAllFacts ? facts : facts.slice(0, 5);

  return (
    <div className="w-full bg-white border border-indigo-200/80 rounded-2xl shadow-sm overflow-hidden my-3 animate-fadeIn">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-900 to-slate-900 text-white px-5 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300">
            <FileText size={18} />
          </div>
          <div>
            <h3 className="font-heading font-bold text-sm tracking-wide text-white">
              Evidence Analyzer Briefing
            </h3>
            <p className="text-[10px] font-mono text-indigo-300 tracking-wider uppercase">
              Fact Classification & Evidence Inventory
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono bg-indigo-800/60 text-indigo-200 px-2 py-0.5 rounded-full border border-indigo-700/50">
          {facts.length} Facts · {inventory.length} Records
        </span>
      </div>

      <div className="p-5 space-y-4">
        <p className="text-xs md:text-sm text-[#4A3B32] font-medium leading-relaxed">
          {msg.content || msg.text}
        </p>

        {/* Evidence Inventory Badges */}
        {inventory.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#7A6A60] block">
              Evidence Inventory (Record Verification):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {inventory.slice(0, 14).map((item, idx) => {
                const isPresent = item.status === "present";
                return (
                  <span
                    key={idx}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-mono font-semibold border ${
                      isPresent
                        ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                        : "bg-slate-100 text-slate-600 border-slate-200"
                    }`}
                    title={item.details || ""}
                  >
                    {isPresent ? <Check size={11} className="text-emerald-600" /> : <X size={11} className="text-slate-400" />}
                    <span>{item.item || item.name}</span>
                    <span className="opacity-70 text-[9px] font-normal">({item.status})</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Classified Facts Preview */}
        {facts.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#7A6A60] block">
              Extracted Facts by Legal Category:
            </span>
            <div className="space-y-1.5">
              {displayedFacts.map((fact, idx) => {
                const ftype = fact.type || "allegation";
                let tagColor = "bg-amber-50 text-amber-800 border-amber-200";
                if (ftype === "procedural_event") tagColor = "bg-sky-50 text-sky-800 border-sky-200";
                else if (ftype === "court_finding") tagColor = "bg-purple-50 text-purple-800 border-purple-200";

                return (
                  <div key={idx} className="p-2.5 rounded-lg bg-[#FAF9F7] border border-[#2C1810]/10 flex items-start gap-2.5 text-xs">
                    <span className="font-mono text-[9px] font-bold text-[#8C5A3C] shrink-0 bg-white border border-[#2C1810]/15 px-1.5 py-0.5 rounded shadow-2xs">
                      {fact.id || `fact_${idx + 1}`}
                    </span>
                    <span className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border shrink-0 ${tagColor}`}>
                      {ftype.replace("_", " ")}
                    </span>
                    <p className="text-[#2C1810] leading-snug flex-1">
                      {fact.text || fact.value}
                    </p>
                  </div>
                );
              })}
            </div>

            {facts.length > 5 && (
              <button
                onClick={() => setShowAllFacts(!showAllFacts)}
                className="text-[11px] font-bold font-mono text-indigo-700 hover:text-indigo-900 flex items-center gap-1 pt-1 cursor-pointer"
              >
                {showAllFacts ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {showAllFacts ? "Show Less Facts" : `View All ${facts.length} Extracted Facts`}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Component for LexiGraph Output
function LexigraphCard({ msg }) {
  const citations = msg.citations || [];
  const holdings = msg.holdings || [];
  const precedents = msg.precedents || [];

  return (
    <div className="w-full bg-white border border-[#D4AF37]/50 rounded-2xl shadow-sm overflow-hidden my-3 animate-fadeIn">
      {/* Header */}
      <div className="bg-gradient-to-r from-[#2C1810] to-[#452718] text-white px-5 py-3.5 flex items-center justify-between border-b border-[#D4AF37]/30">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-[#D4AF37]/20 text-[#D4AF37]">
            <Network size={18} />
          </div>
          <div>
            <h3 className="font-heading font-bold text-sm tracking-wide text-white">
              LexiGraph Legal Retrieval
            </h3>
            <p className="text-[10px] font-mono text-[#D4AF37]/80 tracking-wider uppercase">
              Statutory Framework & Precedent Holdings
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono bg-[#D4AF37]/20 text-[#D4AF37] px-2 py-0.5 rounded-full border border-[#D4AF37]/40 font-bold">
          Verified Graph
        </span>
      </div>

      <div className="p-5 space-y-4">
        <p className="text-xs md:text-sm text-[#4A3B32] font-medium leading-relaxed">
          {msg.content || msg.text}
        </p>

        {/* Governing Statutory Sections */}
        {citations.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#7A6A60] block">
              Governing Statutory Provisions:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {citations.map((c, idx) => (
                <span
                  key={idx}
                  className="px-2.5 py-1 text-[11px] font-mono font-bold rounded-lg bg-[#FAF8F5] border border-[#D4AF37]/60 text-[#2C1810] shadow-2xs"
                >
                  § {c}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Precedents and Holdings */}
        {(holdings.length > 0 || precedents.length > 0) && (
          <div className="space-y-1.5 pt-2 border-t border-amber-100">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#7A6A60] block">
              Retrieved Precedent Holdings:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {holdings.map((h, idx) => {
                const label = typeof h === "string" ? h : (h.id || h.case || "Holding");
                return (
                  <span
                    key={idx}
                    className="px-2.5 py-1 text-[10px] font-mono font-medium rounded-md bg-amber-50 border border-amber-300 text-amber-900 shadow-2xs"
                  >
                    ⚖ {label}
                  </span>
                );
              })}
              {precedents.map((p, idx) => (
                <span
                  key={idx}
                  className="px-2.5 py-1 text-[10px] font-mono font-medium rounded-md bg-blue-50 border border-blue-200 text-blue-900 shadow-2xs"
                >
                  📜 {p}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Component for Judge Scores Scorecard
function JudgeScoresCard({ msg }) {
  const scores = msg.scores || {};
  const pros = scores.prosecution || {};
  const def = scores.defense || {};
  const overall = scores.overall || 0;

  return (
    <div className="w-full bg-[#FAF9F7] border border-amber-300/80 rounded-2xl shadow-sm p-4 my-3 animate-fadeIn">
      <div className="flex items-center justify-between border-b border-amber-200 pb-2.5 mb-3">
        <div className="flex items-center gap-2 text-amber-900">
          <Award size={16} className="text-[#D4AF37]" />
          <h4 className="font-heading font-bold text-xs uppercase tracking-wider">
            Judicial Argument Evaluation
          </h4>
        </div>
        <span className="font-mono text-xs font-bold px-2 py-0.5 bg-amber-100 border border-amber-300 rounded text-amber-900">
          Overall Bench Score: {overall}/10
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Prosecution */}
        <div className="bg-white p-3 rounded-xl border border-blue-100 shadow-2xs space-y-1 text-xs">
          <span className="font-heading font-bold text-blue-900 block text-[11px] uppercase tracking-wider">
            Public Prosecutor (Avg: {pros.average || 0})
          </span>
          <div className="space-y-1 font-mono text-[10px] text-slate-700">
            <div className="flex justify-between"><span>Legal Validity:</span> <span className="font-bold">{pros.legal_validity || 0}/10</span></div>
            <div className="flex justify-between"><span>Evidence Linkage:</span> <span className="font-bold">{pros.evidence_linkage || 0}/10</span></div>
            <div className="flex justify-between"><span>Logic Coherence:</span> <span className="font-bold">{pros.logic_coherence || 0}/10</span></div>
          </div>
        </div>

        {/* Defense */}
        <div className="bg-white p-3 rounded-xl border border-rose-100 shadow-2xs space-y-1 text-xs">
          <span className="font-heading font-bold text-rose-900 block text-[11px] uppercase tracking-wider">
            Defense Counsel (Avg: {def.average || 0})
          </span>
          <div className="space-y-1 font-mono text-[10px] text-slate-700">
            <div className="flex justify-between"><span>Legal Validity:</span> <span className="font-bold">{def.legal_validity || 0}/10</span></div>
            <div className="flex justify-between"><span>Evidence Linkage:</span> <span className="font-bold">{def.evidence_linkage || 0}/10</span></div>
            <div className="flex justify-between"><span>Logic Coherence:</span> <span className="font-bold">{def.logic_coherence || 0}/10</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Component for the Final Verdict Decree
function VerdictCard({ msg }) {
  const result = (msg.result || msg.decision || "DENIED").toUpperCase();
  const confidence = (msg.confidence || msg.confidence_label || "HIGH").toUpperCase();
  const validVotes = msg.valid_votes ?? 3;
  const totalVotes = msg.total_votes ?? 5;
  const agreeCount = msg.agree_count ?? 3;

  const statutes = msg.statutes || [];
  const precedents = msg.precedents || [];
  const holdingsRelied = msg.holdings_relied || [];
  const explanation = msg.explanation || msg.reasoning || msg.text || "";

  // Color schemes
  let bannerBg = "bg-gradient-to-br from-red-950 via-[#450a0a] to-[#260505] border-red-500/60";
  let badgeColor = "bg-red-900/60 text-red-200 border-red-400/40";
  if (result.includes("GRANT")) {
    bannerBg = "bg-gradient-to-br from-emerald-950 via-[#064e3b] to-[#022c22] border-emerald-500/60";
    badgeColor = "bg-emerald-900/60 text-emerald-200 border-emerald-400/40";
  } else if (result.includes("INTERIM")) {
    bannerBg = "bg-gradient-to-br from-blue-950 via-[#1e3a8a] to-[#0f172a] border-blue-500/60";
    badgeColor = "bg-blue-900/60 text-blue-200 border-blue-400/40";
  }

  return (
    <div className={`w-full text-white border-2 rounded-2xl shadow-xl overflow-hidden my-6 animate-fadeIn ${bannerBg}`}>
      {/* Decree Header */}
      <div className="p-6 md:p-8 space-y-4 border-b border-white/10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-white/10 backdrop-blur-md flex items-center justify-center border border-white/20 shadow-inner">
              <Gavel size={26} className="text-[#D4AF37]" />
            </div>
            <div>
              <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-[#D4AF37] font-bold block">
                Official Judicial Pronouncement
              </span>
              <h2 className="font-heading text-2xl md:text-3xl font-extrabold tracking-tight text-white">
                VERDICT: {result}
              </h2>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <span className={`px-3 py-1 text-xs font-mono font-bold uppercase rounded-full border ${badgeColor}`}>
              Confidence: {confidence}
            </span>
            <span className="px-3 py-1 text-xs font-mono font-semibold rounded-full bg-white/10 border border-white/20 text-white/90">
              {validVotes}/{totalVotes} Valid Votes ({agreeCount}/{validVotes} Agree)
            </span>
          </div>
        </div>

        {/* 3 Categories of Law */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3">
          {/* Statutes */}
          <div className="bg-black/30 backdrop-blur-sm p-3 rounded-xl border border-white/10 space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-amber-300 font-bold block">
              Statutes Applied:
            </span>
            <div className="flex flex-wrap gap-1">
              {statutes.length > 0 ? (
                statutes.map((s, idx) => (
                  <span key={idx} className="px-2 py-0.5 text-[10px] font-mono font-bold bg-white/10 rounded border border-white/15 text-white">
                    § {s}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-white/50 italic">None cited</span>
              )}
            </div>
          </div>

          {/* Precedents */}
          <div className="bg-black/30 backdrop-blur-sm p-3 rounded-xl border border-white/10 space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-sky-300 font-bold block">
              Precedents Cited:
            </span>
            <div className="flex flex-wrap gap-1">
              {precedents.length > 0 ? (
                precedents.map((p, idx) => (
                  <span key={idx} className="px-2 py-0.5 text-[10px] font-mono bg-white/10 rounded border border-white/15 text-white">
                    📜 {p}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-white/50 italic">None cited</span>
              )}
            </div>
          </div>

          {/* Holdings Relied */}
          <div className="bg-black/30 backdrop-blur-sm p-3 rounded-xl border border-white/10 space-y-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-300 font-bold block">
              Holdings Relied On:
            </span>
            <div className="flex flex-wrap gap-1">
              {holdingsRelied.length > 0 ? (
                holdingsRelied.map((h, idx) => (
                  <span key={idx} className="px-2 py-0.5 text-[10px] font-mono bg-white/10 rounded border border-white/15 text-white">
                    ⚖ {h}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-white/50 italic">Standard Ratio</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Judicial Rationale & Findings */}
      <div className="p-6 md:p-8 bg-black/40 backdrop-blur-md space-y-3">
        <h4 className="font-heading font-bold text-xs uppercase tracking-widest text-[#D4AF37]">
          Ratio Decidendi & Judicial Rationale:
        </h4>
        <div className="text-[13px] md:text-[14.5px] leading-relaxed text-white/90 font-serif space-y-2 whitespace-pre-line">
          {explanation}
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({ messages, userRole, speakText }) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto bg-[#FAF9F7] px-4 py-6 md:px-8 space-y-6 w-full scroll-smooth">
      <div className="w-full max-w-4xl mx-auto space-y-6 transition-all duration-300">
        
        {/* Empty State */}
        {messages.length === 0 && (
          <div className="h-[300px] flex flex-col items-center justify-center text-[#2C1810]/40 mt-10">
            <div className="w-16 h-16 rounded-full bg-white shadow-sm flex items-center justify-center mb-5 border border-[#D4AF37]/30">
              <Scale size={28} className="text-[#D4AF37]" />
            </div>
            <p className="font-heading text-xl md:text-2xl font-bold tracking-tight text-[#2C1810]/70">
              Court is now in session
            </p>
            <p className="font-body text-sm mt-2 opacity-80 text-center max-w-md">
              The AI Moot Courtroom is standing ready. Select a case from the bank or step through the simulation turns below.
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          // Special Message Types
          if (msg.type === "verdict" || msg.agentId === "verdict" || msg.agent === "verdict") {
            return <VerdictCard key={i} msg={msg} />;
          }

          if (msg.agentId === "evidence_analyzer" || msg.agent === "evidence_analyzer") {
            return <EvidenceAnalyzerCard key={i} msg={msg} />;
          }

          if (msg.agentId === "lexigraph" || msg.agent === "lexigraph") {
            return <LexigraphCard key={i} msg={msg} />;
          }

          if (msg.type === "judge_scores") {
            return <JudgeScoresCard key={i} msg={msg} />;
          }

          // Counsel Turns
          const agentId = msg.agentId || msg.agent || "";
          const isUser = Boolean(
            msg.isUser === true ||
            agentId === "user" ||
            (userRole && agentId === userRole && (msg.speaker?.includes("[YOU]") || msg.speaker?.includes("(You)") || msg.isUser))
          );
          const isProsecutor = agentId === "prosecutor";
          const isJudge = agentId === "judge";
          const isDefense = agentId === "defense";
          const isAccused = agentId === "accused";

          // Icon selection
          let Icon = Bot;
          if (isProsecutor) Icon = Scale;
          else if (isJudge) Icon = Gavel;
          else if (isDefense) Icon = Shield;
          else if (isAccused) Icon = User;

          // Alignment determination:
          // 1. Judge: always center
          // 2. When user is prosecutor: prosecutor / mine is on RIGHT, defense on LEFT
          // 3. When user is defense: defense / mine is on RIGHT, prosecutor on LEFT
          // 4. When observer / other: prosecutor on RIGHT, defense on LEFT
          let isCenter = isJudge;
          let isRightSide = false;

          if (!isJudge) {
            if (userRole === "defense") {
              isRightSide = isDefense || isUser;
            } else if (userRole === "prosecutor") {
              isRightSide = isProsecutor || isUser;
            } else {
              isRightSide = isProsecutor;
            }
          }

          let alignContainer = "justify-start";
          let alignBubbleContainer = "items-start text-left";
          if (isCenter) {
            alignContainer = "justify-center";
            alignBubbleContainer = "items-center text-center";
          } else if (isRightSide) {
            alignContainer = "justify-end";
            alignBubbleContainer = "items-end text-left";
          }

          // Dynamic Bubble Styling
          let bubbleStyle = "bg-white text-[#2C1810] border border-[#2C1810]/15 rounded-tl-sm";
          let isDarkBubble = false;

          if (isUser) {
            // User message: sleek deep chocolate box with gold border and bright, high-contrast readable text
            bubbleStyle = "bg-[#24140D] text-white border border-[#D4AF37]/50 shadow-md " + 
              (isRightSide ? "rounded-2xl rounded-tr-sm" : "rounded-2xl rounded-tl-sm");
            isDarkBubble = true;
          } else if (isJudge) {
            bubbleStyle = "bg-amber-50 text-[#2C1810] border border-amber-300/80 rounded-2xl shadow-sm text-center";
          } else if (isProsecutor) {
            bubbleStyle = "bg-blue-50/90 text-[#2C1810] border border-blue-200/90 shadow-2xs " + 
              (isRightSide ? "rounded-2xl rounded-tr-sm" : "rounded-2xl rounded-tl-sm");
          } else if (isDefense) {
            bubbleStyle = "bg-rose-50/90 text-[#2C1810] border border-rose-200/90 shadow-2xs " + 
              (isRightSide ? "rounded-2xl rounded-tr-sm" : "rounded-2xl rounded-tl-sm");
          } else if (isAccused) {
            bubbleStyle = "bg-slate-50 text-[#2C1810] border border-slate-200 shadow-2xs " + 
              (isRightSide ? "rounded-2xl rounded-tr-sm" : "rounded-2xl rounded-tl-sm");
          }

          const rawText = msg.text || msg.content || "";
          const citations = msg.citations || msg.verified_citations || [];
          const evidenceRefs = msg.evidence_refs || [];
          const unverified = msg.unverified || [];

          return (
            <div key={i} className={`flex w-full gap-3 md:gap-4 ${alignContainer} animate-fadeIn`}>
              
              {/* Left Avatar (Opponent / Third-party) */}
              {!isCenter && !isRightSide && (
                <div className="w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-full bg-white border border-[#D4AF37]/30 flex items-center justify-center shadow-sm mt-1">
                  <Icon size={18} className={isDefense ? "text-red-700" : isProsecutor ? "text-blue-700" : "text-slate-700"} />
                </div>
              )}

              {/* Center Avatar (Judge) */}
              {isCenter && (
                <div className="w-9 h-9 md:w-11 md:h-11 shrink-0 rounded-full bg-amber-100 border-2 border-[#D4AF37] flex items-center justify-center shadow-md mt-1">
                  <Gavel size={20} className="text-amber-700" />
                </div>
              )}

              {/* Message Content Container */}
              <div className={`flex flex-col gap-1.5 max-w-[88%] md:max-w-[75%] ${alignBubbleContainer}`}>
                
                {/* Header (Speaker Name & Citations badge) */}
                <div className={`flex items-center gap-2 px-1.5 ${isRightSide ? "flex-row-reverse" : isCenter ? "justify-center" : "flex-row"}`}>
                  <span className="text-xs font-semibold text-[#5D4037] capitalize flex items-center gap-1.5">
                    {msg.speaker || agentId} {isUser && !msg.speaker?.includes("YOU") ? "(You)" : ""}
                    {msg.round ? (
                      <span className="text-[9px] font-mono text-[#8C5A3C] bg-[#8C5A3C]/10 px-1.5 py-0.2 rounded font-bold">
                        R{msg.round}
                      </span>
                    ) : null}
                  </span>

                  {citations.length > 0 && (
                    <span className="flex items-center gap-1 text-[9px] uppercase font-bold tracking-wider bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full border border-emerald-200">
                      <CheckCircle2 size={10} strokeWidth={3} /> Verified
                    </span>
                  )}

                  {unverified.length > 0 && (
                    <span className="flex items-center gap-1 text-[9px] uppercase font-bold tracking-wider bg-amber-50 text-amber-800 px-2 py-0.5 rounded-full border border-amber-300" title={`Unverified citations: ${unverified.join(', ')}`}>
                      <AlertTriangle size={10} /> Notice
                    </span>
                  )}
                </div>

                {/* Chat Bubble with formatted legal text */}
                <div className={`relative px-5 py-3.5 md:py-4 md:px-6 shadow-2xs leading-relaxed ${bubbleStyle}`}>
                  <FormattedLegalText text={rawText} isDark={isDarkBubble} />
                </div>

                {/* Bottom Actions Bar (TTS, Citations, Evidence Tags) */}
                <div className={`flex flex-wrap items-center gap-1.5 mt-1 px-1.5 ${isRightSide ? "flex-row-reverse" : isCenter ? "justify-center" : "flex-row"}`}>
                  
                  {speakText && (
                    <button
                      onClick={() => speakText(rawText, agentId)}
                      className="p-1.5 rounded-full text-[#5D4037]/60 hover:text-[#2C1810] hover:bg-black/5 transition-colors cursor-pointer"
                      title="Read aloud"
                    >
                      <Volume2 size={14} />
                    </button>
                  )}

                  {/* Citations Badges */}
                  {citations.map((c, idx) => (
                    <span
                      key={`cite-${idx}`}
                      className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-md bg-white border border-[#2C1810]/15 text-[#5D4037] hover:border-[#D4AF37] hover:text-[#8C5A3C] transition-colors cursor-pointer select-none shadow-2xs"
                      title="Cited Section / Precedent"
                    >
                      § {c}
                    </span>
                  ))}

                  {/* Evidence References Badges */}
                  {evidenceRefs.map((f, idx) => (
                    <span
                      key={`ref-${idx}`}
                      className="px-2 py-0.5 text-[9px] font-mono font-medium rounded-md bg-slate-100 border border-slate-200 text-slate-700 select-none"
                      title="Cited Case Fact"
                    >
                      📌 {f}
                    </span>
                  ))}
                </div>

              </div>

              {/* Right Avatar (User / Own side) */}
              {!isCenter && isRightSide && (
                <div className={`w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-full flex items-center justify-center mt-1 shadow-sm ${
                  isUser 
                    ? "bg-gradient-to-br from-[#D4AF37] to-[#8C5A3C]" 
                    : isProsecutor
                      ? "bg-white border border-blue-300"
                      : "bg-white border border-rose-300"
                }`}>
                  {isUser ? (
                    <User size={18} className="text-white" />
                  ) : (
                    <Icon size={18} className={isProsecutor ? "text-blue-700" : "text-red-700"} />
                  )}
                </div>
              )}

            </div>
          );
        })}
      </div>
      
      {/* Invisible element to scroll to */}
      <div ref={chatEndRef} className="h-4" />
    </div>
  );
}