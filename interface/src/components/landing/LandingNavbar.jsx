import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, User, LogOut } from "lucide-react";
import logo from "../../assets/12.svg";
import { useAuth } from "../../context/AuthContext";
import { DEFAULT_AVATAR } from "../../data/avatars";

export default function LandingNavbar({ scrollToSection }) {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef(null);
  const mobileMenuRef = useRef(null);
  const navigate = useNavigate();

  const { currentUser, userProfile, signOut } = useAuth();

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      setIsScrolled(currentScrollY > 40);

      if (currentScrollY > lastScrollY && currentScrollY > 90 && !mobileMenuOpen) {
        setIsVisible(false);
      } else {
        setIsVisible(true);
      }
      setLastScrollY(currentScrollY);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [lastScrollY, mobileMenuOpen]);

  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
      if (
        mobileMenuRef.current &&
        !mobileMenuRef.current.contains(e.target) &&
        !e.target.closest("#mobile-menu-trigger")
      ) {
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Lock body scroll when mobile drawer is open
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  const handleSignOut = async () => {
    setDropdownOpen(false);
    setMobileMenuOpen(false);
    await signOut();
  };

  const navTo = (path, sectionId) => {
    setMobileMenuOpen(false);
    if (sectionId && window.location.pathname === path) {
      scrollToSection?.(sectionId);
    } else {
      navigate(path);
    }
  };

  const displayName = userProfile?.firstName
    ? `${userProfile.firstName} ${userProfile.lastName || ""}`.trim()
    : currentUser?.displayName || currentUser?.email || "User";
  const avatarUrl = userProfile?.avatar || DEFAULT_AVATAR;

  const navLinks = [
    { label: "Moot Court", path: "/mootcourt-modes" },
    { label: "Document Suite", path: "/evidence-analyzer" },
    { label: "LexiGraph", path: "/lexigraph-agent" },
    { label: "Multiplayer", path: "/multiplayer" },
    { label: "Pricing", path: "/pricing", sectionId: "pricing" },
  ];

  return (
    <>
      <header
        className={`fixed inset-x-0 z-50 flex justify-center pointer-events-none transition-all duration-300 ease-in-out ${
          isVisible ? "translate-y-0" : "-translate-y-full"
        } ${isScrolled ? "top-2 sm:top-4 px-3 sm:px-6" : "top-0 px-0"}`}
      >
        <nav
          className={`pointer-events-auto flex items-center justify-between w-full transition-all duration-300 ease-in-out ${
            isScrolled
              ? "max-w-6xl px-3.5 sm:px-6 py-2 rounded-full bg-[#FAF9F7]/90 backdrop-blur-md border border-[#D4AF37]/35 shadow-[0_8px_25px_rgba(44,24,16,0.08)]"
              : "max-w-full px-4 sm:px-8 md:px-12 lg:px-16 py-3 sm:py-4 bg-transparent border-transparent shadow-none"
          }`}
        >
          {/* Logo */}
          <div
            className="flex items-center cursor-pointer select-none shrink-0"
            onClick={() => {
              setMobileMenuOpen(false);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            <img src={logo} alt="Kayda Logo" className="w-11 sm:w-13 md:w-14 h-auto" />
            <span className="font-heading text-xl sm:text-2xl md:text-3xl font-bold tracking-tight text-[#2C1810] -ml-3 sm:-ml-[16px] mt-1">
              ayda
            </span>
          </div>

          {/* Desktop & Laptop Nav Links */}
          <div className="hidden lg:flex items-center gap-6 xl:gap-8 text-[12px] xl:text-[13px] font-bold tracking-[0.08em] uppercase text-[#2C1810]/85">
            {navLinks.map((item) => (
              <button
                key={item.label}
                onClick={() => navTo(item.path, item.sectionId)}
                className="hover:text-[#8C5A3C] transition-colors cursor-pointer"
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* Right Area: Auth & Controls */}
          <div className="flex items-center gap-2 sm:gap-3">
            {currentUser ? (
              <div ref={dropdownRef} className="relative">
                <button
                  id="user-avatar-btn"
                  onClick={() => setDropdownOpen((o) => !o)}
                  className="flex items-center gap-1.5 sm:gap-2 border border-[#D4AF37]/50 rounded-full p-1 pr-2 sm:pr-3 hover:border-[#D4AF37] hover:shadow-[0_2px_12px_rgba(212,175,55,0.25)] transition-all cursor-pointer bg-white/60 touch-manipulation"
                >
                  <img
                    src={avatarUrl}
                    alt="avatar"
                    onError={(e) => {
                      e.currentTarget.src = DEFAULT_AVATAR;
                    }}
                    className="w-6 h-6 sm:w-7 sm:h-7 rounded-full object-cover shrink-0"
                  />
                  <span className="inline-block text-[11px] sm:text-xs font-semibold text-[#2C1810] max-w-[65px] sm:max-w-[120px] truncate">
                    {displayName.split(" ")[0]}
                  </span>
                  <svg
                    width="11"
                    height="11"
                    viewBox="0 0 12 12"
                    fill="none"
                    className={`text-[#8C5A3C] transition-transform duration-200 shrink-0 ${
                      dropdownOpen ? "rotate-180" : ""
                    }`}
                  >
                    <path
                      d="M2 4l4 4 4-4"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>

                {dropdownOpen && (
                  <div className="absolute right-0 top-[calc(100%+8px)] bg-white/95 backdrop-blur-xl border border-[#D4AF37]/30 rounded-xl shadow-[0_16px_40px_rgba(44,24,16,0.12)] min-w-[210px] p-2 z-50 animate-dropdown">
                    <div className="px-3 py-2 border-b border-[#D4AF37]/20 mb-1">
                      <p className="text-xs font-bold text-[#2C1810] truncate">{displayName}</p>
                      <p className="text-[10px] text-[#8C5A3C] truncate">{currentUser.email}</p>
                    </div>
                    <button
                      id="landing-profile-btn"
                      onClick={() => {
                        setDropdownOpen(false);
                        navigate("/profile");
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-[#2C1810] hover:bg-[#D4AF37]/10 flex items-center gap-2 transition-colors cursor-pointer"
                    >
                      <User size={14} />
                      My Profile
                    </button>
                    <button
                      id="signout-btn"
                      onClick={handleSignOut}
                      className="w-full text-left px-3 py-2 rounded-lg text-xs font-semibold text-[#C62828] hover:bg-red-50 flex items-center gap-2 transition-colors cursor-pointer"
                    >
                      <LogOut size={14} />
                      Sign Out
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1.5 sm:gap-2">
                <button
                  id="navbar-signin-btn"
                  onClick={() => navigate("/auth")}
                  className="hidden md:inline-flex px-3.5 sm:px-4 py-1.5 text-[11px] sm:text-xs font-semibold text-[#2C1810] rounded-full border border-[#2C1810] hover:bg-[#2C1810]/5 transition-all cursor-pointer whitespace-nowrap"
                >
                  Sign in
                </button>
                <button
                  id="navbar-launch-btn"
                  onClick={() => navigate("/auth")}
                  className="px-3 sm:px-4 py-1.5 text-[10px] sm:text-xs font-bold uppercase tracking-wider text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] shadow-sm hover:shadow-[0_2px_14px_rgba(212,175,55,0.3)] transition-all cursor-pointer whitespace-nowrap"
                >
                  Get started
                </button>
              </div>
            )}

            {/* Animated Morphing Hamburger Button */}
            <button
              id="mobile-menu-trigger"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
              className="lg:hidden p-2 text-[#2C1810] hover:text-[#8C5A3C] hover:bg-[#2C1810]/5 rounded-lg transition-colors cursor-pointer touch-manipulation shrink-0 flex items-center justify-center w-9 h-9"
            >
              <div className="relative w-5 h-4 flex flex-col justify-between">
                <span
                  className={`h-0.5 w-full bg-current rounded-full transition-all duration-300 ease-in-out origin-center ${
                    mobileMenuOpen ? "translate-y-[7px] rotate-45" : ""
                  }`}
                />
                <span
                  className={`h-0.5 w-full bg-current rounded-full transition-all duration-200 ease-in-out ${
                    mobileMenuOpen ? "opacity-0 scale-x-0" : "opacity-100 scale-x-100"
                  }`}
                />
                <span
                  className={`h-0.5 w-full bg-current rounded-full transition-all duration-300 ease-in-out origin-center ${
                    mobileMenuOpen ? "-translate-y-[7px] -rotate-45" : ""
                  }`}
                />
              </div>
            </button>
          </div>
        </nav>
      </header>

      {/* Backdrop with Fade */}
      <div
        className={`lg:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-xs transition-opacity duration-300 ${
          mobileMenuOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={() => setMobileMenuOpen(false)}
      />

      {/* Animated Dropdown Panel with Elastic Easing */}
      <div
        ref={mobileMenuRef}
        className={`lg:hidden fixed inset-x-3 sm:inset-x-6 top-16 sm:top-20 z-50 bg-[#FAF9F7]/95 backdrop-blur-xl border border-[#D4AF37]/35 rounded-2xl shadow-[0_20px_50px_rgba(44,24,16,0.18)] p-5 transition-all duration-300 origin-top ${
          mobileMenuOpen
            ? "opacity-100 scale-100 translate-y-0 pointer-events-auto"
            : "opacity-0 scale-95 -translate-y-3 pointer-events-none"
        }`}
        style={{
          transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        <div className="flex flex-col gap-1.5">
          {navLinks.map((item, index) => (
            <button
              key={item.label}
              onClick={() => navTo(item.path, item.sectionId)}
              style={{
                transitionDelay: mobileMenuOpen ? `${index * 45}ms` : "0ms",
              }}
              className={`group flex items-center justify-between w-full px-3 py-2.5 rounded-lg text-sm font-bold tracking-wide uppercase text-[#2C1810] hover:bg-[#D4AF37]/10 transition-all duration-200 text-left ${
                mobileMenuOpen ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-2"
              }`}
            >
              <span>{item.label}</span>
              <ArrowRight
                size={14}
                className="text-[#8C5A3C] transition-transform duration-200 group-hover:translate-x-1"
              />
            </button>
          ))}

          {!currentUser && (
            <div
              style={{
                transitionDelay: mobileMenuOpen ? `${navLinks.length * 45}ms` : "0ms",
              }}
              className={`pt-3 mt-1 border-t border-[#D4AF37]/25 flex flex-col gap-2 transition-all duration-200 ${
                mobileMenuOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
              }`}
            >
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  navigate("/auth");
                }}
                className="w-full py-2.5 text-center text-xs font-bold uppercase tracking-wider text-[#2C1810] border border-[#2C1810]/40 rounded-xl hover:bg-[#2C1810]/5 transition-colors"
              >
                Sign In
              </button>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes dropdownFade {
          from { opacity: 0; transform: translateY(-6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-dropdown {
          animation: dropdownFade 0.18s ease-out forwards;
        }
      `}</style>
    </>
  );
}