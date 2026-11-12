// import { useState, useEffect, useRef } from "react";
// import { ChevronLeft, ChevronRight, Menu, Volume2, VolumeX } from "lucide-react";
// import CourtroomStage from "../CourtroomStage";
// import ChatPanel from "../ChatPanel";
// import CourtroomSidebar from "./CourtroomSidebar";
// import CourtroomInputBar from "./CourtroomInputBar";
// import CaseSelectionModal from "./CaseSelectionModal";
// import { getMockResponse } from "../../data/mockTrialResponses";
// import { uploadCaseFile } from "../../firebase";

// export default function CourtroomInterface({ userRole, onExit }) {
//   const [messages, setMessages] = useState([]);
//   const [activeSpeaker, setActiveSpeaker] = useState(null);
//   const [status, setStatus] = useState("running"); 
//   const [trialPhase, setTrialPhase] = useState("PROCEEDINGS INITIATION");
//   const [sidebarOpen, setSidebarOpen] = useState(false);
//   const [inputText, setInputText] = useState("");
//   const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
//   const [ttsEnabled, setTtsEnabled] = useState(false);
//   const ttsEnabledRef = useRef(false);

//   // Case Selection & Observer Mode state
//   const [isCaseModalOpen, setIsCaseModalOpen] = useState(false);
//   const [selectedCaseId, setSelectedCaseId] = useState("1");
//   const [caseData, setCaseData] = useState({
//     fileId: "1",
//     title: "Sasikala Pushpa vs. State of Tamil Nadu",
//     firNo: "LAWS(SC)-2019-5-25",
//     charge: "S.438 CrPC / IPC 193",
//     evidenceLinked: true
//   });

//   const observerSourceRef = useRef(null);

//   // This is the piece that was missing: nothing in the app previously
//   // opened a connection to /api/simulate/<case_id>. Selecting a case only
//   // ever updated the sidebar's case card — the trial itself never started.
//   const runObserverSimulation = (caseId) => {
//     if (observerSourceRef.current) {
//       observerSourceRef.current.close(); // stop any playback already in flight
//     }

//     setMessages([]);
//     setActiveSpeaker(null);
//     setTrialPhase("PROCEEDINGS INITIATION");

//     const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
//     const es = new EventSource(`${apiUrl}/api/simulate/${caseId}`);
//     observerSourceRef.current = es;

//     es.onmessage = (e) => {
//       const evt = JSON.parse(e.data);
//       if (evt.type === "verdict") {
//         setActiveSpeaker(null);
//         setTrialPhase("PROCEEDINGS CONCLUDED");
//         es.close();
//         observerSourceRef.current = null;
//         return;
//       }
//       handleEvent(evt);
//     };

//     es.onerror = (err) => {
//       console.error("Observer stream error:", err);
//       es.close();
//       observerSourceRef.current = null;
//     };
//   };

//   const handleSelectCase = async (caseId) => {
//     try {
//       setSelectedCaseId(caseId);
//       const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
//       const res = await fetch(`${apiUrl}/api/cases/${caseId}`);
//       if (res.ok) {
//         const data = await res.json();
//         if (data.caseData) {
//           setCaseData(data.caseData);
//         }
//       }
//       if (userRole === "observer") {
//         runObserverSimulation(caseId); // restart playback for the newly picked case
//       }
//     } catch (err) {
//       console.error("Error fetching case details:", err);
//     }
//   };

//   const [uploadStatus, setUploadStatus] = useState(null);
//   const [uploadProgress, setUploadProgress] = useState(0);
//   const [uploadedFileName, setUploadedFileName] = useState("");

//   const fileInputRef = useRef(null);

//   // Speech-to-Text States
//   const [isListening, setIsListening] = useState(false);
//   const recognitionRef = useRef(null);

//   useEffect(() => {
//     if (typeof window !== "undefined") {
//       const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
//       if (SpeechRecognitionClass) {
//         const rec = new SpeechRecognitionClass();
//         rec.continuous = false;
//         rec.interimResults = false;
//         rec.lang = "en-IN";

//         rec.onresult = (event) => {
//           const transcript = event.results[0][0].transcript;
//           if (transcript) {
//             setInputText((prev) => {
//               const spacing = prev ? " " : "";
//               return prev + spacing + transcript;
//             });
//           }
//         };

//         rec.onerror = (e) => {
//           console.error("Speech recognition error:", e);
//           setIsListening(false);
//         };

//         rec.onend = () => {
//           setIsListening(false);
//         };

//         recognitionRef.current = rec;
//       }
//     }
//   }, []);

//   const toggleListening = () => {
//     if (!recognitionRef.current) {
//       alert("Speech-to-Text is not supported or permitted in this browser configuration. Please use Google Chrome.");
//       return;
//     }

//     if (isListening) {
//       recognitionRef.current.stop();
//     } else {
//       try {
//         recognitionRef.current.start();
//         setIsListening(true);
//       } catch (err) {
//         console.error("Recognition start failed:", err);
//       }
//     }
//   };

//   const handleSidebarFileUpload = (e) => {
//     const file = e.target.files[0];
//     if (!file) return;

//     setUploadedFileName(file.name);
//     setUploadStatus("uploading");
//     setUploadProgress(0);

//     uploadCaseFile(file, (progress) => {
//       setUploadProgress(progress);
//     })
//     .then((result) => {
//       setUploadStatus("analyzing");
      
//       setTimeout(() => {
//         const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
//         const capitalize = (str) => str.replace(/\b\w/g, c => c.toUpperCase());
        
//         const accuses = ["Karan Johar", "Rajesh Gupta", "Meera Sen", "Vikram Rathore", "Sanjay Mehta"];
//         const selectedAccused = capitalize(cleanName.split(" ").slice(0, 2).join(" ")) || accuses[Math.floor(Math.random() * accuses.length)];
//         const selectedCharge = cleanName.toLowerCase().includes("fraud") 
//           ? "IPC 420" 
//           : cleanName.toLowerCase().includes("assault") 
//             ? "IPC 323" 
//             : "IPC 379";
        
//         const newCase = {
//           fileId: Math.floor(Math.random() * 900 + 100).toString() + "-A",
//           title: `State vs. ${selectedAccused}`,
//           firNo: `2026/${Math.floor(Math.random() * 900 + 100)}`,
//           charge: selectedCharge,
//           evidenceLinked: true
//         };

//         setCaseData(newCase);
//         setUploadStatus(null);
        
//         setMessages([]);
//         setActiveSpeaker("judge");
//         setTrialPhase("PROCEEDINGS INITIATION");
        
//         setTimeout(() => {
//           handleEvent({
//             agent_id: "judge",
//             display_name: "Hon’ble Judge",
//             full_text: `The court is now in session for the newly uploaded file. Case File ${newCase.fileId}: ${newCase.title}. Under charges of ${newCase.charge}, the Defense Counsel and Public Prosecutor may state their grounds.`,
//             verified_citations: [],
//           });
          
//           setTimeout(() => {
//             setActiveSpeaker("prosecutor");
//             setTimeout(() => {
//               handleEvent({
//                 agent_id: "prosecutor",
//                 display_name: "Public Prosecutor",
//                 full_text: `Your Honor, regarding the case of ${newCase.title}, the state submits that the evidence recovered from the accused's possession constitutes clear intent and action under ${newCase.charge}. We are prepared to proceed.`,
//                 verified_citations: [newCase.charge],
//               });
              
//               setTimeout(() => {
//                 setActiveSpeaker(null);
//                 setTrialPhase("DEFENSE REBUTTAL");
//               }, 500);
//             }, 800);
//           }, 1000);

//         }, 300);

//       }, 1500);
//     })
//     .catch((err) => {
//       console.error("Upload error:", err);
//       setUploadStatus(null);
//     });
//   };

//   useEffect(() => {
//     ttsEnabledRef.current = ttsEnabled;
//   }, [ttsEnabled]);

//   useEffect(() => {
//     // Disable body scroll when courtroom is active to prevent scrolling the landing page
//     document.body.style.overflow = 'hidden';
    
//     // Automatically trigger courtroom proceedings on mount
//     startCasePractice();

//     return () => {
//       document.body.style.overflow = '';
//       if (window.speechSynthesis) {
//         window.speechSynthesis.cancel();
//       }
//       if (observerSourceRef.current) {
//         observerSourceRef.current.close();
//       }
//     };
//   }, []);

//   const speakText = (text, voiceRole) => {
//     if (!window.speechSynthesis) return;
//     window.speechSynthesis.cancel(); // stop current speech
    
//     const utterance = new SpeechSynthesisUtterance(text);
//     const voices = window.speechSynthesis.getVoices();
    
//     // Find an English voice if available
//     const englishVoice = voices.find(v => v.lang.startsWith("en-"));
//     if (englishVoice) {
//       utterance.voice = englishVoice;
//     }
    
//     if (voiceRole === "judge") {
//       utterance.rate = 0.85;
//       utterance.pitch = 0.95;
//     } else if (voiceRole === "prosecutor") {
//       utterance.rate = 0.95;
//       utterance.pitch = 1.0;
//     } else if (voiceRole === "defense") {
//       utterance.rate = 1.0;
//       utterance.pitch = 1.05;
//     }
    
//     window.speechSynthesis.speak(utterance);
//   };

//   const roleNameMap = {
//     prosecutor: "Public Prosecutor",
//     defense: "Defense Counsel",
//     judge: "Hon’ble Judge",
//     observer: "Court Observer"
//   };

//   const handleEvent = (event) => {
//     setActiveSpeaker(event.agent_id);
//     setMessages((prev) => [
//       ...prev,
//       {
//         speaker: event.display_name,
//         text: event.full_text,
//         citations: event.verified_citations,
//         agentId: event.agent_id
//       },
//     ]);

//     if (ttsEnabledRef.current) {
//       speakText(event.full_text, event.agent_id);
//     }
//   };

//   const startCasePractice = () => {
//     setStatus("running");
//     setSidebarOpen(false); // Close sidebar on mobile when started
    
//     if (userRole === "observer") {
//         runObserverSimulation(selectedCaseId);
//     } else if (userRole === "defense") {
//         setTrialPhase("PROSECUTION OPENING STATEMENT");
//         setActiveSpeaker("judge");
//         setTimeout(() => {
//           handleEvent({
//             agent_id: "judge",
//             display_name: "Hon’ble Judge",
//             full_text: "The court is in session. State vs. Rahul Sharma. Public Prosecutor, please present your opening framing of the charges.",
//             verified_citations: [],
//           });
          
//           setTimeout(() => {
//              setActiveSpeaker("prosecutor");
//              setTimeout(() => {
//                  handleEvent({
//                     agent_id: "prosecutor",
//                     display_name: "Public Prosecutor",
//                     full_text: "May it please the Hon’ble Court, on the night of Oct 12th, the accused intentionally relocated the complainant's property without consent. The evidence definitively establishes theft under Section 379.",
//                     verified_citations: ["IPC 379"],
//                  });
//                  setTimeout(() => {
//                      setActiveSpeaker(null);
//                      setTrialPhase("DEFENSE REBUTTAL");
//                  }, 500);
//              }, 800);
//           }, 1000);

//         }, 100);
//     } else {
//         setTrialPhase("AWAITING YOUR OPENING");
//     }
//   };

//   const submitUserInput = (e) => {
//     e.preventDefault();
//     if (inputText.length < 20) {
//       alert("COURT PROTOCOL VIOLATION:\n\nPlease provide a structured legal argument (minimum 20 characters).\nInformal or short phrases are not acceptable on the court record.");
//       return;
//     }
    
//     const userRoleName = roleNameMap[userRole];
    
//     setMessages(prev => [...prev, {
//       speaker: userRoleName,
//       text: inputText,
//       citations: [],
//       agentId: userRole
//     }]);
    
//     const query = inputText;
//     setInputText("");
    
//     // Call backend API
//     fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:5001'}/api/query`, {
//       method: "POST",
//       headers: {
//         "Content-Type": "application/json"
//       },
//       body: JSON.stringify({ query: query })
//     })
//     .then(response => {
//       if (!response.ok) {
//         throw new Error(`HTTP error! status: ${response.status}`);
//       }
//       return response.json();
//     })
//     .then(data => {
//       if (data.success) {
//         // Map agent names to display names
//         const agentDisplayNames = {
//           "Prosecutor": "Public Prosecutor",
//           "Accused": "Defense Counsel"
//         };
        
//         setTimeout(() => {
//           setActiveSpeaker(data.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense");
//           setTrialPhase(`${data.agent.toUpperCase()} RESPONSE`);
          
//           setTimeout(() => {
//             handleEvent({
//               agent_id: data.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense",
//               display_name: agentDisplayNames[data.agent] || data.agent,
//               full_text: data.response,
//               verified_citations: []
//             });
            
//             setTimeout(() => {
//               setActiveSpeaker(null);
//               setTrialPhase("AWAITING RESPONSE");
//             }, 2000);
//           }, 500);
//         }, 500);
//       } else {
//         alert("Error: " + (data.error || "Unknown error"));
//         setActiveSpeaker(null);
//       }
//     })
//     .catch(error => {
//       console.warn("Backend unavailable, using demo mode:", error.message);

//       // Offline fallback: use mock responses
//       const mockData = getMockResponse(query, userRole);
//       const agentDisplayNames = {
//         "Prosecutor": "Public Prosecutor",
//         "Accused": "Defense Counsel"
//       };

//       setTimeout(() => {
//         setActiveSpeaker(mockData.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense");
//         setTrialPhase(`${mockData.agent.toUpperCase()} RESPONSE (DEMO)`);

//         setTimeout(() => {
//           handleEvent({
//             agent_id: mockData.agent.toLowerCase() === "prosecutor" ? "prosecutor" : "defense",
//             display_name: agentDisplayNames[mockData.agent] || mockData.agent,
//             full_text: mockData.response,
//             verified_citations: mockData.citations || []
//           });

//           setTimeout(() => {
//             setActiveSpeaker(null);
//             setTrialPhase("AWAITING RESPONSE");
//           }, 2000);
//         }, 500);
//       }, 800);
//     });
//   };

//   return (
//     <div className="h-screen flex bg-surface-court text-textPrimary font-body overflow-hidden">
//       <CourtroomSidebar
//         sidebarOpen={sidebarOpen}
//         setSidebarOpen={setSidebarOpen}
//         sidebarCollapsed={sidebarCollapsed}
//         onExit={onExit}
//         caseData={caseData}
//         onOpenCaseModal={() => setIsCaseModalOpen(true)}
//         uploadStatus={uploadStatus}
//         uploadProgress={uploadProgress}
//         uploadedFileName={uploadedFileName}
//         handleSidebarFileUpload={handleSidebarFileUpload}
//         fileInputRef={fileInputRef}
//         inputText={inputText}
//         activeSpeaker={activeSpeaker}
//         status={status}
//       />

//       <CaseSelectionModal
//         isOpen={isCaseModalOpen}
//         onClose={() => setIsCaseModalOpen(false)}
//         onSelectCase={handleSelectCase}
//         currentCaseId={selectedCaseId}
//       />

//       {/* RIGHT PANEL */}
//       <div className="flex-1 flex flex-col relative w-full md:w-auto overflow-hidden bg-white transition-all duration-[350ms] ease-in-out">
        
//         {/* Floating Sidebar Toggle Button (Desktop & Tablet) */}
//         <button
//           onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
//           className="hidden md:flex absolute left-4 top-1/2 -translate-y-1/2 z-40 p-2.5 bg-white border border-surface-border shadow-md rounded-lg text-primaryBrown hover:bg-gold/10 hover:text-gold hover:scale-105 transition-all duration-[350ms] ease-in-out cursor-pointer group"
//           title={sidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
//         >
//           {sidebarCollapsed ? <ChevronRight size={16} className="group-hover:translate-x-0.5 transition-transform" /> : <ChevronLeft size={16} className="group-hover:-translate-x-0.5 transition-transform" />}
//         </button>
        
//         {/* MOBILE HEADER FOR RIGHT PANEL */}
//         <div className="md:hidden flex justify-between items-center bg-white border-b border-surface-border p-3 z-30 shadow-[0_2px_10px_rgba(0,0,0,0.05)] relative shrink-0">
//            <button onClick={() => setSidebarOpen(true)} className="p-1.5 bg-[#FAF8F5] rounded text-primaryBrown border border-surface-border cursor-pointer">
//               <Menu size={18} />
//            </button>
//            <h1 className="text-sm font-heading font-extrabold text-wood-dark cursor-pointer" onClick={onExit}>Kayda</h1>
//            <div className="flex items-center gap-2">
//              <button
//                onClick={() => setTtsEnabled(!ttsEnabled)}
//                className="p-1.5 text-primaryBrown rounded cursor-pointer"
//                title={ttsEnabled ? "Mute Readout" : "Unmute Readout"}
//              >
//                {ttsEnabled ? <Volume2 size={18} className="text-gold" /> : <VolumeX size={18} />}
//              </button>
//              {status === "idle" && (
//                 <button onClick={() => setSidebarOpen(true)} className="text-[9px] font-bold uppercase tracking-widest text-primaryBrown bg-gold/20 px-2.5 py-1.5 rounded cursor-pointer">Setup</button>
//              )}
//              {status !== "idle" && (
//                 <span className="text-[8px] font-black uppercase tracking-widest text-wood-dark border border-surface-border px-2 py-1 rounded bg-[#FAF8F5]">{trialPhase.substring(0, 10)}...</span>
//              )}
//            </div>
//         </div>

//         <CourtroomStage
//           activeSpeaker={activeSpeaker}
//           lastMessage={messages[messages.length - 1]}
//           userRole={userRole}
//         />
        
//         <ChatPanel messages={messages} userRole={userRole} speakText={speakText} />

//         {userRole !== "observer" && (
//           <CourtroomInputBar
//             status={status}
//             activeSpeaker={activeSpeaker}
//             inputText={inputText}
//             setInputText={setInputText}
//             submitUserInput={submitUserInput}
//             isListening={isListening}
//             toggleListening={toggleListening}
//             ttsEnabled={ttsEnabled}
//             setTtsEnabled={setTtsEnabled}
//           />
//         )}
//       </div>
//     </div>
//   );
// }

import { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Menu, Volume2, VolumeX } from "lucide-react";
import CourtroomStage from "../CourtroomStage";
import ChatPanel from "../ChatPanel";
import CourtroomSidebar from "./CourtroomSidebar";
import CourtroomInputBar from "./CourtroomInputBar";
import ObserverControlBar from "./ObserverControlBar";
import CaseSelectionModal from "./CaseSelectionModal";
import { getMockResponse } from "../../data/mockTrialResponses";
import { uploadCaseFile } from "../../firebase";
import { useAuth } from "../../context/AuthContext";

export default function CourtroomInterface({ userRole, gameId, onExit }) {
  const { currentUser } = useAuth();
  const userId = currentUser?.uid || sessionStorage.getItem("mootcourt_user_id") || "guest_player";

  const [messages, setMessages] = useState([]);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [status, setStatus] = useState("running"); 
  const [trialPhase, setTrialPhase] = useState("PROCEEDINGS INITIATION");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputText, setInputText] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const ttsEnabledRef = useRef(false);
  
  // WebSocket Reference
  const wsRef = useRef(null);

  // ── Orchestrator SSE state ──────────────────────────────────────────────────
  const [caseQuery, setCaseQuery] = useState("");
  const [showCasePrompt, setShowCasePrompt] = useState(false);
  const [orchestratorRunning, setOrchestratorRunning] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const sseAbortRef = useRef(null);

  // Case Selection & Observer Mode state
  const [isCaseModalOpen, setIsCaseModalOpen] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState("1");
  const [caseData, setCaseData] = useState({
    fileId: "1",
    title: "Sasikala Pushpa vs. State of Tamil Nadu",
    firNo: "LAWS(SC)-2019-5-25",
    charge: "Code of Criminal Procedure, 1973 - S.438, S.340",
    evidenceLinked: true,
    case_facts: [],
    evidence_inventory: [],
  });

  const [observerEvents, setObserverEvents] = useState([]);
  const [observerIndex, setObserverIndex] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(false);

  // Auto-play timer effect
  useEffect(() => {
    let timer = null;
    if (isAutoPlaying && observerEvents.length > 0 && observerIndex < observerEvents.length) {
      timer = setTimeout(() => {
        revealNextObserverTurn();
      }, 2400);
    } else if (observerEvents.length > 0 && observerIndex >= observerEvents.length) {
      setIsAutoPlaying(false);
    }
    return () => clearTimeout(timer);
  }, [isAutoPlaying, observerIndex, observerEvents]);

  // Loads the full transcript for a case once — no SSE, no pacing.
  // The user clicks "Next" to reveal each turn or uses "Auto-Play".
  const loadObserverEvents = async (caseId) => {
    let targetCaseId = caseId || "1";
    setMessages([]);
    setActiveSpeaker(null);
    setObserverIndex(0);
    setIsAutoPlaying(false);
    setTrialPhase("PROCEEDINGS INITIATION");

    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
      let res = await fetch(`${apiUrl}/api/simulate/${targetCaseId}/events`);
      if (!res.ok && targetCaseId !== "1") {
        console.warn(`Case ${targetCaseId} failed, falling back to case 1`);
        targetCaseId = "1";
        setSelectedCaseId("1");
        res = await fetch(`${apiUrl}/api/simulate/1/events`);
      }
      if (!res.ok) throw new Error(`Server status ${res.status}`);
      const data = await res.json();
      setObserverEvents(data.events || []);

      // Also refresh caseData details
      const cRes = await fetch(`${apiUrl}/api/cases/${targetCaseId}`);
      if (cRes.ok) {
        const cData = await cRes.json();
        if (cData.caseData) {
          setCaseData(cData.caseData);
        }
      }
    } catch (err) {
      console.error("Failed to load simulation transcript:", err);
      setObserverEvents([]);
    }
  };

  const revealNextObserverTurn = () => {
    if (observerIndex >= observerEvents.length) return;
    const evt = observerEvents[observerIndex];
    handleEvent(evt);
    const nextIndex = observerIndex + 1;
    setObserverIndex(nextIndex);
    setTrialPhase(
      nextIndex >= observerEvents.length
        ? "PROCEEDINGS CONCLUDED"
        : `TURN ${nextIndex + 1} OF ${observerEvents.length}`
    );
  };

  const restartObserverPlayback = () => {
    setMessages([]);
    setActiveSpeaker(null);
    setObserverIndex(0);
    setIsAutoPlaying(false);
    setTrialPhase("PROCEEDINGS INITIATION");
  };

  const handleSelectCase = async (caseId) => {
    try {
      setSelectedCaseId(caseId);
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
      const res = await fetch(`${apiUrl}/api/cases/${caseId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.caseData) {
          setCaseData(data.caseData);
        }
      }
      loadObserverEvents(caseId);
    } catch (err) {
      console.error("Error fetching case details:", err);
    }
  };

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
    
    // If we have a gameId, connect to WebSocket for multiplayer mode
    if (gameId && userId) {
      // Guard against React StrictMode double-mount: defer WS creation by one tick.
      // StrictMode cleans up synchronously before the next tick, so the clearTimeout
      // in the cleanup cancels the first phantom mount — no stale connection is created.
      let ws = null;
      let readyFired = false;

      const timer = setTimeout(() => {
        const baseApi = import.meta.env.VITE_API_URL || "https://kayda-agents.onrender.com";
        const wsBase = baseApi.replace(/^http/, "ws");
        const wsUrl = `${wsBase}/ws/games/${gameId}?user_id=${userId}`;
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (readyFired) return;  // idempotency guard
          readyFired = true;
          // Signal backend we are ready to play
          const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
          fetch(`${apiUrl}/api/games/${gameId}/ready?user_id=${userId}`, { method: "POST" })
            .then(r => r.json())
            .then(d => console.log("[WS] Ready response:", d))
            .catch(e => console.error("[WS] Ready error:", e));
        };

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          console.log("WS Event:", data);

          if (data.type === "GAME_STARTED") {
            setStatus("running");
            setSidebarOpen(false);
            setTrialPhase(data.phase || "CASE_INTRO");
            if (data.current_turn === userId) {
              setActiveSpeaker(userRole);
            } else {
              setActiveSpeaker(userRole === "prosecutor" ? "defense" : "prosecutor");
            }
          } else if (data.type === "TURN_CHANGED") {
            setTrialPhase(data.phase);
            if (data.current_turn === userId) {
              setActiveSpeaker(userRole);
            } else {
              setActiveSpeaker(userRole === "prosecutor" ? "defense" : "prosecutor");
            }
          } else if (data.type === "ACTION_SUBMITTED") {
            const isMe = data.player_id === userId;
            const fullContent = data.payload?.content || data.payload?.text || data.content || data.text || "";
            if (fullContent) {
              handleEvent({
                agent_id: isMe ? userRole : (userRole === "prosecutor" ? "defense" : "prosecutor"),
                display_name: isMe
                  ? `[YOU] ${roleNameMap[userRole]}`
                  : roleNameMap[userRole === "prosecutor" ? "defense" : "prosecutor"],
                full_text: fullContent,
                verified_citations: [],
                isUser: isMe,
              });
            }
            setTrialPhase(data.phase);
            if (data.next_turn === userId) {
              setActiveSpeaker(userRole);
            } else {
              setActiveSpeaker(userRole === "prosecutor" ? "defense" : "prosecutor");
            }
          } else if (data.type === "JUDGE_MESSAGE" || data.type === "JUDGE_INTERRUPTION") {
            handleEvent({
              agent_id: "judge",
              display_name: data.display_name || "Hon’ble Judge",
              full_text: data.content,
              verified_citations: data.citations || [],
            });
            setActiveSpeaker("judge");
            if (data.phase) {
              setTrialPhase(data.phase);
            }
            if (data.active_turn) {
              setTimeout(() => {
                if (data.active_turn === userId) {
                  setActiveSpeaker(userRole);
                } else {
                  setActiveSpeaker(userRole === "prosecutor" ? "defense" : "prosecutor");
                }
              }, 4500);
            }
          } else if (data.type === "OBJECTION_RAISED") {
            const isMe = data.player_id === userId;
            const objectingRole = data.player_role || (isMe ? userRole : (userRole === "prosecutor" ? "defense" : "prosecutor"));
            handleEvent({
              agent_id: objectingRole,
              display_name: isMe ? `[YOU] ${roleNameMap[userRole]}` : roleNameMap[objectingRole],
              full_text: `⚠️ OBJECTION: ${data.text || "Formal objection raised to the Court."}`,
              verified_citations: [],
            });
            setActiveSpeaker(objectingRole);
          } else if (data.type === "GAME_COMPLETED") {
            setStatus("completed");
            setTrialPhase("VERDICT RENDERED");
            if (data.verdict_summary) {
              handleEvent({
                agent_id: "judge",
                display_name: "Hon’ble Judge — Final Order",
                full_text: data.verdict_summary,
                verified_citations: ["Verdict Rendered"],
              });
              setActiveSpeaker("judge");
            }
          } else if (data.type === "PLAYER_CONNECTED") {
            console.log("[WS] Player connected:", data.player?.user_id);
          } else if (data.type === "PLAYER_READY") {
            console.log("[WS] Player ready:", data.player?.user_id);
          }
        };

        ws.onerror = (error) => {
          console.error("[WS] WebSocket error:", error);
        };

        ws.onclose = (e) => {
          console.log("[WS] WebSocket closed:", e.code, e.reason);
        };
      }, 0);

      return () => {
        clearTimeout(timer);
        if (ws && ws.readyState !== WebSocket.CLOSED) {
          ws.close();
        }
        wsRef.current = null;
        document.body.style.overflow = '';
        if (window.speechSynthesis) window.speechSynthesis.cancel();
      };
    } else {
      // Single-player mode
      if (userRole === "observer") {
        startCasePractice();
      } else {
        // Prosecutor/Defense: show case prompt to kick off the orchestrator
        setShowCasePrompt(true);
      }

      return () => {
        document.body.style.overflow = '';
        if (window.speechSynthesis) {
          window.speechSynthesis.cancel();
        }
        // Abort any in-flight SSE stream
        if (sseAbortRef.current) {
          sseAbortRef.current.abort();
          sseAbortRef.current = null;
        }
      };
    }
  }, [gameId, userId, userRole]);

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
    prosecution: "Public Prosecutor",
    defense: "Defense Counsel",
    judge: "Hon’ble Judge",
    observer: "Court Observer"
  };

  const handleEvent = (event) => {
    if (!event) return;

    if (event.session_id && !activeSessionId) {
      setActiveSessionId(event.session_id);
    }

    // 0. Role Assignment from Orchestrator
    if (event.type === "role_assignment") {
      setMessages((prev) => [
        ...prev,
        {
          type: "system",
          agentId: "system",
          speaker: "Court Registrar",
          text: `⚖️ ${event.message || `Session initialized: Mode=${event.mode}, You=${event.user_role}, AI=${event.ai_role}`}`,
          content: event.message,
        }
      ]);
      return;
    }

    // 0b. Awaiting Human Input Turn
    if (event.type === "awaiting_human_input") {
      const isMyTurn = !userRole || event.role === userRole || (event.role === "prosecutor" && userRole === "prosecutor") || (event.role === "defense" && userRole === "defense");
      if (isMyTurn) {
        setActiveSpeaker(event.role);
        setTrialPhase(`YOUR TURN: ${event.display_name?.toUpperCase() || "COUNSEL"}`);
        setMessages((prev) => [
          ...prev,
          {
            type: "prompt",
            agentId: event.role,
            speaker: "Court Protocol",
            text: `⚖️ ${event.prompt || `Your turn to present legal submissions as ${event.display_name}.`}`,
            content: event.prompt,
            isUser: true,
          }
        ]);
      }
      return;
    }

    // 0c. Turn Start (for both Human and AI)
    if (event.type === "turn_start") {
      const spk = event.speaker || event.role || "prosecutor";
      setActiveSpeaker(spk);
      const isMyTurn = Boolean(event.is_human || (userRole && spk === userRole));
      if (isMyTurn) {
        setTrialPhase(`YOUR TURN: ${event.display_name?.toUpperCase() || roleNameMap[spk]?.toUpperCase() || "COUNSEL"}`);
      } else {
        setTrialPhase(`OPPOSING COUNSEL PRESENTING: ${event.display_name || roleNameMap[spk] || "DEFENSE COUNSEL"}`);
      }
      return;
    }

    // 1. Phase change
    if (event.type === "phase_change") {
      const phaseNames = {
        INIT: "PROCEEDINGS INITIATION",
        EVIDENCE: "EVIDENCE EXTRACTION & CLASSIFICATION",
        LEXIGRAPH: "LEXIGRAPH GRAPH RETRIEVAL",
        COURTROOM: `DEBATE ROUND ${event.round || 1}`,
        VERDICT: "JUDICIAL ADJUDICATION",
        DONE: "PROCEEDINGS CONCLUDED",
        FAILED: "SIMULATION FAILED",
      };
      setTrialPhase(phaseNames[event.phase] || event.phase);
      if (event.phase === "DONE") {
        setActiveSpeaker(null);
      }
      return;
    }

    // 2. Verdict Decree
    if (event.type === "verdict") {
      setActiveSpeaker("judge");
      setTrialPhase("VERDICT CONCLUDED");
      setMessages((prev) => [
        ...prev,
        {
          type: "verdict",
          agentId: "verdict",
          result: event.result || "DENIED",
          confidence: event.confidence || event.confidence_label || "high",
          valid_votes: event.valid_votes ?? 3,
          total_votes: event.total_votes ?? 5,
          agree_count: event.agree_count ?? 3,
          statutes: event.statutes || [],
          precedents: event.precedents || [],
          holdings_relied: event.holdings_relied || [],
          vote_tally: event.vote_tally || {},
          explanation: event.explanation || event.reasoning || "",
        }
      ]);
      return;
    }

    // 3. Judge evaluation scores
    if (event.type === "judge_scores") {
      setMessages((prev) => [
        ...prev,
        {
          type: "judge_scores",
          scores: event.scores || {
            prosecution: event.prosecution,
            defense: event.defense,
            overall: event.overall
          }
        }
      ]);
      return;
    }

    // 4. Judicial Inquiry
    if (event.type === "judge_question") {
      setActiveSpeaker("judge");
      setTrialPhase("JUDICIAL INQUIRY");
      const questionText = event.question || "";
      setMessages((prev) => [
        ...prev,
        {
          agentId: "judge",
          speaker: "Hon’ble Judge (Inquiry to Accused)",
          text: questionText,
          content: questionText,
          citations: [],
        }
      ]);
      if (ttsEnabledRef.current && questionText) {
        speakText(questionText, "judge");
      }
      return;
    }

    // 5. Agent message (prosecutor, defense, accused, evidence_analyzer, lexigraph)
    const agent = event.agent || event.agent_id || "prosecutor";
    const isUser = Boolean(event.isUser || event.is_human || (userRole && agent === userRole));
    const displayName = event.display_name || (isUser ? `[YOU] ${roleNameMap[agent] || agent}` : (roleNameMap[agent] || agent.toUpperCase()));
    const content = event.content || event.full_text || event.text || "";
    const citations = event.citations || event.verified_citations || [];
    const evidenceRefs = event.evidence_refs || [];
    const facts = event.facts || [];
    const inventory = event.inventory || [];
    const holdings = event.holdings || [];
    const precedents = event.precedents || [];
    const round = event.round;

    setActiveSpeaker(agent);

    setMessages((prev) => [
      ...prev,
      {
        agentId: agent,
        speaker: displayName,
        text: content,
        content: content,
        citations: citations,
        evidence_refs: evidenceRefs,
        facts: facts,
        inventory: inventory,
        holdings: holdings,
        precedents: precedents,
        round: round,
        isUser: isUser,
      },
    ]);

    if (ttsEnabledRef.current && content) {
      speakText(content, agent);
    }
  };

  const startCasePractice = () => {
    setStatus("running");
    setSidebarOpen(false);
    loadObserverEvents(selectedCaseId);
  };

  // ── Orchestrator SSE Stream ─────────────────────────────────────────────────
  const startOrchestratorStream = async (query) => {
    if (!query || query.trim().length < 10) {
      alert("Please provide a case description (at least 10 characters).");
      return;
    }

    setShowCasePrompt(false);
    setOrchestratorRunning(true);
    setMessages([]);
    setActiveSpeaker(null);
    setTrialPhase("INITIALIZING PIPELINE");
    setStatus("running");

    const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
    const abortCtrl = new AbortController();
    sseAbortRef.current = abortCtrl;
    const sid = `mc_${Date.now().toString(36)}`;
    setActiveSessionId(sid);

    try {
      const response = await fetch(`${apiUrl}/api/orchestrator/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          session_id: sid,
          role: userRole || "prosecutor",
          mode: "ai_vs_human",
          max_rounds: 2,
        }),
        signal: abortCtrl.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr || jsonStr === "{}") continue;
            try {
              const evt = JSON.parse(jsonStr);
              handleEvent(evt);
            } catch (parseErr) {
              console.warn("SSE parse error:", parseErr, jsonStr);
            }
          } else if (line.startsWith("event: done")) {
            // Stream finished
            setOrchestratorRunning(false);
            setTrialPhase("PROCEEDINGS CONCLUDED");
            setActiveSpeaker(null);
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error("Orchestrator SSE error:", err);
        setTrialPhase("CONNECTION ERROR");
      }
    } finally {
      setOrchestratorRunning(false);
      sseAbortRef.current = null;
    }
  };

  const submitUserInput = (e) => {
    e.preventDefault();
    
    // CASE_INTRO: just send END_TURN to advance phase — no text needed
    if (e._caseIntro && gameId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "END_TURN", text: "" }));
      return;
    }

    if (inputText.length < 20) {
      alert("COURT PROTOCOL VIOLATION:\n\nPlease provide a structured legal argument (minimum 20 characters).\nInformal or short phrases are not acceptable on the court record.");
      return;
    }
    
    const query = inputText;
    setInputText("");
    
    if (gameId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      // Map server-controlled phase → action type
      // trialPhase comes from GAME_STARTED/TURN_CHANGED events (server truth)
      const phaseActionMap = {
        "CASE_INTRO": "SUBMIT_OPENING",
        "OPENING": "SUBMIT_OPENING",
        "ARGUMENT": "SUBMIT_ARGUMENT",
        "REBUTTAL": "SUBMIT_REBUTTAL",
        "CLOSING": "SUBMIT_ARGUMENT", // fallback
      };
      const actionType = phaseActionMap[trialPhase] || "SUBMIT_ARGUMENT";

      wsRef.current.send(JSON.stringify({
        action: actionType,
        text: query
      }));
      // ⚠️ Do NOT add to messages here — the ACTION_SUBMITTED broadcast
      // from the server will add it for BOTH players uniformly.
      return;
    }

    // In orchestrator AI vs Human mode, send argument to active orchestrator session
    if (orchestratorRunning) {
      const userRoleName = roleNameMap[userRole] || (userRole === "prosecutor" ? "Public Prosecutor" : "Defense Counsel");
      setMessages((prev) => [
        ...prev,
        {
          agentId: userRole,
          speaker: `[YOU] ${userRoleName}`,
          text: query,
          content: query,
          citations: [],
          evidence_refs: [],
          isUser: true,
        },
      ]);
      const opponentRole = userRole === "prosecutor" ? "defense" : "prosecutor";
      setActiveSpeaker(opponentRole);
      setTrialPhase(`OPPOSING COUNSEL PRESENTING: ${roleNameMap[opponentRole] || "DEFENSE COUNSEL"}`);

      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
      fetch(`${apiUrl}/api/orchestrator/submit-argument`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeSessionId || "",
          argument: query,
          role: userRole || "prosecutor",
        }),
      }).catch((err) => console.error("Error submitting argument to orchestrator:", err));
      return;
    }
    
    // In legacy single-player mode, immediately display user's message in the feed
    const userRoleName = roleNameMap[userRole] || (userRole === "prosecutor" ? "Public Prosecutor" : "Defense Counsel");
    setMessages((prev) => [
      ...prev,
      {
        agentId: userRole,
        speaker: `[YOU] ${userRoleName}`,
        text: query,
        content: query,
        citations: [],
        evidence_refs: [],
        isUser: true,
      },
    ]);

    // Call single-player backend API
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

  const raiseObjection = (reason = "Objection: Submissions exceed the evidentiary record.") => {
    if (gameId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: "RAISE_OBJECTION",
        text: reason
      }));
    } else {
      alert("Objection Raised!\nThe Court has noted your objection.");
    }
  };

  return (
    <div className="h-screen flex bg-surface-court text-textPrimary font-body overflow-hidden">
      <CourtroomSidebar
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        sidebarCollapsed={sidebarCollapsed}
        onExit={onExit}
        caseData={caseData}
        onOpenCaseModal={() => setIsCaseModalOpen(true)}
        uploadStatus={uploadStatus}
        uploadProgress={uploadProgress}
        uploadedFileName={uploadedFileName}
        handleSidebarFileUpload={handleSidebarFileUpload}
        fileInputRef={fileInputRef}
        inputText={inputText}
        activeSpeaker={activeSpeaker}
        latestMessage={messages[messages.length - 1] || null}
        status={status}
        onRaiseObjection={raiseObjection}
      />

      <CaseSelectionModal
        isOpen={isCaseModalOpen}
        onClose={() => setIsCaseModalOpen(false)}
        onSelectCase={handleSelectCase}
        currentCaseId={selectedCaseId}
      />

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
           <button onClick={() => setSidebarOpen(true)} className="p-1.5 bg-[#FAF8F5] rounded text-primaryBrown border border-surface-border cursor-pointer">
              <Menu size={18} />
           </button>
           <h1 className="text-sm font-heading font-extrabold text-wood-dark cursor-pointer" onClick={onExit}>Kayda</h1>
           <div className="flex items-center gap-2">
             <button
               onClick={() => setTtsEnabled(!ttsEnabled)}
               className="p-1.5 text-primaryBrown rounded cursor-pointer"
               title={ttsEnabled ? "Mute Readout" : "Unmute Readout"}
             >
               {ttsEnabled ? <Volume2 size={18} className="text-gold" /> : <VolumeX size={18} />}
             </button>
             {status === "idle" && (
                <button onClick={() => setSidebarOpen(true)} className="text-[9px] font-bold uppercase tracking-widest text-primaryBrown bg-gold/20 px-2.5 py-1.5 rounded cursor-pointer">Setup</button>
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

        {/* Case Prompt Modal for Prosecutor/Defense */}
        {showCasePrompt && (userRole === "prosecutor" || userRole === "defense") && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl border border-[#D4AF37]/30 p-8 max-w-xl w-full mx-4 animate-in fade-in">
              <div className="text-center mb-6">
                <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-[#C5A059] font-bold block mb-2">
                  {userRole === "prosecutor" ? "Public Prosecutor" : "Defense Counsel"}
                </span>
                <h2 className="font-heading text-2xl font-bold text-[#2C1810] mb-1">
                  Enter Case Description
                </h2>
                <p className="text-xs text-[#5D4037]/70">
                  Provide the FIR, case facts, or a brief description to initiate the court session.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => setCaseQuery("The accused, Ramesh Kumar, allegedly stabbed the victim Suresh Gupta with a kitchen knife outside a restaurant on 12 March 2026. Two eyewitnesses were present. The victim was hospitalized and survived. A blood-stained kitchen knife was recovered from the accused's bag.")}
                  className="text-[10px] font-mono bg-[#D4AF37]/10 hover:bg-[#D4AF37]/25 text-[#8C6D1F] border border-[#D4AF37]/30 px-2.5 py-1 rounded-md transition-colors cursor-pointer"
                >
                  ⚡ Load Demo Assault Case (S.324 IPC)
                </button>
                <button
                  type="button"
                  onClick={() => setCaseQuery("Anticipatory bail petition under Section 438 CrPC. Allegations of fabricated affidavit under Section 193 IPC. Petitioner Sasikala Pushpa seeks pre-arrest protection claiming political vendetta and non-service of summons.")}
                  className="text-[10px] font-mono bg-[#8C2D19]/10 hover:bg-[#8C2D19]/25 text-[#8C2D19] border border-[#8C2D19]/30 px-2.5 py-1 rounded-md transition-colors cursor-pointer"
                >
                  ⚡ Load Sasikala Bail Case (S.438 CrPC)
                </button>
              </div>
              <textarea
                value={caseQuery}
                onChange={(e) => setCaseQuery(e.target.value)}
                placeholder="e.g. The accused, Ramesh Kumar, allegedly stabbed the victim Suresh Gupta with a kitchen knife outside a restaurant on 12 March 2026. Two eyewitnesses were present..."
                className="w-full h-36 p-4 border border-[#D4AF37]/30 rounded-xl text-sm font-body text-[#2C1810] placeholder:text-[#5D4037]/40 focus:outline-none focus:ring-2 focus:ring-[#D4AF37]/50 resize-none bg-[#FAF9F7]"
                autoFocus
              />
              <div className="flex gap-3 mt-5">
                <button
                  onClick={onExit}
                  className="flex-1 py-3 rounded-xl border border-[#D4AF37]/30 text-sm font-semibold text-[#5D4037] hover:bg-[#FAF9F7] transition-colors cursor-pointer"
                >
                  Back to Role Selection
                </button>
                <button
                  onClick={() => startOrchestratorStream(caseQuery)}
                  disabled={caseQuery.trim().length < 10}
                  className="flex-1 py-3 rounded-xl bg-[#2C1810] text-white text-sm font-semibold hover:bg-[#1a0f0a] transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Begin Court Session
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Bottom bar: Observer controls OR Input bar OR Pipeline status */}
        {userRole === "observer" ? (
          <ObserverControlBar
            currentIndex={observerIndex}
            totalTurns={observerEvents.length}
            onNext={revealNextObserverTurn}
            onRestart={restartObserverPlayback}
            isAutoPlaying={isAutoPlaying}
            onToggleAutoPlay={() => setIsAutoPlaying(!isAutoPlaying)}
          />
        ) : (
          <div className="w-full flex flex-col">
            {orchestratorRunning && (
              <div className="shrink-0 border-t border-surface-border bg-[#FAF9F7]/90 backdrop-blur-xs px-6 py-2 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-[#D4AF37] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-[#D4AF37] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-[#D4AF37] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-xs font-mono uppercase tracking-widest text-[#5D4037]/80">
                    {trialPhase}
                  </span>
                </div>
                <button
                  onClick={() => {
                    if (sseAbortRef.current) sseAbortRef.current.abort();
                    setOrchestratorRunning(false);
                    setShowCasePrompt(true);
                  }}
                  className="text-[11px] font-mono text-[#8C2D19] hover:underline cursor-pointer"
                >
                  Reset / New Case
                </button>
              </div>
            )}
            <CourtroomInputBar
              status={status}
              activeSpeaker={activeSpeaker}
              isMyTurn={
                activeSpeaker === userRole ||
                (trialPhase && trialPhase.toUpperCase().includes("YOUR TURN")) ||
                (trialPhase === "CASE_INTRO" && userRole === "prosecutor") ||
                (trialPhase === "DEFENSE REBUTTAL" && userRole === "defense")
              }
              trialPhase={trialPhase}
              inputText={inputText}
              setInputText={setInputText}
              submitUserInput={submitUserInput}
              isListening={isListening}
              toggleListening={toggleListening}
              ttsEnabled={ttsEnabled}
              setTtsEnabled={setTtsEnabled}
            />
          </div>
        )}
      </div>
    </div>
  );
}