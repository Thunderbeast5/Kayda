import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { updatePlayerProfile, uploadAvatar, getPlayerProfile } from "../api/playerApi";
import StandardNavbar from "../components/StandardNavbar";

// ─── Precision Legal Icons ───────────────────────────────────────────────────
const Icons = {
  Defense: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  Prosecutor: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  ),
  Judge: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m14 13-7.5 7.5c-.83.83-2.17.83-3 0 0 0 0 0 0 0a2.12 2.12 0 0 1 0-3L11 10" />
      <path d="m16 16 6-6" />
      <path d="m8 8 6-6" />
      <path d="m9 7 8 8" />
      <path d="m21 11-8-8" />
    </svg>
  ),
  Rating: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  ),
  Docket: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  Victory: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
      <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
      <path d="M4 22h16" />
      <path d="M10 14.66V17c0 .55-.45 1-1 1H7" />
      <path d="M14 14.66V17c0 .55.45 1 1 1h2" />
      <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
    </svg>
  ),
  Defeat: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
  Draw: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="8" y1="12" x2="16" y2="12" />
    </svg>
  ),
  Camera: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  ),
  Check: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
};

const ROLES = [
  { key: "defense", label: "Defense Counsel", Icon: Icons.Defense, code: "DEF" },
  { key: "prosecutor", label: "State Prosecutor", Icon: Icons.Prosecutor, code: "PRS" },
  { key: "judge", label: "Presiding Judge", Icon: Icons.Judge, code: "MAG" },
];

function useAnimatedCount(target, duration = 700) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (target === 0) { setCount(0); return; }
    let start = 0;
    const step = Math.max(1, Math.ceil(target / (duration / 16)));
    const timer = setInterval(() => {
      start += step;
      if (start >= target) { setCount(target); clearInterval(timer); }
      else setCount(start);
    }, 16);
    return () => clearInterval(timer);
  }, [target, duration]);
  return count;
}

// ─── Proportional Outcomes (Large Version) ──────────────────────────────────
function ProportionalOutcomesLarge({ wins, losses, draws }) {
  const total = wins + losses + draws;
  const winPct = total > 0 ? Math.round((wins / total) * 100) : 0;
  const lossPct = total > 0 ? Math.round((losses / total) * 100) : 0;
  const drawPct = total > 0 ? Math.max(0, 100 - winPct - lossPct) : 0;

  const r = 56;
  const circumference = 2 * Math.PI * r;
  const winArc = (winPct / 100) * circumference;
  const lossArc = (lossPct / 100) * circumference;
  const drawArc = (drawPct / 100) * circumference;

  return (
    <div className="bg-white/85 backdrop-blur-xl border border-[#D4AF37]/25 rounded-2xl p-6 shadow-sm flex flex-col justify-between flex-1">
      <div className="flex items-center justify-between pb-3 border-b border-[#D4AF37]/15">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#8C5A3C] font-semibold">
          Proportional Outcomes
        </span>
        <span className="font-mono text-[9px] text-[#C5A059] uppercase tracking-wider font-bold">
          Precedent Distribution
        </span>
      </div>

      <div className="flex flex-col sm:flex-row items-center gap-8 py-4">
        {/* Large Radial Arc Ring */}
        <div className="relative flex-shrink-0">
          <svg width="144" height="144" className="-rotate-90">
            <circle cx="72" cy="72" r={r} fill="none" stroke="rgba(44,24,16,0.06)" strokeWidth="9" />
            {total > 0 && (
              <>
                <circle
                  cx="72"
                  cy="72"
                  r={r}
                  fill="none"
                  stroke="#4CAF50"
                  strokeWidth="9"
                  strokeLinecap="round"
                  strokeDasharray={`${winArc} ${circumference}`}
                  strokeDashoffset="0"
                />
                <circle
                  cx="72"
                  cy="72"
                  r={r}
                  fill="none"
                  stroke="#E53935"
                  strokeWidth="9"
                  strokeLinecap="round"
                  strokeDasharray={`${lossArc} ${circumference}`}
                  strokeDashoffset={`${-winArc}`}
                />
                <circle
                  cx="72"
                  cy="72"
                  r={r}
                  fill="none"
                  stroke="#FF9800"
                  strokeWidth="9"
                  strokeLinecap="round"
                  strokeDasharray={`${drawArc} ${circumference}`}
                  strokeDashoffset={`${-(winArc + lossArc)}`}
                />
              </>
            )}
          </svg>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
            <span className="font-heading text-3xl font-bold text-[#2C1810] block leading-none">{winPct}%</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#8C5A3C] font-semibold mt-1 block">
              Win Rate
            </span>
          </div>
        </div>

        {/* Larger Visual Metric Bars */}
        <div className="flex-1 w-full flex flex-col justify-center gap-4">
          {[
            { label: "Verdicts Won", val: wins, pct: winPct, color: "from-[#4CAF50] to-[#2E7D32]", bg: "bg-[#4CAF50]/15", dot: "bg-[#4CAF50]" },
            { label: "Lost Appeals", val: losses, pct: lossPct, color: "from-[#E53935] to-[#C62828]", bg: "bg-[#E53935]/15", dot: "bg-[#E53935]" },
            { label: "Adjourned / Draw", val: draws, pct: drawPct, color: "from-[#FF9800] to-[#EF6C00]", bg: "bg-[#FF9800]/15", dot: "bg-[#FF9800]" },
          ].map((item) => (
            <div key={item.label} className="w-full">
              <div className="flex justify-between items-center text-xs font-mono mb-1.5 text-[#5D4037]">
                <span className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${item.dot}`} />
                  <span className="font-medium">{item.label}</span>
                </span>
                <span className="font-bold text-[#2C1810]">
                  {item.val} <span className="font-normal text-[#8C5A3C]/70">({item.pct}%)</span>
                </span>
              </div>
              <div className={`h-2.5 w-full rounded-full ${item.bg} overflow-hidden p-[1px]`}>
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${item.color} transition-all duration-700 ease-out`}
                  style={{ width: total > 0 ? `${(item.val / total) * 100}%` : "0%" }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="pt-3 border-t border-[#D4AF37]/15 flex items-center justify-between font-mono text-[10px] text-[#8C5A3C]">
        <span>Total Proceedings: <strong className="text-[#2C1810]">{total}</strong></span>
        <span>Adjudication Metric Active</span>
      </div>
    </div>
  );
}

// ─── Stat Card Component ─────────────────────────────────────────────────────
function LargeStatCard({ icon, value, label, subtext, accent, className = "" }) {
  const animatedValue = useAnimatedCount(value);
  return (
    <div className={`bg-white/85 backdrop-blur-md border border-[#D4AF37]/25 rounded-xl p-4 md:p-5 flex flex-col justify-between hover:border-[#D4AF37]/60 transition-all shadow-sm ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[#8C5A3C] font-semibold">{label}</span>
        <span className="p-1.5 rounded-lg bg-[#2C1810]/[0.03] text-[#5D4037]">{icon}</span>
      </div>
      <div className="mt-1 flex items-baseline justify-between">
        <div className="font-heading text-2xl md:text-3xl font-bold text-[#2C1810]" style={{ borderLeft: `3px solid ${accent}`, paddingLeft: "8px" }}>
          {animatedValue}
        </div>
        {subtext && (
          <span className="font-mono text-[10px] text-[#8C5A3C]/70 uppercase tracking-widest">{subtext}</span>
        )}
      </div>
    </div>
  );
}

// ─── Main Profile Page Component ─────────────────────────────────────────────
export default function ProfilePage() {
  const navigate = useNavigate();
  const { userId } = useParams();
  const { currentUser, userProfile, refreshProfile, loading: authLoading } = useAuth();
  const fileInputRef = useRef(null);

  const isOwnProfile = !userId || userId === currentUser?.uid;

  const [otherProfile, setOtherProfile] = useState(null);
  const [loadingOther, setLoadingOther] = useState(false);
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState("defense");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState(null);

  useEffect(() => {
    if (!isOwnProfile && userId) {
      setLoadingOther(true);
      getPlayerProfile(userId)
        .then((p) => setOtherProfile(p))
        .catch(() => setOtherProfile(null))
        .finally(() => setLoadingOther(false));
    }
  }, [userId, isOwnProfile]);

  const profile = isOwnProfile ? userProfile : otherProfile;
  const avatarUrl = profile?.avatar || profile?.photoURL || null;

  useEffect(() => {
    if (isOwnProfile && userProfile) {
      setEditName(userProfile.display_name || userProfile.displayName || "");
      setEditRole(userProfile.preferred_role || "defense");
    }
  }, [userProfile, isOwnProfile]);

  const getInitials = () => {
    if (profile?.firstName) return `${profile.firstName[0]}${profile.lastName?.[0] || ""}`.toUpperCase();
    if (profile?.display_name) {
      const parts = profile.display_name.split(" ");
      return `${parts[0]?.[0] || ""}${parts[1]?.[0] || ""}`.toUpperCase();
    }
    return profile?.email?.[0]?.toUpperCase() || "J";
  };

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadAvatar(currentUser.uid, file);
      await refreshProfile();
      showToast("Seal updated");
    } catch {
      showToast("Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updatePlayerProfile(currentUser.uid, {
        display_name: editName.trim(),
        preferred_role: editRole,
      });
      await refreshProfile();
      setDirty(false);
      showToast("Dossier modified");
    } catch {
      showToast("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditName(profile?.display_name || profile?.displayName || "");
    setEditRole(profile?.preferred_role || "defense");
    setDirty(false);
  };

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  if (authLoading || (isOwnProfile && !currentUser) || (!isOwnProfile && loadingOther)) {
    return (
      <div className="h-screen w-screen bg-[#FAF9F7] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#D4AF37]/30 border-t-[#2C1810] rounded-full animate-spin" />
      </div>
    );
  }

  const currentRoleConfig = ROLES.find((r) => r.key === (profile?.preferred_role || "defense")) || ROLES[0];

  return (
    <div className="h-screen w-screen bg-gradient-to-b from-[#FAF9F7] via-[#F6F2EC] to-[#EFEAE2] font-body text-[#2C1810] flex flex-col overflow-hidden">
      <StandardNavbar />

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 flex flex-col justify-center min-h-0">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch h-full max-h-[880px]">
          
          {/* ── Left Column: Identity & Record Details ── */}
          <div className="lg:col-span-5 flex flex-col gap-4 justify-between h-full">
            
            {/* Identity Card */}
            <div className="bg-white/85 backdrop-blur-xl border border-[#D4AF37]/25 rounded-2xl p-5 shadow-sm relative overflow-hidden flex-shrink-0">
              <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-[#2C1810] via-[#D4AF37] to-[#2C1810]" />
              
              <div className="flex items-center gap-4">
                <div className="relative flex-shrink-0">
                  <div className="w-20 h-20 rounded-full border border-[#D4AF37]/40 p-1 bg-white shadow-sm">
                    {avatarUrl && failedAvatarUrl !== avatarUrl ? (
                      <img
                        src={avatarUrl}
                        alt="Counsel Seal"
                        onError={() => setFailedAvatarUrl(avatarUrl)}
                        className="w-full h-full rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full rounded-full bg-gradient-to-br from-[#2C1810] to-[#4A2D20] text-[#D4AF37] flex items-center justify-center font-heading font-bold text-2xl">
                        {getInitials()}
                      </div>
                    )}
                  </div>

                  {isOwnProfile && (
                    <>
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-[#2C1810] text-[#D4AF37] border border-[#D4AF37]/50 flex items-center justify-center cursor-pointer shadow hover:scale-105 transition-transform"
                      >
                        {uploading ? (
                          <div className="w-3 h-3 border border-[#D4AF37] border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <Icons.Camera />
                        )}
                      </button>
                      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarUpload} />
                    </>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-[9px] uppercase tracking-widest px-2.5 py-0.5 rounded border border-[#D4AF37]/35 bg-[#D4AF37]/8 text-[#8C6D1F] font-bold">
                      {currentRoleConfig.code}
                    </span>
                    <span className="font-mono text-[10px] text-[#8C5A3C]">RECORD VERIFIED</span>
                  </div>
                  <h1 className="font-heading text-2xl font-bold truncate text-[#2C1810]">
                    {profile?.display_name || profile?.displayName || "Advocate"}
                  </h1>
                  <p className="font-mono text-xs text-[#8C5A3C] truncate">
                    {isOwnProfile ? profile?.email : "Accredited Legal Advocate"}
                  </p>
                </div>
              </div>
            </div>

            {/* Dossier Configurator (Own Profile) or Bio */}
            {isOwnProfile ? (
              <div className="flex-1 bg-white/85 backdrop-blur-xl border border-[#D4AF37]/25 rounded-2xl p-5 md:p-6 flex flex-col justify-between shadow-sm min-h-0">
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#8C5A3C] font-semibold">Dossier Revision</span>
                    {dirty && <span className="font-mono text-[9px] text-[#D4AF37] uppercase tracking-wider font-bold">Unsaved Changes</span>}
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label htmlFor="dossier-name" className="block font-mono text-[10px] uppercase tracking-wider text-[#8C5A3C] mb-1.5 font-medium">
                        Representation Handle
                      </label>
                      <input
                        id="dossier-name"
                        type="text"
                        value={editName}
                        onChange={(e) => { setEditName(e.target.value); setDirty(true); }}
                        placeholder="Formal Counsel Name"
                        className="w-full px-3.5 py-2.5 text-sm font-body bg-[#FAF8F5] text-[#2C1810] border border-[#D4AF37]/30 rounded-xl outline-none focus:border-[#C5A059] focus:ring-2 focus:ring-[#D4AF37]/10"
                      />
                    </div>

                    <div>
                      <span className="block font-mono text-[10px] uppercase tracking-wider text-[#8C5A3C] mb-2 font-medium">
                        Procedural Specialization
                      </span>
                      <div className="grid grid-cols-3 gap-2.5">
                        {ROLES.map(({ key, label, Icon }) => {
                          const isSelected = editRole === key;
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={() => { setEditRole(key); setDirty(true); }}
                              className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between h-20 ${
                                isSelected
                                  ? "bg-[#2C1810] border-[#D4AF37] text-[#FAF9F7] shadow-md"
                                  : "bg-[#FAF8F5]/70 border-[#D4AF37]/25 text-[#2C1810] hover:border-[#D4AF37]/60 hover:bg-[#FAF8F5]"
                              }`}
                            >
                              <div className={`p-1.5 w-fit rounded-lg ${isSelected ? "bg-white/10 text-[#D4AF37]" : "bg-[#2C1810]/5 text-[#5D4037]"}`}>
                                <Icon />
                              </div>
                              <span className="font-mono text-[10px] font-semibold uppercase truncate">
                                {label}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#D4AF37]/15">
                  {dirty && (
                    <button
                      type="button"
                      onClick={handleCancel}
                      className="px-5 py-2 rounded-full text-xs font-mono uppercase tracking-wider text-[#8C5A3C] hover:text-[#2C1810] transition-colors"
                    >
                      Reset
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving || !dirty}
                    className="px-6 py-2.5 rounded-full text-xs font-mono uppercase tracking-[0.15em] bg-[#2C1810] text-[#D4AF37] border border-[#D4AF37]/50 disabled:opacity-40 cursor-pointer hover:bg-[#3E2723] transition-all shadow-sm"
                  >
                    {saving ? "Affixing..." : "Affix Record"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-1 bg-white/70 border border-[#D4AF37]/20 rounded-2xl p-6 flex items-center justify-center text-center">
                <p className="font-mono text-xs text-[#8C5A3C]">Observing accredited court transcript</p>
              </div>
            )}
          </div>

          {/* ── Right Column: 2-Row Judicial Standing & Large Outcomes ── */}
          <div className="lg:col-span-7 flex flex-col justify-between gap-5 h-full">
            
            {/* Top Section: Judicial Standing in 2 Organized Rows */}
            <div>
              <div className="flex justify-between items-center mb-3">
                <h2 className="font-heading text-xl font-bold text-[#2C1810] tracking-tight">Judicial Standing</h2>
                <span className="font-mono text-[10px] uppercase tracking-widest text-[#8C5A3C]">Dossier Ledger</span>
              </div>
              
              <div className="space-y-3">
                {/* Row 1: Primary Metrics (Rating & Case Proceedings) */}
                <div className="grid grid-cols-2 gap-3">
                  <LargeStatCard
                    icon={<Icons.Rating />}
                    value={profile?.rating || 1200}
                    label="Official Elo Rating"
                    subtext="Benchmark"
                    accent="#D4AF37"
                  />
                  <LargeStatCard
                    icon={<Icons.Docket />}
                    value={profile?.games_played || 0}
                    label="Procedural Cases"
                    subtext="Total Dockets"
                    accent="#5D4037"
                  />
                </div>

                {/* Row 2: Secondary Outcome Metrics (Won, Lost, Adjourned) */}
                <div className="grid grid-cols-3 gap-3">
                  <LargeStatCard
                    icon={<Icons.Victory />}
                    value={profile?.wins || 0}
                    label="Won Precedents"
                    accent="#4CAF50"
                  />
                  <LargeStatCard
                    icon={<Icons.Defeat />}
                    value={profile?.losses || 0}
                    label="Overruled"
                    accent="#E53935"
                  />
                  <LargeStatCard
                    icon={<Icons.Draw />}
                    value={profile?.draws || 0}
                    label="Adjourned"
                    accent="#FF9800"
                  />
                </div>
              </div>
            </div>

            {/* Bottom Section: Substantial Proportional Outcomes Box */}
            <ProportionalOutcomesLarge
              wins={profile?.wins || 0}
              losses={profile?.losses || 0}
              draws={profile?.draws || 0}
            />

            {/* Footer Regulatory Ledger */}
            <div className="px-4 py-2.5 bg-white/60 border border-[#D4AF37]/20 rounded-xl flex items-center justify-between text-[#8C5A3C] font-mono text-[10px] uppercase tracking-wider">
              <span>Simulated High Court Jurisdiction</span>
              <span className="text-[#2C1810] font-semibold">Active Docket Protocol</span>
            </div>

          </div>

        </div>
      </main>

      {/* Floating Status Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 py-3 px-5 bg-[#2C1810] text-[#D4AF37] border border-[#D4AF37]/40 rounded-xl text-xs font-mono uppercase tracking-wider shadow-xl flex items-center gap-2.5 z-50">
          <Icons.Check />
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
}