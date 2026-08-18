import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { updatePlayerProfile, uploadAvatar } from "../api/playerApi";
import StandardNavbar from "../components/StandardNavbar";

// ─── Role Config ──────────────────────────────────────────────────────────────
const ROLES = [
  { key: "defense", label: "Defense", icon: "🛡️" },
  { key: "prosecutor", label: "Prosecutor", icon: "⚖️" },
  { key: "judge", label: "Judge", icon: "🏛️" },
];

// ─── Animated Counter Hook ────────────────────────────────────────────────────
function useAnimatedCount(target, duration = 900) {
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

// ─── Win Rate Ring ────────────────────────────────────────────────────────────
function WinRateRing({ wins, losses, draws }) {
  const total = wins + losses + draws;
  const winPct = total > 0 ? Math.round((wins / total) * 100) : 0;
  const lossPct = total > 0 ? Math.round((losses / total) * 100) : 0;
  const drawPct = total > 0 ? 100 - winPct - lossPct : 0;

  const r = 52, circumference = 2 * Math.PI * r;
  const winArc = (winPct / 100) * circumference;
  const lossArc = (lossPct / 100) * circumference;
  const drawArc = (drawPct / 100) * circumference;

  return (
    <div className="flex flex-col sm:flex-row items-center gap-8 mt-5 p-7 bg-white/70 backdrop-blur-md border border-[#D4AF37]/15 rounded-[20px]">
      {/* Ring */}
      <div className="relative flex-shrink-0">
        <svg width="130" height="130" className="-rotate-90">
          <circle cx="65" cy="65" r={r} fill="none" stroke="rgba(44,24,16,0.06)" strokeWidth="9" />
          {total > 0 && (
            <>
              <circle cx="65" cy="65" r={r} fill="none" stroke="#4CAF50" strokeWidth="9" strokeLinecap="round"
                strokeDasharray={`${winArc} ${circumference - winArc}`} strokeDashoffset="0"
                style={{ transition: "stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
              <circle cx="65" cy="65" r={r} fill="none" stroke="#E53935" strokeWidth="9" strokeLinecap="round"
                strokeDasharray={`${lossArc} ${circumference - lossArc}`} strokeDashoffset={`${-winArc}`}
                style={{ transition: "stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
              <circle cx="65" cy="65" r={r} fill="none" stroke="#FF9800" strokeWidth="9" strokeLinecap="round"
                strokeDasharray={`${drawArc} ${circumference - drawArc}`} strokeDashoffset={`${-(winArc + lossArc)}`}
                style={{ transition: "stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
            </>
          )}
        </svg>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
          <span className="font-heading text-[28px] font-bold text-[#2C1810] leading-none">{winPct}%</span>
          <p className="text-[9px] font-semibold text-[#8C5A3C] uppercase tracking-[0.1em] mt-0.5">Win Rate</p>
        </div>
      </div>

      {/* Breakdown bars */}
      <div className="flex-1 flex flex-col gap-3 w-full">
        {[
          { label: "Wins", value: wins, total, color: "bg-gradient-to-r from-[#4CAF50] to-[#66BB6A]" },
          { label: "Losses", value: losses, total, color: "bg-gradient-to-r from-[#E53935] to-[#EF5350]" },
          { label: "Draws", value: draws, total, color: "bg-gradient-to-r from-[#FF9800] to-[#FFB74D]" },
        ].map(({ label, value, total: t, color }) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-xs font-semibold text-[#5D4037] min-w-[55px]">{label}</span>
            <div className="flex-1 h-2 bg-[#2C1810]/5 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${color}`}
                style={{ width: t > 0 ? `${(value / t) * 100}%` : "0%", transition: "width 1s cubic-bezier(0.4,0,0.2,1)" }} />
            </div>
            <span className="text-xs font-bold text-[#2C1810] min-w-[24px] text-right">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ icon, value, label, iconBg, iconColor, accentColor }) {
  const animatedValue = useAnimatedCount(value);
  return (
    <div className="group bg-white/80 backdrop-blur-md border border-[#D4AF37]/15 rounded-2xl p-6 text-center transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_12px_40px_rgba(44,24,16,0.08)] hover:border-[#D4AF37]/35 relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-[3px] opacity-0 group-hover:opacity-100 transition-opacity duration-300`} style={{ background: accentColor }} />
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-3 text-lg`} style={{ background: iconBg, color: iconColor }}>
        {icon}
      </div>
      <div className="font-heading text-[32px] font-bold text-[#2C1810] leading-none mb-1">{animatedValue}</div>
      <div className="text-[11px] font-semibold text-[#8C5A3C] uppercase tracking-[0.08em]">{label}</div>
    </div>
  );
}

// ─── Main Profile Page ────────────────────────────────────────────────────────
export default function ProfilePage() {
  const navigate = useNavigate();
  const { currentUser, userProfile, refreshProfile } = useAuth();
  const fileInputRef = useRef(null);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState("defense");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [dirty, setDirty] = useState(false);

  // Sync form state when profile loads
  useEffect(() => {
    if (userProfile) {
      setEditName(userProfile.display_name || userProfile.displayName || "");
      setEditRole(userProfile.preferred_role || "defense");
    }
  }, [userProfile]);

  if (!currentUser || !userProfile) return null;

  const profile = userProfile;
  const memberSince = profile.createdAt?.toDate
    ? profile.createdAt.toDate().toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : "—";

  const getInitials = () => {
    if (profile.firstName) return `${profile.firstName[0]}${profile.lastName?.[0] || ""}`.toUpperCase();
    if (profile.display_name) {
      const parts = profile.display_name.split(" ");
      return `${parts[0]?.[0] || ""}${parts[1]?.[0] || ""}`.toUpperCase();
    }
    return profile.email?.[0]?.toUpperCase() || "?";
  };

  const avatarUrl = profile.avatar || profile.photoURL || null;

  // ── Handlers ──
  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadAvatar(currentUser.uid, file);
      await refreshProfile();
      showToast("Avatar updated!");
    } catch (err) {
      console.error("Avatar upload failed:", err);
      showToast("Upload failed — try again");
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
      showToast("Profile saved!");
    } catch (err) {
      console.error("Save failed:", err);
      showToast("Save failed — try again");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditName(profile.display_name || profile.displayName || "");
    setEditRole(profile.preferred_role || "defense");
    setDirty(false);
  };

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2800);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#FAF9F7] to-[#F5F0EB] font-body">
      <StandardNavbar />

      <div className="max-w-[900px] mx-auto px-6 pt-10 pb-20">

        {/* ── Hero Card ── */}
        <div className="relative bg-white/75 backdrop-blur-[24px] border border-[#D4AF37]/20 rounded-3xl p-10 sm:p-12 shadow-[0_4px_40px_rgba(44,24,16,0.06)] overflow-hidden">
          {/* Gold accent bar */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-[#D4AF37] via-[#8C5A3C] to-[#D4AF37]" />

          <div className="flex flex-col sm:flex-row items-center gap-8">
            {/* Avatar */}
            <div className="relative flex-shrink-0">
              {avatarUrl ? (
                <img src={avatarUrl} alt="avatar"
                  className="w-[110px] h-[110px] rounded-full object-cover border-[3px] border-[#D4AF37]/40 shadow-[0_8px_32px_rgba(44,24,16,0.12)] transition-transform duration-300 hover:scale-[1.04]" />
              ) : (
                <div className="w-[110px] h-[110px] rounded-full bg-gradient-to-br from-[#2C1810] to-[#8C5A3C] flex items-center justify-center text-[#D4AF37] text-4xl font-bold border-[3px] border-[#D4AF37]/40 shadow-[0_8px_32px_rgba(44,24,16,0.12)] transition-transform duration-300 hover:scale-[1.04]">
                  {getInitials()}
                </div>
              )}
              {/* Upload button */}
              <button
                id="profile-avatar-upload"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="absolute bottom-1 right-1 w-[34px] h-[34px] rounded-full bg-gradient-to-br from-[#2C1810] to-[#3E2723] border-2 border-[#D4AF37] flex items-center justify-center cursor-pointer transition-all duration-200 hover:scale-110 hover:from-[#3E2723] hover:to-[#5D4037] shadow-[0_4px_12px_rgba(0,0,0,0.2)] disabled:opacity-50"
              >
                {uploading ? (
                  <div className="w-3.5 h-3.5 border-2 border-[#D4AF37] border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#D4AF37" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                )}
              </button>
              <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarUpload} />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0 text-center sm:text-left">
              <h1 className="font-heading text-[32px] sm:text-[36px] font-bold text-[#2C1810] leading-tight mb-1">
                {profile.display_name || profile.displayName || "Player"}
              </h1>
              <p className="text-[13px] text-[#8C5A3C] tracking-[0.02em] mb-3">{profile.email}</p>

              <div className="flex items-center gap-2.5 flex-wrap justify-center sm:justify-start">
                {/* Rating badge */}
                <span className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-[0.06em] bg-gradient-to-r from-[#D4AF37]/15 to-[#D4AF37]/8 text-[#8C6D1F] border border-[#D4AF37]/35">
                  ⭐ {profile.rating || 1200} ELO
                </span>
                {/* Role badge */}
                <span className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-[0.06em] bg-[#2C1810]/[0.06] text-[#5D4037] border border-[#2C1810]/12">
                  {ROLES.find(r => r.key === (profile.preferred_role || "defense"))?.icon} {profile.preferred_role || "defense"}
                </span>
                {/* Member since badge */}
                <span className="inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-[0.06em] bg-[#8C5A3C]/[0.06] text-[#8C5A3C] border border-[#8C5A3C]/15">
                  📅 Since {memberSince}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Stats Section ── */}
        <h2 className="font-heading text-[22px] font-bold text-[#2C1810] mt-10 mb-5 flex items-center gap-3 after:content-[''] after:flex-1 after:h-px after:bg-gradient-to-r after:from-[#D4AF37]/40 after:to-transparent">
          Performance
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          <StatCard icon="⭐" value={profile.rating || 1200} label="Rating"
            iconBg="rgba(212,175,55,0.12)" iconColor="#D4AF37" accentColor="linear-gradient(90deg,#D4AF37,#E6C65A)" />
          <StatCard icon="🎮" value={profile.games_played || 0} label="Games"
            iconBg="rgba(93,64,55,0.1)" iconColor="#5D4037" accentColor="linear-gradient(90deg,#5D4037,#8C5A3C)" />
          <StatCard icon="🏆" value={profile.wins || 0} label="Wins"
            iconBg="rgba(76,175,80,0.1)" iconColor="#4CAF50" accentColor="linear-gradient(90deg,#4CAF50,#66BB6A)" />
          <StatCard icon="💔" value={profile.losses || 0} label="Losses"
            iconBg="rgba(229,57,53,0.1)" iconColor="#E53935" accentColor="linear-gradient(90deg,#E53935,#EF5350)" />
          <StatCard icon="🤝" value={profile.draws || 0} label="Draws"
            iconBg="rgba(255,152,0,0.1)" iconColor="#FF9800" accentColor="linear-gradient(90deg,#FF9800,#FFB74D)" />
        </div>

        {/* Win Rate Ring */}
        <WinRateRing wins={profile.wins || 0} losses={profile.losses || 0} draws={profile.draws || 0} />

        {/* ── Edit Profile ── */}
        <h2 className="font-heading text-[22px] font-bold text-[#2C1810] mt-10 mb-5 flex items-center gap-3 after:content-[''] after:flex-1 after:h-px after:bg-gradient-to-r after:from-[#D4AF37]/40 after:to-transparent">
          Edit Profile
        </h2>

        <div className="bg-white/75 backdrop-blur-[20px] border border-[#D4AF37]/15 rounded-[20px] p-8">
          <div className="flex flex-col gap-6">
            {/* Display Name */}
            <div className="flex flex-col gap-2">
              <label htmlFor="profile-display-name" className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#6B4C3B]">
                Display Name
              </label>
              <input
                id="profile-display-name"
                type="text"
                value={editName}
                onChange={(e) => { setEditName(e.target.value); setDirty(true); }}
                placeholder="Enter your display name"
                className="w-full py-3 px-4 text-sm font-body text-[#2C1810] bg-[#2C1810]/[0.02] border-[1.5px] border-[#D4AF37]/30 rounded-xl outline-none transition-all duration-200 focus:border-[#D4AF37] focus:ring-[3px] focus:ring-[#D4AF37]/12 placeholder:text-[#6B4C3B]/40"
              />
            </div>

            {/* Preferred Role */}
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#6B4C3B]">
                Preferred Role
              </span>
              <div className="flex gap-3 flex-wrap">
                {ROLES.map(({ key, label, icon }) => (
                  <button
                    key={key}
                    id={`profile-role-${key}`}
                    onClick={() => { setEditRole(key); setDirty(true); }}
                    className={`flex-1 min-w-[120px] py-3.5 px-4 border-[1.5px] rounded-[14px] cursor-pointer transition-all duration-250 text-center
                      ${editRole === key
                        ? "border-[#D4AF37] bg-gradient-to-br from-[#D4AF37]/10 to-[#D4AF37]/[0.04] shadow-[0_4px_20px_rgba(212,175,55,0.15)]"
                        : "border-[#D4AF37]/25 bg-white/60 hover:border-[#D4AF37]/50 hover:bg-[#D4AF37]/[0.04] hover:-translate-y-0.5"
                      }`}
                  >
                    <div className="text-2xl mb-1">{icon}</div>
                    <div className="text-xs font-bold uppercase tracking-[0.06em] text-[#2C1810]">{label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 justify-end mt-2">
              {dirty && (
                <button
                  id="profile-cancel-btn"
                  onClick={handleCancel}
                  className="px-7 py-2.5 rounded-full text-xs font-bold uppercase tracking-[0.06em] cursor-pointer transition-all duration-250 bg-transparent text-[#5D4037] border-[1.5px] border-[#5D4037]/25 hover:bg-[#5D4037]/5 hover:border-[#5D4037]/40 font-body"
                >
                  Cancel
                </button>
              )}
              <button
                id="profile-save-btn"
                onClick={handleSave}
                disabled={saving || !dirty}
                className="px-7 py-2.5 rounded-full text-xs font-bold uppercase tracking-[0.06em] cursor-pointer transition-all duration-250 bg-gradient-to-br from-[#2C1810] to-[#3E2723] text-[#FAF9F7] border border-[#D4AF37] shadow-[0_4px_16px_rgba(44,24,16,0.2)] hover:-translate-y-0.5 hover:shadow-[0_8px_28px_rgba(212,175,55,0.3)] hover:from-[#3E2723] hover:to-[#5D4037] disabled:opacity-50 disabled:cursor-not-allowed disabled:translate-y-0 font-body"
              >
                {saving ? (
                  <span className="flex items-center gap-2">
                    <div className="w-3.5 h-3.5 border-2 border-[#D4AF37] border-t-transparent rounded-full animate-spin" />
                    Saving…
                  </span>
                ) : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div className="fixed bottom-8 right-8 py-3.5 px-6 bg-gradient-to-br from-[#2C1810] to-[#3E2723] text-[#D4AF37] border border-[#D4AF37]/40 rounded-[14px] text-[13px] font-semibold font-body shadow-[0_12px_40px_rgba(44,24,16,0.25)] flex items-center gap-2.5 z-[1000] animate-[toastSlide_0.4s_cubic-bezier(0.4,0,0.2,1)]">
          ✓ {toast}
        </div>
      )}

      <style>{`@keyframes toastSlide { from { opacity: 0; transform: translateY(20px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }`}</style>
    </div>
  );
}
