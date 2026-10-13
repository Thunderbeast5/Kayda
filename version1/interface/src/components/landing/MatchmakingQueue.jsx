import React, { useState, useEffect, useRef } from "react";
import { Search, X, CheckCircle2 } from "lucide-react";
import { joinMatchmakingQueue, leaveMatchmakingQueue, pollMatchmakingStatus } from "../../api/matchmakingApi";
import { useAuth } from "../../context/AuthContext";

export default function MatchmakingQueue({ preferredRole, onMatchFound, onCancel }) {
  const { currentUser, userProfile } = useAuth();
  
  const [elapsed, setElapsed] = useState(0);
  const [status, setStatus] = useState("SEARCHING"); // "SEARCHING", "FOUND"
  const [opponent, setOpponent] = useState(null);
  const [assignedRole, setAssignedRole] = useState(null);
  
  // Ensure consistent user ID across matchmaking and courtroom for guest users
  const guestIdKey = "mootcourt_user_id";
  let storedUserId = currentUser?.uid || sessionStorage.getItem(guestIdKey);
  if (!storedUserId) {
    storedUserId = `user_${Math.random().toString(36).substring(2, 9)}`;
    sessionStorage.setItem(guestIdKey, storedUserId);
  }
  const actualUserId = storedUserId;
  const actualUsername = userProfile?.display_name || userProfile?.displayName || currentUser?.displayName || `Advocate_${Math.floor(Math.random() * 1000)}`;
  const actualRating = userProfile?.rating || 1200;

  const pollIntervalRef = useRef(null);
  const timerIntervalRef = useRef(null);

  useEffect(() => {
    // 1. Join queue
    const joinQueue = async () => {
      try {
        await joinMatchmakingQueue(actualUserId, actualUsername, preferredRole, actualRating);
        
        // 2. Start polling
        pollIntervalRef.current = setInterval(async () => {
          try {
            const res = await pollMatchmakingStatus(actualUserId);
            if (res.status === "MATCH_FOUND") {
              handleMatchFound(res);
            } else if (res.status === "NOT_IN_QUEUE") {
              // Re-join if backend reloaded or connection was dropped
              await joinMatchmakingQueue(actualUserId, actualUsername, preferredRole, actualRating);
            }
          } catch (pollErr) {
            console.warn("Poll failed, will retry...", pollErr);
          }
        }, 2000);
      } catch (err) {
        console.error("Failed to join queue", err);
      }
    };

    joinQueue();

    // 3. Start elapsed timer
    timerIntervalRef.current = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);

    return () => {
      cleanup();
    };
  }, [preferredRole]);

  const cleanup = () => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
  };

  const handleMatchFound = (res) => {
    cleanup();
    setStatus("FOUND");
    setOpponent(res.opponent);
    setAssignedRole(res.your_role);
    
    // Automatically transition to game after 2.5 seconds
    setTimeout(() => {
      onMatchFound(res.game_id, res.your_role);
    }, 2500);
  };

  const handleCancel = async () => {
    cleanup();
    await leaveMatchmakingQueue(actualUserId);
    onCancel();
  };

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white rounded-2xl border border-[#E8E2D9] shadow-2xl w-full max-w-md p-8 relative overflow-hidden flex flex-col items-center">
        {/* Background Accent */}
        <div className="absolute top-0 left-0 right-0 h-2 bg-gradient-to-r from-[#8C5A3C] via-[#D4AF37] to-[#8C5A3C]"></div>

        {status === "SEARCHING" ? (
          <>
            <div className="relative mb-8 mt-4">
              <div className="w-24 h-24 rounded-full border-4 border-[#F5F2EC] flex items-center justify-center">
                <Search className="w-10 h-10 text-[#C5A059] animate-pulse" />
              </div>
              {/* Radar ripple effect */}
              <div className="absolute inset-0 rounded-full border-2 border-[#D4AF37] animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite] opacity-20"></div>
              <div className="absolute inset-0 rounded-full border-2 border-[#D4AF37] animate-[ping_3s_cubic-bezier(0,0,0.2,1)_infinite] opacity-10" style={{ animationDelay: '1s' }}></div>
            </div>

            <h2 className="font-heading text-2xl font-bold text-[#2C1810] mb-2">Finding Match</h2>
            <p className="font-body text-[#5D4037]/70 text-sm mb-6 text-center">
              Searching for a compatible opponent for <span className="font-bold">{preferredRole.toLowerCase()}</span>...
            </p>

            <div className="bg-[#FAF8F5] border border-[#E8E2D9] rounded-lg px-6 py-4 mb-8 flex flex-col items-center w-full">
              <span className="text-[11px] font-mono uppercase tracking-widest text-[#8C5A3C] mb-1">Time Elapsed</span>
              <span className="font-mono text-3xl text-[#2C1810] font-bold">{formatTime(elapsed)}</span>
            </div>

            <button 
              onClick={handleCancel}
              className="group flex items-center gap-2 px-6 py-3 rounded-full border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 transition-colors duration-300"
            >
              <X className="w-4 h-4 group-hover:rotate-90 transition-transform duration-300" />
              <span className="text-sm font-semibold tracking-wide uppercase">Cancel</span>
            </button>
          </>
        ) : (
          <>
            <div className="mb-8 mt-4">
              <div className="w-24 h-24 rounded-full bg-green-50 flex items-center justify-center animate-[bounce_0.5s_ease-out]">
                <CheckCircle2 className="w-12 h-12 text-green-500" />
              </div>
            </div>

            <h2 className="font-heading text-3xl font-bold text-[#2C1810] mb-2">Match Found!</h2>
            
            <div className="bg-gradient-to-br from-[#FAF8F5] to-white border border-[#D4AF37]/30 rounded-xl p-5 w-full mt-4 mb-2 shadow-inner">
              <div className="flex justify-between items-center mb-4">
                <div className="text-center">
                  <p className="text-[10px] font-mono text-[#8C5A3C] uppercase tracking-wider mb-1">You</p>
                  <p className="font-bold text-[#2C1810]">{actualUsername}</p>
                  <p className="text-xs font-semibold text-[#D4AF37]">{assignedRole}</p>
                </div>
                <div className="text-xl font-bold text-[#5D4037]/30">VS</div>
                <div className="text-center">
                  <p className="text-[10px] font-mono text-[#8C5A3C] uppercase tracking-wider mb-1">Opponent</p>
                  <p className="font-bold text-[#2C1810]">{opponent?.username || "Opponent"}</p>
                  <p className="text-xs font-semibold text-[#D4AF37]">{assignedRole === "DEFENSE" ? "PROSECUTION" : "DEFENSE"}</p>
                </div>
              </div>
            </div>
            
            <p className="font-body text-sm text-[#5D4037] animate-pulse mt-4">
              Entering courtroom...
            </p>
          </>
        )}
      </div>
    </div>
  );
}
