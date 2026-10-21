import Avatar from "./Avatar";

export default function CourtroomStage({ activeSpeaker, lastMessage, userRole }) {
  const isJudgeView = userRole === "judge";

  const getAgentStyle = (role) => {
    const isActive = activeSpeaker === role;
    return `relative transition-all duration-500 flex flex-col items-center ${
      isActive ? "scale-110 md:scale-110 drop-shadow-2xl z-30" : "opacity-60 grayscale-[30%] scale-90 md:scale-95 z-10"
    }`;
  };

  return (
    <div className="h-[220px] relative overflow-hidden bg-surface-court flex flex-col border-b-4 border-wood-dark shrink-0">
      
      {/* 1. THE WALL & BENCH */}
      <div className="absolute top-0 w-full h-[35%] bg-wood-dark shadow-md z-0">
        <div className="w-full h-full opacity-20 bg-[url('https://www.transparenttextures.com/patterns/wood-pattern.png')]"></div>
        <div className="absolute bottom-0 w-full h-2 bg-wood-deep border-t border-white/10"></div>
      </div>

      {/* 2. THE JUDGE */}
      {!isJudgeView && (
        <div className="absolute top-[4%] left-1/2 -translate-x-1/2 z-10 flex flex-col items-center">
          <div className={getAgentStyle('judge')}>
            <Avatar role="judge" name="HON’BLE JUDGE" active={activeSpeaker === "judge"} message={lastMessage?.agentId === "judge" ? lastMessage.text : ""} />
          </div>
        </div>
      )}

      {/* 3. THE FLOOR */}
      <div className="absolute bottom-0 w-full h-[65%] bg-surface-border origin-bottom [transform:perspective(600px)_rotateX(15deg)] z-0 shadow-inner">
         <div className="w-full h-full opacity-10 bg-[url('https://www.transparenttextures.com/patterns/dark-matter.png')]"></div>
      </div>

      {/* 4. THE COUNSELS & EVIDENCE */}
      <div className="relative w-full h-full z-20">
        <div className="max-w-5xl mx-auto h-full flex justify-between items-end px-4 md:px-10 pb-1.5 md:pb-2.5 transition-all duration-[350ms] ease-in-out">
          
          {/* PROSECUTOR SIDE */}
          <div className="w-[80px] md:w-[120px] flex flex-col items-center">
            {userRole !== 'prosecutor' && (
              <div className={getAgentStyle('prosecutor')}>
                <Avatar role="prosecutor" name="PUBLIC PROSECUTOR" active={activeSpeaker === "prosecutor"} message={lastMessage?.agentId === "prosecutor" ? lastMessage.text : ""} />
              </div>
            )}
            <div className="w-full h-12 md:h-14 bg-primaryBrown rounded-t-mg border-x-4 border-t-[4px] md:border-t-6 border-wood-dark shadow-[0_10px_20px_rgba(0,0,0,0.4)]"></div>
          </div>

          {/* EVIDENCE DESK */}
          <div className="mb-1.5 opacity-80 scale-75 md:scale-90 flex-shrink-0">
             <div className="w-24 md:w-32 h-10 md:h-12 bg-wood-light border-t-[4px] border-wood-light shadow-lg flex items-center justify-center relative">
                <div className="absolute top-[-4px] right-1 md:right-2 w-6 md:w-10 h-1 bg-white rotate-[-5deg] rounded-sm shadow-sm border border-surface-border"></div>
                <div className="absolute top-[-5px] left-1 md:left-2 w-8 md:w-12 h-1 bg-surface-paperMain rotate-[3deg] rounded-sm shadow border border-surface-border"></div>
                <span className="text-[6px] md:text-[8px] text-white/40 font-bold tracking-[0.2em] uppercase mt-1">Evidence Desk</span>
             </div>
          </div>

          {/* DEFENSE SIDE */}
          <div className="w-[80px] md:w-[120px] flex flex-col items-center">
            {userRole !== 'defense' && (
              <div className={getAgentStyle('defense')}>
                <Avatar role="defense" name="DEFENSE COUNSEL" active={activeSpeaker === "defense"} message={lastMessage?.agentId === "defense" ? lastMessage.text : ""} />
              </div>
            )}
            <div className="w-full h-12 md:h-14 bg-primaryBrown rounded-t-lg border-x-4 border-t-[4px] md:border-t-6 border-wood-dark shadow-[0_10px_20px_rgba(0,0,0,0.4)]"></div>
          </div>
        </div>
      </div>

      {/* 5. USER'S POV PODIUM */}
      {!isJudgeView && (
        <div className="absolute -bottom-12 left-1/2 -translate-x-1/2 w-[90%] md:w-[70%] max-w-[600px] h-20 md:h-24 bg-wood-deep rounded-t-[50px] border-t-[4px] md:border-t-6 border-primaryBrown z-50 shadow-[0_-15px_40px_rgba(0,0,0,0.5)]">
           <div className="flex justify-center pt-1.5 md:pt-2.5">
              <span className="text-gold/50 text-[8px] tracking-[0.4em] font-bold uppercase drop-shadow">Your Podium</span>
           </div>
        </div>
      )}

      {/* JUDGE'S POV CORRECTION */}
      {isJudgeView && (
        <div className="absolute top-[-15px] left-1/2 -translate-x-1/2 w-[95%] md:w-[90%] max-w-[800px] h-16 bg-wood-deep rounded-b-[20px] border-b-[4px] md:border-b-6 border-primaryBrown z-50 shadow-[0_20px_50px_rgba(0,0,0,0.8)]">
        </div>
      )}

      {/* COURT IN SESSION DIVIDER - BOTTOM */}
      <div className="absolute bottom-0 w-full flex items-center justify-center opacity-70 select-none z-40 pt-2 pb-1.5">
        <div className="h-px bg-primaryBrown flex-1"></div>
        <div className="px-6 font-serif text-[10px] font-black tracking-[0.4em] uppercase text-primaryBrown">Court In Session</div>
        <div className="h-px bg-primaryBrown flex-1"></div>
      </div>
    </div>
  );
}
