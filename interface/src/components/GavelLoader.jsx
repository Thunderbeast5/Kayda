import { useId } from "react";

/**
 * GavelLoader — KAYDA
 * A restrained, premium gavel-strike loading animation.
 *
 * Props
 *  - message  string   Label under the animation (rendered uppercase).   default "Court is in session"
 *  - size     number | string   Width of the artwork (px number or any CSS length).   default 180
 *  - playing  boolean  Loop while true. When false the gavel settles onto the block. default true
 *  - showDots boolean  Show the three-dot indicator.   default true
 *  - className string  Extra classes for the root element.
 *
 * Requires: React 18+ (useId) and Tailwind CSS v3+ (arbitrary values).
 * Background is transparent — it inherits whatever overlay it is placed in.
 */

const STYLES = `
.gl-root { --gl-dur: 2.6s; }

/* ---------- Gavel: pivots around the end of the handle ---------- */
.gl-gavel {
  transform-origin: 188px 142px;
  transform-box: view-box;
  transform: rotate(0deg);
  transition: transform .7s cubic-bezier(.3,.7,.2,1);
  will-change: transform;
}
.gl-play .gl-gavel { animation: gl-swing var(--gl-dur) infinite; }

@keyframes gl-swing {
  0%   { transform: rotate(38deg); animation-timing-function: cubic-bezier(.35,0,.35,1); }
  12%  { transform: rotate(44deg); animation-timing-function: cubic-bezier(.6,0,.95,.5); }
  34%  { transform: rotate(0deg);  animation-timing-function: cubic-bezier(.1,.6,.3,1); }
  41%  { transform: rotate(10deg); animation-timing-function: cubic-bezier(.4,0,.6,1); }
  47%  { transform: rotate(4deg);  animation-timing-function: cubic-bezier(.45,0,.2,1); }
  80%  { transform: rotate(38deg); }
  100% { transform: rotate(38deg); }
}

/* ---------- Sound block: squash, bounce, vibrate ---------- */
.gl-block {
  transform-origin: 110px 192px;
  transform-box: view-box;
  will-change: transform;
}
.gl-play .gl-block { animation: gl-block var(--gl-dur) infinite; }

@keyframes gl-block {
  0%, 33.9% { transform: translate(0px,0px) scale(1,1); }
  34%  { transform: translate(0px,2px)     scale(1.012,.972); animation-timing-function: cubic-bezier(.2,.7,.3,1); }
  38%  { transform: translate(0px,-1.2px)  scale(.996,1.006); }
  42%  { transform: translate(1px,.3px)    scale(1,1); }
  46%  { transform: translate(-.8px,0px)   scale(1,1); }
  50%  { transform: translate(.5px,0px)    scale(1,1); }
  54%  { transform: translate(-.3px,0px)   scale(1,1); }
  58%  { transform: translate(.1px,0px)    scale(1,1); }
  62%, 100% { transform: translate(0px,0px) scale(1,1); }
}

/* ---------- Contact shadow on the block face ---------- */
.gl-contact { opacity: 0; }
.gl-play .gl-contact { animation: gl-contact var(--gl-dur) infinite; }
@keyframes gl-contact {
  0%   { opacity: 0; }
  12%  { opacity: 0; }
  34%  { opacity: .38; }
  41%  { opacity: .12; }
  47%  { opacity: .06; }
  80%, 100% { opacity: 0; }
}

/* ---------- Ripple on the surface ---------- */
.gl-ripple {
  opacity: 0;
  transform-origin: 110px 192px;
  transform-box: view-box;
}
.gl-play .gl-ripple { animation: gl-ripple var(--gl-dur) infinite; }
.gl-play .gl-ripple-2 { animation-delay: .16s; }
@keyframes gl-ripple {
  0%, 33.9% { opacity: 0; transform: scale(1); }
  34%  { opacity: .55; transform: scale(1); animation-timing-function: cubic-bezier(.1,.6,.3,1); }
  72%  { opacity: 0; transform: scale(1.75); }
  100% { opacity: 0; transform: scale(1.75); }
}

/* ---------- Dots ---------- */
.gl-dot { opacity: .35; transform: scale(.85); }
.gl-play .gl-dot { animation: gl-dot 1.4s ease-in-out infinite; }
.gl-play .gl-dot:nth-child(2) { animation-delay: .18s; }
.gl-play .gl-dot:nth-child(3) { animation-delay: .36s; }
@keyframes gl-dot {
  0%, 80%, 100% { opacity: .25; transform: scale(.8); }
  40% { opacity: 1; transform: scale(1); }
}
@keyframes gl-fade {
  0%, 100% { opacity: .3; }
  50% { opacity: .9; }
}

/* ---------- Reduced motion: static pose, gentle opacity fade only ---------- */
@media (prefers-reduced-motion: reduce) {
  .gl-play .gl-gavel,
  .gl-play .gl-block,
  .gl-play .gl-contact,
  .gl-play .gl-ripple { animation: none; }
  .gl-gavel { transform: rotate(14deg); transition: none; }
  .gl-play .gl-dot { animation: gl-fade 1.8s ease-in-out infinite; transform: none; }
}
`;

const WALNUT = "#573824";
const GOLD = "#B8965A";

export default function GavelLoader({
  message = "Court is in session",
  size = 180,
  playing = true,
  showDots = true,
  className = "",
}) {
  const uid = useId().replace(/:/g, "");
  const id = (n) => `gl-${n}-${uid}`;
  const url = (n) => `url(#${id(n)})`;
  const width = typeof size === "number" ? `${size}px` : size;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy={playing}
      className={`gl-root ${playing ? "gl-play" : ""} inline-flex flex-col items-center justify-center bg-transparent select-none ${className}`}
    >
      <style>{STYLES}</style>

      <svg
        viewBox="0 0 220 190"
        style={{ width }}
        className="h-auto max-w-full overflow-visible"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <radialGradient id={id("top")} cx="50%" cy="42%" r="70%">
            <stop offset="0" stopColor="#7A5233" />
            <stop offset=".55" stopColor="#5E3D27" />
            <stop offset="1" stopColor="#4A2F1D" />
          </radialGradient>
          <linearGradient id={id("side")} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#3A2416" />
            <stop offset=".35" stopColor="#5E3D27" />
            <stop offset=".62" stopColor={WALNUT} />
            <stop offset="1" stopColor="#2E1B10" />
          </linearGradient>
          <linearGradient id={id("foot")} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#2E1B10" />
            <stop offset=".4" stopColor="#4A2F1D" />
            <stop offset="1" stopColor="#24150C" />
          </linearGradient>
          <radialGradient id={id("footTop")} cx="50%" cy="40%" r="75%">
            <stop offset="0" stopColor="#5E3D27" />
            <stop offset="1" stopColor="#3A2416" />
          </radialGradient>
          <linearGradient id={id("handle")} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#7A5233" />
            <stop offset=".5" stopColor={WALNUT} />
            <stop offset="1" stopColor="#3A2416" />
          </linearGradient>
          <linearGradient id={id("head")} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#3A2416" />
            <stop offset=".3" stopColor="#7A5233" />
            <stop offset=".55" stopColor="#5E3D27" />
            <stop offset="1" stopColor="#2E1B10" />
          </linearGradient>
          <linearGradient id={id("gold")} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#8E7140" />
            <stop offset=".45" stopColor="#D9BC82" />
            <stop offset=".75" stopColor={GOLD} />
            <stop offset="1" stopColor="#8E7140" />
          </linearGradient>
          <filter id={id("soft")} x="-20%" y="-100%" width="140%" height="300%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>

        {/* Shift art so the composition sits centred in the viewBox */}
        <g transform="translate(0 -36)">
          {/* Ground shadow */}
          <ellipse cx="110" cy="199" rx="64" ry="7" fill="#2A190E" opacity=".16" filter={url("soft")} />

          {/* Ripples (behind the block, on the surface) */}
          <ellipse className="gl-ripple" cx="110" cy="192" rx="54" ry="9" fill="none" stroke={GOLD} strokeWidth="1.25" vectorEffect="non-scaling-stroke" />
          <ellipse className="gl-ripple gl-ripple-2" cx="110" cy="192" rx="54" ry="9" fill="none" stroke={GOLD} strokeWidth="1" vectorEffect="non-scaling-stroke" />

          {/* ---------- Sound block ---------- */}
          <g className="gl-block">
            {/* foot */}
            <path d="M56,186 V192 A54,9 0 0 0 164,192 V186 Z" fill={url("foot")} />
            <ellipse cx="110" cy="186" rx="54" ry="9" fill={url("footTop")} />
            <ellipse cx="110" cy="186" rx="54" ry="9" fill="none" stroke={GOLD} strokeWidth=".7" opacity=".45" />
            {/* body */}
            <path d="M64,170 V184 A46,8.5 0 0 0 156,184 V170 Z" fill={url("side")} />
            <path d="M64,177 A46,8.5 0 0 0 156,177" fill="none" stroke={url("gold")} strokeWidth="1.4" />
            {/* top face */}
            <ellipse cx="110" cy="170" rx="46" ry="10" fill={url("top")} />
            <ellipse cx="110" cy="170" rx="46" ry="10" fill="none" stroke={GOLD} strokeWidth=".8" opacity=".55" />
            <ellipse cx="110" cy="170" rx="37" ry="7.8" fill="none" stroke={GOLD} strokeWidth=".6" opacity=".4" />
            <ellipse cx="110" cy="170" rx="24" ry="5.2" fill="#2A190E" opacity=".28" />
            {/* subtle grain */}
            <path d="M82,168 C96,165 124,165 138,168" fill="none" stroke="#2A190E" strokeWidth=".6" opacity=".25" />
            <path d="M80,172 C96,175 124,175 140,172" fill="none" stroke="#F8F5EF" strokeWidth=".5" opacity=".08" />
            {/* contact shadow */}
            <ellipse className="gl-contact" cx="110" cy="170.5" rx="22" ry="4.2" fill="#1F120A" />
          </g>

          {/* ---------- Gavel (pivot = end of handle at 188,142) ---------- */}
          <g className="gl-gavel">
            <g transform="translate(188 142)">
              {/* handle */}
              <path d="M14,-3.6 L-30,-3.4 L-66,-5.2 L-66,5.2 L-30,3.4 L14,3.6 Z" fill={url("handle")} />
              <circle cx="14" cy="0" r="4.6" fill={url("handle")} />
              <rect x="3.6" y="-4.6" width="2.2" height="9.2" rx="1" fill={url("gold")} />
              <rect x="-69" y="-6.8" width="5" height="13.6" rx="1.4" fill={url("gold")} />
              <rect x="-40" y="-3.3" width="40" height="1" rx=".5" fill="#F8F5EF" opacity=".12" />

              {/* head */}
              <rect x="-91" y="-28" width="26" height="56" rx="3.5" fill={url("head")} />
              <rect x="-92" y="-28" width="28" height="6.5" rx="2" fill={url("gold")} />
              <rect x="-92" y="21.5" width="28" height="6.5" rx="2" fill={url("gold")} />
              <path d="M-86,-16 C-83,-8 -88,4 -85,16" fill="none" stroke="#2A190E" strokeWidth=".8" opacity=".28" />
              <rect x="-82" y="-18" width="1.6" height="36" rx=".8" fill="#F8F5EF" opacity=".16" />
            </g>
          </g>
        </g>
      </svg>

      <p
        className="mt-5 pl-[0.3em] text-center text-[11px] font-medium uppercase tracking-[0.3em] sm:text-xs"
        style={{ color: WALNUT }}
      >
        {message}
      </p>

      <div
        className={`mt-2.5 flex items-center gap-1.5 transition-opacity duration-500 ${
          showDots && playing ? "opacity-100" : "opacity-0"
        }`}
        aria-hidden="true"
      >
        <span className="gl-dot block h-1 w-1 rounded-full" style={{ background: GOLD }} />
        <span className="gl-dot block h-1 w-1 rounded-full" style={{ background: GOLD }} />
        <span className="gl-dot block h-1 w-1 rounded-full" style={{ background: GOLD }} />
      </div>
    </div>
  );
}