import { useState } from "react";
import CourtroomStage from "./components/CourtroomStage";
import ChatPanel from "./components/ChatPanel";
import { Network, Briefcase, Lightbulb, Play, Send, Scale, Hand, BookOpen, Anchor, AlertTriangle, GitCommit } from "lucide-react";

export default function App() {
  const [activeScreen, setActiveScreen] = useState("setup");
  const [userRole, setUserRole] = useState("defense"); // "prosecutor", "defense", "judge"

  if (activeScreen === "setup") {
    // Setup Entry Screen Same As Before
    return (
      <div className="min-h-screen bg-[#EFEBE9] flex items-center justify-center font-body selection:bg-gold/30 p-4">
        <div className="bg-white p-8 md:p-12 rounded-2xl shadow-2xl max-w-4xl w-full border border-[#D7CCC8] relative overflow-hidden">
          <div className="absolute inset-0 opacity-[0.015] bg-[radial-gradient(#5D4037_1px,transparent_1px)] [background-size:16px_16px]"></div>
          <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-primaryBrown via-gold to-primaryBrown"></div>
          
          <div className="text-center relative z-10 mb-10 mt-2">
            <h1 className="text-4xl md:text-5xl font-heading font-extrabold text-primaryBrown tracking-tight mb-3">
              MootCourt.<span className="text-gold">ai</span>
            </h1>
            <p className="text-textMuted font-mono uppercase tracking-widest text-xs md:text-sm font-bold opacity-80">Practice Law. Think Like a Lawyer.</p>
          </div>

          <div className="mb-10 text-center">
            <span className="inline-block bg-[#F5F5F0] text-primaryBrown font-bold text-xs uppercase tracking-widest px-4 py-2 rounded-full border border-[#D7CCC8]">
              Assume Counsel
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 relative z-10 mb-12">
            {[
              { id: "prosecutor", label: "Public Prosecutor", icon: <Scale size={36} strokeWidth={1.5} /> },
              { id: "defense", label: "Defense Counsel", icon: <Briefcase size={36} strokeWidth={1.5} /> },
              { id: "judge", label: "Hon'ble Judge", icon: <Hand size={36} strokeWidth={1.5} /> }
            ].map(role => (
              <button
                key={role.id}
                onClick={() => setUserRole(role.id)}
                className={`flex flex-col items-center justify-center p-8 rounded-xl border-2 transition-all duration-300 ${userRole === role.id ? 'border-gold bg-[#FCFBF8] shadow-[0_8px_20px_rgba(197,160,89,0.15)] scale-105' : 'border-[#e0e0e0] hover:border-[#D7CCC8] hover:bg-gray-50'}`}
              >
                <div className={`${userRole === role.id ? 'text-gold' : 'text-textMuted'} mb-5 transition-colors`}>{role.icon}</div>
                <span className={`font-heading font-extrabold text-sm md:text-[15px] uppercase tracking-wider ${userRole === role.id ? 'text-primaryBrown' : 'text-textMuted'}`}>
                  {role.label}
                </span>
                {userRole === role.id && (
                  <div className="mt-3 w-12 h-1 bg-gold rounded-full"></div>
                )}
              </button>
            ))}
          </div>

          <div className="flex flex-col md:flex-row items-center justify-center gap-6 relative z-10 border-t border-[#f0f0f0] pt-10">
            <button className="flex items-center gap-3 text-sm font-bold text-primaryBrown border border-[#D7CCC8] bg-white px-6 py-4 rounded-lg hover:bg-[#F5F5F0] transition-colors shadow-sm w-full md:w-auto justify-center">
               <Briefcase size={18} /> Upload Case Files
            </button>

            <button
              onClick={() => setActiveScreen("courtroom")}
              className="bg-primaryBrown text-white font-bold px-10 py-4 rounded-lg shadow-xl shadow-primaryBrown/20 transition-all hover:bg-[#4E342E] hover:-translate-y-1 active:translate-y-0 tracking-widest uppercase flex items-center justify-center gap-3 text-sm w-full md:w-auto"
            >
               Begin Proceedings <Play fill="currentColor" size={16} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return <CourtroomInterface userRole={userRole} onExit={() => setActiveScreen("setup")} />;
}

function CourtroomInterface({ userRole, onExit }) {
  const [messages, setMessages] = useState([]);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [status, setStatus] = useState("idle"); 
  const [trialPhase, setTrialPhase] = useState("PROCEEDINGS INITIATION");
  const [inputText, setInputText] = useState("");

  const roleNameMap = {
    prosecutor: "Public Prosecutor",
    defense: "Defense Counsel",
    judge: "Hon’ble Judge"
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
  };

  const startCasePractice = () => {
    setStatus("running");
    
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
                 }, 1500);
             }, 2000);
          }, 3000);

        }, 1000);
    } else {
        setTrialPhase("AWAITING YOUR OPENING");
        // Immediately yield to user if they are prosecutor or judge for demo purposes
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
    
    setInputText("");
    
    setTimeout(() => {
       setActiveSpeaker("judge");
       setTrialPhase("JUDICIAL QUESTIONING");
       setTimeout(() => {
          handleEvent({
            agent_id: "judge",
            display_name: "Hon’ble Judge",
            full_text: "The court notes the counsel's argument. However, please clarify the specific elements of 'dishonest intention' you are contesting based on the precedents.",
            verified_citations: []
          });
          setTimeout(() => {
              setActiveSpeaker(null);
              setTrialPhase("COUNSEL CLARIFICATION");
          }, 3500);
       }, 1500);
    }, 1000);
  };

  return (
    <div className="h-screen flex bg-[#FAF9F6] text-textPrimary font-body">

      {/* LEFT PANEL */}
      <div className="w-[320px] lg:w-[360px] flex-shrink-0 border-r border-[#D7CCC8] p-5 lg:p-6 flex flex-col gap-4 relative bg-[#FCFBF8] z-20 shadow-xl overflow-y-auto">
        <div className="flex justify-between items-center z-10 pb-2 border-b border-[#EBE7E0]">
            <div>
              <h1 className="text-xl lg:text-[22px] font-heading font-extrabold text-[#3E2723] tracking-tight leading-snug cursor-pointer" onClick={onExit}>
                MootCourt.<span className="text-gold">ai</span>
              </h1>
            </div>
            
            <button className="relative p-2 bg-white border border-[#D7CCC8] shadow-sm rounded-lg text-primaryBrown hover:bg-gold/10 hover:text-gold transition-all" title="Upload Case Files">
               <Briefcase size={20} />
            </button>
        </div>

        {/* CASE FILE */}
        <div className="bg-[#FAEED1] shadow-[0_2px_10px_rgba(0,0,0,0.05)] rounded-tr-xl rounded-b-xl border border-[#D7CCC8] px-4 py-3 relative mt-3 h-auto z-10">
          <div className="absolute -top-[23px] left-[-1px] bg-[#FAEED1] px-4 py-1.5 rounded-t-lg border-t border-l border-r border-[#D7CCC8] text-[9px] font-black text-primaryBrown uppercase tracking-wider">
            Case File 402-B
          </div>
          <h2 className="font-heading font-bold mb-2 text-[16px] leading-tight text-[#3E2723]">State <span className="text-xs italic font-normal">vs.</span> Sharma</h2>
          <ul className="text-xs space-y-2 text-textPrimary/90 font-mono">
            <li className="flex justify-between border-b border-[#D7CCC8]/40 pb-1">
                <span className="font-bold text-[#8D6E63] uppercase text-[9px] tracking-widest">FIR No</span> <span>2024/005</span>
            </li>
            <li className="flex justify-between border-b border-[#D7CCC8]/40 pb-1">
                <span className="font-bold text-[#8D6E63] uppercase text-[9px] tracking-widest">Charge</span> 
                <span className="bg-white/60 px-1 rounded font-bold text-[#8B0000]">IPC 379</span>
            </li>
          </ul>
        </div>

        {/* LEXIGRAPH VISUALIZER */}
        <div className="bg-white p-4 rounded-lg shadow-sm border border-[#EBE7E0] flex flex-col gap-2 relative z-10 w-full flex-shrink-0 mt-2">
          <div className="flex items-center gap-2 text-[#5D4037] border-b border-[#f0f0f0] pb-2">
            <Network size={16} strokeWidth={2.5} />
            <span className="font-heading font-extrabold text-[11px] uppercase tracking-[0.1em]">LexiGraph Evidence</span>
          </div>
          <div className="relative h-[110px] w-full bg-[#FAFAFA] rounded border border-dashed border-[#dcdcdc] flex items-center justify-center overflow-hidden">
             
             {inputText.length > 5 || activeSpeaker ? (
               <div className="absolute flex flex-col items-center justify-center w-full h-full p-2 animate-[fadeIn_0.5s_ease-out]">
                  <div className="flex items-center w-full justify-center">
                      <div className="p-1 px-3 border-2 border-gold rounded-full bg-white text-[10px] font-bold text-[#3E2723] shadow-md z-10 transition-transform hover:scale-110 cursor-pointer">IPC 379</div>
                      
                      {/* Animated connecting line */}
                      <svg className="w-12 h-2 -mx-2 z-0 opacity-60" viewBox="0 0 100 20">
                         <path d="M0,10 L100,10" fill="none" stroke="#C5A059" strokeWidth="4" strokeDasharray="6,6" className="animate-[pulse_1s_linear_infinite]" />
                      </svg>
                      
                      <div className="p-1 px-3 border-2 border-[#8B0000] rounded-full bg-white text-[10px] font-bold text-[#8B0000] shadow-md z-10 transition-transform hover:scale-110 cursor-pointer">Mens Rea</div>
                  </div>
                  
                  {inputText.length > 15 && (
                      <div className="flex items-center w-full justify-center animate-[fadeIn_1s_ease-out] relative">
                          <svg className="absolute w-2 h-8 -top-8 left-[40%] z-0 opacity-40 shrink-0" viewBox="0 0 10 40">
                             <path d="M5,0 L5,40" fill="none" stroke="#1E88E5" strokeWidth="4" strokeDasharray="4,4" />
                          </svg>
                          <div className="mt-2 p-1 px-3 ml-4 border-2 border-[#1E88E5] rounded-full bg-white text-[9px] font-bold text-[#1E88E5] shadow-sm z-10 transition-transform hover:scale-110 cursor-pointer">Intent Absent</div>
                      </div>
                  )}
               </div>
            ) : (
               <p className="text-[10px] text-textMuted font-mono bg-white/50 px-2 py-1 rounded">Awaiting active reasoning...</p>
            )}

          </div>
        </div>

        {/* LEGAL COACH INTERVENTION */}
        {status === "running" && (
            <div className="bg-gradient-to-br from-[#E3F2FD] to-[#f4faff] border border-[#90CAF9] p-5 rounded-lg shadow-sm mt-3 mb-auto animate-[fadeIn_0.5s_ease-out]">
                <div className="flex items-center gap-2 text-[#1565C0] font-black text-[10.5px] uppercase tracking-widest mb-3">
                    <Lightbulb size={16} className="fill-[#bbdefb]" /> Legal Guidance
                </div>
                <div className="text-[12px] text-[#0D47A1] leading-relaxed space-y-3">
                    <p className="font-bold border-b border-blue-200 pb-1 text-xs">You should:</p>
                    <div className="space-y-2">
                        <p className="flex items-start gap-2 font-medium">
                           <GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500" /> 
                           <span>Challenge intent interpretation under <span className="relative group inline-block">
                               <span className="font-bold underline decoration-2 decoration-[#64B5F6] cursor-help transition-all hover:bg-white text-blue-800 rounded px-0.5">Section 378</span>
                               <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-white border border-[#90CAF9] rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 text-[11px] font-serif text-[#3E2723] leading-relaxed">
                                  <strong>IPC Section 378 - Theft:</strong><br/>Whoever, intending to take dishonestly any moveable property out of the possession of any person without that person's consent...
                               </div>
                           </span>.</span>
                        </p>
                        <p className="flex items-start gap-2 font-medium"><GitCommit size={14} className="mt-0.5 shrink-0 text-blue-500" /> Emphasize lack of direct eyewitness evidence.</p>
                    </div>
                    <div className="mt-4 p-3 bg-white/80 rounded border border-blue-200 shadow-inner">
                        <span className="font-bold text-[9px] uppercase tracking-widest text-[#1565C0] block mb-1">Suggested Form:</span>
                        <span className="italic text-[11.5px]">"It is submitted that the prosecution has failed to establish dishonest intention..."</span>
                    </div>
                </div>
            </div>
        )}

        {status === "idle" && (
          <div className="mt-auto pt-6">
            <button
              onClick={startCasePractice}
              className="bg-primaryBrown text-white font-bold px-4 py-4 rounded-lg shadow-md hover:bg-[#4E342E] hover:-translate-y-0.5 active:translate-y-0 w-full tracking-[0.2em] text-[13px] uppercase flex items-center justify-center gap-2 transition-all border border-[#3E2723]"
            >
              Start Case Practice <Play fill="currentColor" size={14} />
            </button>
          </div>
        )}
      </div>

      {/* RIGHT PANEL */}
      <div className="flex-1 flex flex-col relative w-[calc(100%-320px)] overflow-hidden bg-[#FBFBFA]">
        


        <CourtroomStage
          activeSpeaker={activeSpeaker}
          lastMessage={messages[messages.length - 1]}
          userRole={userRole}
        />
        
        <ChatPanel messages={messages} userRole={userRole} />

        {/* STRUCTURED LEGAL NOTEPAD / USER ACTION ZONE */}
        {status === "running" && (
            <div className="bg-[#FAF7F2] px-6 lg:px-10 py-5 border-t border-[#D7CCC8] shadow-[0_-10px_35px_rgba(0,0,0,0.06)] z-30 flex justify-center animate-[slideUp_0.4s_ease-out]">
                <form onSubmit={submitUserInput} className="w-full max-w-4xl relative flex flex-col gap-3">
                    
                    {/* User Power Tools */}
                    <div className="flex justify-between items-end px-1 pb-1">
                       <span className={`text-[12px] font-black uppercase tracking-widest ${activeSpeaker ? 'text-primaryBrown/50' : 'text-gold drop-shadow-md'} flex items-center gap-2 transition-colors`}>
                         <div className={`w-2 h-2 rounded-full ${activeSpeaker ? 'bg-primaryBrown/30' : 'bg-gold animate-pulse'}`}></div> 
                         {activeSpeaker ? 'Awaiting turn...' : 'You have the floor'}
                       </span>
                       
                       <div className="flex gap-4">
                          <button type="button" className="flex items-center gap-2 text-[10px] uppercase font-black tracking-widest text-[#0D47A1] bg-[#E3F2FD] px-4 py-2 rounded-lg border border-[#90CAF9] hover:bg-[#BBDEFB] hover:border-[#42A5F5] transition-all shadow-sm">
                              <BookOpen size={14} /> Consult Legal Database
                          </button>
                          {/* Emphasized Objection Button */}
                          <button type="button" className="flex items-center gap-2 text-[10px] uppercase font-black tracking-widest text-white bg-[#D32F2F] px-4 py-2 rounded-lg border border-[#B71C1C] hover:bg-[#C62828] hover:shadow-md transition-all shadow-sm ml-2">
                              <AlertTriangle size={14} fill="currentColor" className="text-white" /> Raise Objection
                          </button>
                       </div>
                    </div>

                    {/* STRUCTURED NOTEPAD */}
                    <div className={`relative group shadow-lg border-[2px] rounded-xl overflow-hidden transition-all flex flex-col bg-[#FCFBF8] ${activeSpeaker ? 'border-[#EBE7E0]' : 'border-gold focus-within:ring-4 focus-within:ring-gold/20'}`}>
                      
                      {/* Guidelines Header */}
                      <div className="bg-[#F5F5F0] border-b border-[#EBE7E0] px-5 py-3 flex items-center gap-3">
                        <span className="text-[10px] font-black tracking-[0.25em] uppercase text-[#5D4037]">Guidelines:</span>
                        <span className="text-[11px] font-mono text-[#5D4037]/80 flex items-center gap-2 font-medium">
                           ▪ State facts clearly ▪ Formally address the Hon'ble Court
                        </span>
                      </div>

                      <div className="flex flex-1">
                        <div className="w-12 bg-white border-r border-[#EBE7E0] flex flex-col items-center pt-4 shrink-0 shadow-[inset_-2px_0_4px_rgba(0,0,0,0.01)]">
                           {/* Legal pad margin line */}
                           <div className="h-full w-px bg-red-800/15 ml-4"></div>
                        </div>
                        <textarea 
                           value={inputText}
                           onChange={(e) => setInputText(e.target.value)}
                           disabled={activeSpeaker !== null}
                           placeholder={activeSpeaker ? "Opposing counsel is presenting arguments..." : "Draft your structured pleading here..."}
                           className={`w-full bg-transparent border-none focus:outline-none px-6 py-4 text-[17px] font-serif leading-[1.8] resize-none h-[80px] ${activeSpeaker ? 'opacity-50 text-textMuted' : 'opacity-100 text-[#212121]'}`}
                        />
                      </div>

                      <button 
                         type="submit" 
                         disabled={inputText.length < 20 || activeSpeaker !== null} 
                         className={`absolute right-4 bottom-4 px-6 py-3 rounded-lg shadow-lg font-bold text-[11px] uppercase tracking-[0.15em] flex items-center gap-2 z-10 transition-all ${inputText.length > 20 && !activeSpeaker ? 'bg-gold text-[#3E2723] hover:bg-[#b08d4b] hover:-translate-y-0.5' : 'bg-[#EBE7E0] text-[#8D6E63] cursor-not-allowed border border-[#D7CCC8]'}`}
                      >
                          Submit to Court Record <Send size={15} />
                      </button>
                    </div>
                </form>
            </div>
        )}
      </div>
    </div>
  );
}