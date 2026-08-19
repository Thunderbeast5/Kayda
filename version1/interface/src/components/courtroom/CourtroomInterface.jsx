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

export default function CourtroomInterface({ userRole, gameId, onExit }) {
  const [messages, setMessages] = useState([]);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [status, setStatus] = useState("running"); 
  const [trialPhase, setTrialPhase] = useState("PROCEEDINGS INITIATION");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputText, setInputText] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const ttsEnabledRef = useRef(false);

  // Case Selection & Observer Mode state
  const [isCaseModalOpen, setIsCaseModalOpen] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState("1");
  const [caseData, setCaseData] = useState({
    fileId: "1",
    title: "Sasikala Pushpa vs. State of Tamil Nadu",
    firNo: "LAWS(SC)-2019-5-25",
    charge: "S.438 CrPC / IPC 193",
    evidenceLinked: true
  });

  const [observerEvents, setObserverEvents] = useState([]);
  const [observerIndex, setObserverIndex] = useState(0);

  // Loads the full transcript for a case once — no SSE, no pacing.
  // The user clicks "Next" to reveal each turn instead of it auto-playing.
  const loadObserverEvents = async (caseId) => {
    setMessages([]);
    setActiveSpeaker(null);
    setObserverIndex(0);
    setTrialPhase("PROCEEDINGS INITIATION");

    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5001";
      const res = await fetch(`${apiUrl}/api/simulate/${caseId}/events`);
      if (!res.ok) throw new Error(`Server status ${res.status}`);
      const data = await res.json();
      setObserverEvents(data.events || []);
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
      if (userRole === "observer") {
        loadObserverEvents(caseId); // new case picked — load its transcript
      }
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
    
    if (userRole === "observer") {
        loadObserverEvents(selectedCaseId); // loads transcript; user clicks Next to advance
    } else if (userRole === "defense") {
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

        {userRole === "observer" ? (
          <ObserverControlBar
            currentIndex={observerIndex}
            totalTurns={observerEvents.length}
            onNext={revealNextObserverTurn}
            onRestart={restartObserverPlayback}
          />
        ) : (
          <CourtroomInputBar
            status={status}
            activeSpeaker={activeSpeaker}
            inputText={inputText}
            setInputText={setInputText}
            submitUserInput={submitUserInput}
            isListening={isListening}
            toggleListening={toggleListening}
            ttsEnabled={ttsEnabled}
            setTtsEnabled={setTtsEnabled}
          />
        )}
      </div>
    </div>
  );
}