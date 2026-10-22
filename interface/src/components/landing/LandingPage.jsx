import { useState, useEffect } from "react";
import { centerpieceScript } from "../../data/centerpieceScript";
import LandingNavbar from "./LandingNavbar";
import LandingHero from "./LandingHero";
import RoleSelector from "./RoleSelector";
import SimulationCenterpiece from "./SimulationCenterpiece";
import JudicialCouncilSection from "./JudicialCouncilSection";
import WorkspaceUtilitiesSection from "./WorkspaceUtilitiesSection";
import TrialLifecycleSection from "./TrialLifecycleSection";
import TestimonialsSection from "./TestimonialsSection";
import FaqSection from "./FaqSection";
import SummonsCtaSection from "./SummonsCtaSection";
import LandingFooter from "./LandingFooter";

export default function LandingPage({ userRole, setUserRole, onEnterCourt }) {
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
      <LandingNavbar scrollToSection={scrollToSection} />
      <LandingHero scrollToSection={scrollToSection} />
      {/* <RoleSelector setUserRole={setUserRole} onEnterCourt={onEnterCourt} /> */}
      <SimulationCenterpiece 
        simMessages={simMessages}
        setSimMessages={setSimMessages}
        currentSimIndex={currentSimIndex}
        setCurrentSimIndex={setCurrentSimIndex}
        isTyping={isTyping}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
        activeSpeaker={activeSpeaker}
        setActiveSpeaker={setActiveSpeaker}
      />
      <JudicialCouncilSection scrollToSection={scrollToSection} />
      <WorkspaceUtilitiesSection />
      <TrialLifecycleSection />
      <TestimonialsSection />
      <FaqSection openFaqIndex={openFaqIndex} toggleFaq={toggleFaq} />
      <SummonsCtaSection scrollToSection={scrollToSection} />
      <LandingFooter scrollToSection={scrollToSection} />
    </div>
  );
}
