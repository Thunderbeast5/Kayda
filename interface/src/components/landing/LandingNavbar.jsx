import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import logo from "../../assets/12.svg";
import { useAuth } from "../../context/AuthContext";

export default function LandingNavbar({ scrollToSection }) {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState(null);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  const { currentUser, userProfile, signOut } = useAuth();

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY > 50) setIsScrolled(true);
      else setIsScrolled(false);
      if (currentScrollY > lastScrollY && currentScrollY > 100) setIsVisible(false);
      else setIsVisible(true);
      setLastScrollY(currentScrollY);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [lastScrollY]);

  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSignOut = async () => {
    setDropdownOpen(false);
    await signOut();
  };

  const getInitials = () => {
    if (userProfile?.firstName) return `${userProfile.firstName[0]}${userProfile.lastName?.[0] || ""}`.toUpperCase();
    if (currentUser?.displayName) {
      const parts = currentUser.displayName.split(" ");
      return `${parts[0]?.[0] || ""}${parts[1]?.[0] || ""}`.toUpperCase();
    }
    return currentUser?.email?.[0]?.toUpperCase() || "?";
  };

  const displayName = userProfile?.firstName
    ? `${userProfile.firstName} ${userProfile.lastName || ""}`.trim()
    : currentUser?.displayName || currentUser?.email || "User";

  return (
    <div
      className={`fixed inset-x-0 z-50 flex justify-center pointer-events-none transition-all duration-500 ease-in-out ${
        isVisible ? "translate-y-0" : "-translate-y-[150px]"
      } ${isScrolled ? "top-5 px-6" : "top-0 px-0"}`}
    >
      <nav
        className={`pointer-events-auto flex items-center justify-between w-full transition-all duration-500 ease-in-out ${
          isScrolled
            ? "max-w-6xl px-7 py-2 rounded-full bg-[#FAF9F7]/80 backdrop-blur-md border border-[#D4AF37]/30 shadow-[0_10px_30px_rgba(44,24,16,0.08)]"
            : "max-w-full px-8 md:px-16 py-4 bg-transparent border-transparent shadow-none"
        }`}
      >
        {/* Logo */}
        <div
          className="flex items-center cursor-pointer select-none"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <img src={logo} alt="Kayda Logo" className="w-14 h-auto" />
          <span className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-[#2C1810] -ml-[16px] mt-0.5">
            ayda
          </span>
        </div>

        {/* Navigation Links */}
        <div className="hidden md:flex items-center gap-8 text-[13px] font-bold tracking-[0.08em] uppercase text-[#2C1810]/80">
          <button onClick={() => navigate("/mootcourt-modes")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1.5 cursor-pointer">
            Moot Court
          </button>
          <button onClick={() => navigate("/evidence-analyzer")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
            Document Suite
          </button>
          <button onClick={() => navigate("/lexigraph-agent")} className="hover:text-[#8C5A3C] transition-colors cursor-pointer">
            LexiGraph
          </button>
          <button onClick={() => navigate("/multiplayer")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
            Multiplayer
          </button>
          <button
            onClick={() => {
              if (window.location.pathname === "/pricing") scrollToSection("pricing");
              else navigate("/pricing");
            }}
            className="hover:text-[#8C5A3C] transition-colors cursor-pointer"
          >
            Pricing
          </button>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-4">
          {currentUser ? (
            <div ref={dropdownRef} style={{ position: "relative" }}>
              <button
                id="user-avatar-btn"
                onClick={() => setDropdownOpen((o) => !o)}
                style={{
                  display: "flex", alignItems: "center", gap: "8px",
                  background: "none", border: "1.5px solid rgba(212,175,55,0.4)",
                  borderRadius: "100px", padding: "4px 14px 4px 4px",
                  cursor: "pointer", transition: "all 0.2s",
                }}
                className="hover:border-[#D4AF37] hover:shadow-[0_4px_16px_rgba(212,175,55,0.2)]"
              >
                {currentUser.photoURL && failedAvatarUrl !== currentUser.photoURL ? (
                  <img src={currentUser.photoURL} alt="avatar" onError={() => setFailedAvatarUrl(currentUser.photoURL)} style={{ width: "30px", height: "30px", borderRadius: "50%", objectFit: "cover" }} />
                ) : (
                  <div style={{ width: "30px", height: "30px", borderRadius: "50%", background: "linear-gradient(135deg, #2C1810, #8C5A3C)", display: "flex", alignItems: "center", justifyContent: "center", color: "#D4AF37", fontSize: "11px", fontWeight: 700 }}>
                    {getInitials()}
                  </div>
                )}
                <span style={{ fontSize: "13px", fontWeight: 600, color: "#2C1810", maxWidth: "100px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {displayName.split(" ")[0]}
                </span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ color: "#8C5A3C", transition: "transform 0.2s", transform: dropdownOpen ? "rotate(180deg)" : "none" }}>
                  <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>

              {dropdownOpen && (
                <div style={{ position: "absolute", right: 0, top: "calc(100% + 10px)", background: "rgba(255,255,255,0.95)", backdropFilter: "blur(20px)", border: "1px solid rgba(212,175,55,0.25)", borderRadius: "14px", boxShadow: "0 20px 60px rgba(44,24,16,0.12)", minWidth: "200px", padding: "8px", zIndex: 100, animation: "fadeDown 0.2s ease" }}>
                  <div style={{ padding: "10px 12px 12px", borderBottom: "1px solid rgba(212,175,55,0.15)", marginBottom: "6px" }}>
                    <p style={{ margin: 0, fontSize: "13px", fontWeight: 700, color: "#2C1810", fontFamily: "'Manrope', sans-serif" }}>{displayName}</p>
                    <p style={{ margin: "2px 0 0", fontSize: "11px", color: "#8C5A3C", fontFamily: "'Manrope', sans-serif" }}>{currentUser.email}</p>
                  </div>
                  <button
                    id="landing-profile-btn"
                    onClick={() => { setDropdownOpen(false); navigate("/profile"); }}
                    style={{ width: "100%", textAlign: "left", padding: "9px 12px", borderRadius: "8px", background: "none", border: "none", fontFamily: "'Manrope', sans-serif", fontSize: "13px", fontWeight: 600, color: "#2C1810", cursor: "pointer", display: "flex", alignItems: "center", gap: "8px", transition: "background 0.15s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(212,175,55,0.08)"}
                    onMouseLeave={e => e.currentTarget.style.background = "none"}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
                    </svg>
                    My Profile
                  </button>
                  <button
                    id="signout-btn"
                    onClick={handleSignOut}
                    style={{ width: "100%", textAlign: "left", padding: "9px 12px", borderRadius: "8px", background: "none", border: "none", fontFamily: "'Manrope', sans-serif", fontSize: "13px", fontWeight: 600, color: "#C62828", cursor: "pointer", display: "flex", alignItems: "center", gap: "8px", transition: "background 0.15s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(211,47,47,0.07)"}
                    onMouseLeave={e => e.currentTarget.style.background = "none"}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                    </svg>
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <button
                id="navbar-signin-btn"
                onClick={() => navigate("/auth")}
                className="px-6 py-1.5 text-[13px] font-semibold text-[#2C1810] bg-transparent border border-[#2C1810] rounded-full hover:bg-[#2C1810]/5 transition-all duration-300 cursor-pointer"
              >
                Sign in
              </button>
              <button
                id="navbar-launch-btn"
                onClick={() => navigate("/auth")}
                className="px-6 py-1.5 text-[13px] font-semibold text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(212,175,55,0.35)] transition-all duration-300 cursor-pointer"
              >
                Get started
              </button>
            </>
          )}
        </div>
      </nav>

      <style>{`@keyframes fadeDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}