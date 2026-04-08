import Avatar from "./Avatar";

export default function CourtroomStage({ activeSpeaker, lastMessage, userRole }) {
  const isJudgeView = userRole === "judge";

  const getAgentStyle = (role) => {
    const isActive = activeSpeaker === role;
    return `relative transition-all duration-500 flex flex-col items-center ${
      isActive ? "scale-110 drop-shadow-2xl z-30" : "opacity-60 grayscale-[30%] scale-95 z-10"
    }`;
  };

  return (
    <div className="h-[45%] min-h-[300px] relative overflow-hidden bg-[#EFEBE9] flex flex-col border-b-4 border-[#3E2723]">
      
      {/* 1. THE WALL & BENCH (Background Layer) */}
      <div className="absolute top-0 w-full h-[35%] bg-[#3E2723] shadow-2xl z-0">
        <div className="w-full h-full opacity-20 bg-[url('https://www.transparenttextures.com/patterns/wood-pattern.png')]"></div>
        {/* The Judge's elevated platform edge */}
        <div className="absolute bottom-0 w-full h-4 bg-[#2E1A17] border-t border-white/10"></div>
      </div>

      {/* 2. THE JUDGE (Middle Layer) */}
      {!isJudgeView && (
        <div className="absolute top-[8%] left-1/2 -translate-x-1/2 z-10 flex flex-col items-center">
          <div className={getAgentStyle('judge')}>
            <Avatar role="judge" name="HON’BLE JUDGE" active={activeSpeaker === "judge"} message={lastMessage?.agentId === "judge" ? lastMessage.text : ""} />
          </div>
        </div>
      )}

      {/* 3. THE FLOOR (Perspective Layer) */}
      <div className="absolute bottom-0 w-full h-[65%] bg-[#D7CCC8] origin-bottom [transform:perspective(1000px)_rotateX(20deg)] z-0 shadow-inner">
         <div className="w-full h-full opacity-10 bg-[url('https://www.transparenttextures.com/patterns/dark-matter.png')]"></div>
      </div>

      {/* 4. THE COUNSELS & EVIDENCE (Foreground Layer) */}
      <div className="relative flex justify-between items-end w-full h-full px-10 pb-4 z-20">
        
        {/* PROSECUTOR SIDE */}
        <div className="w-[120px] flex flex-col items-center">
          {userRole !== 'prosecutor' && (
            <div className={getAgentStyle('prosecutor')}>
              <Avatar role="prosecutor" name="PUBLIC PROSECUTOR" active={activeSpeaker === "prosecutor"} message={lastMessage?.agentId === "prosecutor" ? lastMessage.text : ""} />
            </div>
          )}
          <div className="w-full h-24 bg-[#5D4037] rounded-t-lg border-x-4 border-t-8 border-[#3E2723] shadow-[0_15px_30px_rgba(0,0,0,0.5)]"></div>
        </div>

        {/* EVIDENCE DESK (Center) */}
        <div className="mb-2 opacity-80 scale-90">
           <div className="w-32 h-16 bg-[#6D4C41] border-t-[6px] border-[#4E342E] shadow-xl flex items-center justify-center relative">
              <div className="absolute top-[-5px] right-2 w-10 h-1 bg-white rotate-[-5deg] rounded-sm shadow-sm border border-[#ccc]"></div>
              <div className="absolute top-[-6px] left-2 w-12 h-1 bg-[#FCEBA6] rotate-[3deg] rounded-sm shadow border border-[#D7CCC8]"></div>
              <span className="text-[8px] text-white/40 font-bold tracking-[0.2em] uppercase mt-2">Evidence Desk</span>
           </div>
        </div>

        {/* DEFENSE SIDE */}
        <div className="w-[120px] flex flex-col items-center">
          {userRole !== 'defense' && (
            <div className={getAgentStyle('defense')}>
              <Avatar role="defense" name="DEFENSE COUNSEL" active={activeSpeaker === "defense"} message={lastMessage?.agentId === "defense" ? lastMessage.text : ""} />
            </div>
          )}
          <div className="w-full h-24 bg-[#5D4037] rounded-t-lg border-x-4 border-t-8 border-[#3E2723] shadow-[0_15px_30px_rgba(0,0,0,0.5)]"></div>
        </div>
      </div>

      {/* 5. USER'S POV PODIUM (Overlay Layer) */}
      {!isJudgeView && (
        <div className="absolute -bottom-10 left-1/2 -translate-x-1/2 w-[70%] max-w-[600px] h-32 bg-[#2E1A17] rounded-t-[100px] border-t-8 border-[#5D4037] z-50 shadow-[0_-20px_50px_rgba(0,0,0,0.6)]">
           <div className="flex justify-center pt-4">
              <span className="text-gold/50 text-[10px] tracking-[0.5em] font-bold uppercase drop-shadow">Your Podium</span>
           </div>
        </div>
      )}

      {/* JUDGE'S POV CORRECTION */}
      {isJudgeView && (
        <div className="absolute top-[-20px] left-1/2 -translate-x-1/2 w-[90%] max-w-[800px] h-24 bg-[#2E1A17] rounded-b-[40px] border-b-8 border-[#5D4037] z-50 shadow-[0_20px_50px_rgba(0,0,0,0.8)]">
        </div>
      )}
    </div>
  );
}
