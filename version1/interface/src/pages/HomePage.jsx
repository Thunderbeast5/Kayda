import { useState } from "react";
import LandingPage from "../components/landing/LandingPage";
import CourtroomInterface from "../components/courtroom/CourtroomInterface";

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