import { useState } from "react";
import LandingPage from "../components/landing/LandingPage";
import CourtroomInterface from "../components/courtroom/CourtroomInterface";

export default function HomePage() {
  const [activeScreen, setActiveScreen] = useState("landing"); // "landing" | "courtroom"
  const [userRole, setUserRole] = useState("defense"); // "prosecutor" | "defense" | "judge"
  const [gameId, setGameId] = useState(null);

  if (activeScreen === "landing") {
    return (
      <LandingPage 
        userRole={userRole} 
        setUserRole={setUserRole} 
        onEnterCourt={(newGameId) => {
          if (newGameId) setGameId(newGameId);
          setActiveScreen("courtroom");
        }} 
      />
    );
  }

  return (
    <CourtroomInterface 
      userRole={userRole} 
      gameId={gameId}
      onExit={() => {
        setActiveScreen("landing");
        setGameId(null);
      }} 
    />
  );
}