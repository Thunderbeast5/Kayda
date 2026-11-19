import { memo } from "react";
import room from "../assets/courtroom/room4.png";
import judgeDesk from "../assets/courtroom/judge-table.png";
import prosecutorDesk from "../assets/courtroom/prosecutor-table.png";
import defenseDesk from "../assets/courtroom/defense-table.png";
import gallery from "../assets/courtroom/public.png";
import judge from "../assets/courtroom/judge.png";
import prosecutor from "../assets/courtroom/pro.png";
import defense from "../assets/courtroom/def.png";
import audience from "../assets/courtroom/audience.png";

const A = {
  room,
  judgeDesk,
  prosecutorDesk,
  defenseDesk,
  gallery,
  judge,
  prosecutor,
  defense,
  audience,
};

// All positions are % of the 1846x852 reference scene, so everything scales together.
const LAYOUT = {
  judge:      { avatar: { left: 46.4, top: 32.0, width: 7.2 },  desk: { left: 27.1, top: 37.8, width: 45.7 } },
  prosecutor: { avatar: { left: 15.7, top: 38.0, width: 6.8 },  desk: { left: 7.3,  top: 47.8, width: 23.8 } },
  defense:    { avatar: { left: 77.8, top: 38.0, width: 6.8 },  desk: { left: 68.9, top: 47.8, width: 24.5 } },
};

// Stable Desk component outside CourtroomStage to prevent unmount/remount flickering during typing
const Desk = memo(function Desk({ role, src, z }) {
  const { desk } = LAYOUT[role];
  return (
    <img
      src={src}
      alt=""
      draggable={false}
      className="absolute select-none pointer-events-none"
      style={{ left: `${desk.left}%`, top: `${desk.top}%`, width: `${desk.width}%`, zIndex: z }}
    />
  );
});

const Figure = memo(function Figure({ role, src, activeSpeaker, message, isUser, bubbleSide = "top", showBubble = true }) {
  const { avatar } = LAYOUT[role];
  const isActive = activeSpeaker === role;

  return (
    <div
      className="absolute z-[20] flex flex-col items-center"
      style={{ left: `${avatar.left}%`, top: `${avatar.top}%`, width: `${avatar.width}%` }}
    >
      {!isUser && (
        <img
          src={src}
          alt={role}
          draggable={false}
          className={`w-full select-none origin-bottom transition-all duration-500 ${
            isActive
              ? role === "judge"
                ? "scale-[1.10] brightness-105 drop-shadow-[0_0_16px_rgba(212,175,55,0.9)]"
                : "scale-[1.08] brightness-100 drop-shadow-[0_0_10px_rgba(255,200,100,0.7)]"
              : ""
          }`}
        />
      )}

      {isUser && (
        <div className="w-full aspect-square flex items-center justify-center">
          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gold text-[7px] md:text-[9px] font-bold tracking-[0.2em] uppercase">
            You
          </span>
        </div>
      )}

      {/* Speech bubble / cloud: disabled for judge, retained for prosecutor & defense */}
      {showBubble && role !== "judge" && isActive && message && (
        <div
          className={`absolute z-50 w-[220%] max-w-[190px] rounded-md bg-surface-paperMain text-black/80 shadow-lg border border-wood-dark px-2 py-1 text-[8px] md:text-[10px] leading-snug line-clamp-3 ${
            bubbleSide === "side" ? "left-full ml-2 top-0" : "bottom-full mb-1 left-1/2 -translate-x-1/2"
          }`}
        >
          {message}
        </div>
      )}
    </div>
  );
});

function CourtroomStage({ activeSpeaker, lastMessage, userRole }) {
  const msgFor = (role) => (lastMessage?.agentId === role ? lastMessage.text : "");

  return (
    <div
      className="relative w-full overflow-hidden shrink-0 border-b-4 border-wood-dark bg-surface-court"
      style={{
        height: "min(46.15vw, 360px)", // keeps the 1846:852 ratio, capped on desktop
        backgroundImage: `url(${A.room})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      {/* Scene: fixed aspect ratio, centered */}
      <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 h-full aspect-[1846/852]">
        {/* 1. ROOM BACKGROUND */}
        <img
          src={A.room}
          alt=""
          draggable={false}
          className="absolute inset-0 w-full h-full select-none pointer-events-none z-0"
        />

        {/* 2. JUDGE (in front of his desk) */}
        <div style={{ zIndex: 20 }} className="absolute inset-0 pointer-events-none">
          <div className="relative w-full h-full pointer-events-auto">
            <Figure
              role="judge"
              src={A.judge}
              activeSpeaker={activeSpeaker}
              message={msgFor("judge")}
              isUser={userRole === "judge"}
              bubbleSide="side"
              showBubble={false}
            />
          </div>
        </div>
        <Desk role="judge" src={A.judgeDesk} z={15} />

        {/* 3. PROSECUTOR + DEFENSE (avatars sit in front of their desks) */}
        <Figure
          role="prosecutor"
          src={A.prosecutor}
          activeSpeaker={activeSpeaker}
          message={msgFor("prosecutor")}
          isUser={userRole === "prosecutor"}
        />
        <Desk role="prosecutor" src={A.prosecutorDesk} z={15} />

        <Figure
          role="defense"
          src={A.defense}
          activeSpeaker={activeSpeaker}
          message={msgFor("defense")}
          isUser={userRole === "defense"}
        />
        <Desk role="defense" src={A.defenseDesk} z={15} />

        {/* 4. AUDIENCE (in front of the public gallery) */}
        <img
          src={A.audience}
          alt=""
          draggable={false}
          className="absolute select-none pointer-events-none z-[50]"
          style={{ left: "5%", top: "66%", width: "22%" }}
        />
        <img
          src={A.audience}
          alt=""
          draggable={false}
          className="absolute select-none pointer-events-none z-[50] -scale-x-100"
          style={{ left: "74%", top: "66.5%", width: "22%" }}
        />

        {/* 5. PUBLIC GALLERY (front rail + benches, covers audience bodies) */}
        <img
          src={A.gallery}
          alt=""
          draggable={false}
          className="absolute left-0 w-full select-none pointer-events-none z-[40]"
          style={{ top: "48%" }}
        />
      </div>
    </div>
  );
}

export default memo(CourtroomStage);