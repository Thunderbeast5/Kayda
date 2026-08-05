// // import logo from "../../assets/13.svg";

// // export default function LandingNavbar({ scrollToSection }) {
// //   return (
// //     <div className="fixed top-5 inset-x-0 z-50 flex justify-center px-6 pointer-events-none">
// //       <nav className="pointer-events-auto flex items-center justify-between w-full max-w-6xl px-7 py-3.5 rounded-full bg-[#FAF9F7]/80 backdrop-blur-md border border-[#D4AF37]/30 shadow-[0_10px_30px_rgba(44,24,16,0.08)]">
        
// //         {/* Logo + Emblem */}
// //         <div 
// //           className="flex items-center cursor-pointer select-none"
// //           onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
// //         >
// //           <img src={logo} alt="Kayda Logo" className="h-14 md:h-16 w-auto object-contain" />
// //         </div>

// //         {/* Navigation Links */}
// //         <div className="hidden md:flex items-center gap-8 text-[13px] font-semibold tracking-[0.08em] uppercase text-[#2C1810]/80">
// //           <button onClick={() => scrollToSection("choose-role")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1.5 cursor-pointer">
// //             Moot Court <span className="text-[10px] text-[#D4AF37]">✦</span>
// //           </button>
// //           <button onClick={() => { window.location.hash = '#/evidence-analyzer'; }} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
// //             Document Suite <span className="text-[10px] text-[#2C1810]/40">▾</span>
// //           </button>
// //           <button onClick={() => scrollToSection("drafting")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
// //             Drafting & Templates <span className="text-[10px] text-[#2C1810]/40">▾</span>
// //           </button>
// //           <button onClick={() => scrollToSection("pricing")} className="hover:text-[#8C5A3C] transition-colors cursor-pointer">
// //             Pricing
// //           </button>
// //         </div>

// //         {/* Action Buttons */}
// //         <div className="flex items-center gap-5">
// //           <button className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#2C1810] hover:underline cursor-pointer">
// //             Sign In
// //           </button>
// //           <button 
// //             onClick={() => scrollToSection("choose-role")}
// //             className="px-6 py-2.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(212,175,55,0.35)] transition-all duration-300 cursor-pointer"
// //           >
// //             Launch App
// //           </button>
// //         </div>
// //       </nav>
// //     </div>
// //   );
// // }
// import logo from "../../assets/12.svg";

// export default function LandingNavbar({ scrollToSection }) {
//   return (
//     <div className="fixed top-5 inset-x-0 z-50 flex justify-center px-6 pointer-events-none">
//       <nav className="pointer-events-auto flex items-center justify-between w-full max-w-6xl px-7 py-2 rounded-full bg-[#FAF9F7]/80 backdrop-blur-md border border-[#D4AF37]/30 shadow-[0_10px_30px_rgba(44,24,16,0.08)]">
        
//         {/* Logo + Emblem */}
//         <div 
//           className="flex items-center cursor-pointer select-none"
//           onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
//         >
//           <img src={logo} alt="Kayda Logo" className="w-14 h-auto" />
          
//           {/* Reduced the top margin to mt-0.5 to bring it slightly up from the last adjustment */}
//           <span className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-[#2C1810] -ml-[16px] mt-0.5">
//             ayda
//           </span>
//         </div>

//         {/* Navigation Links */}
//         <div className="hidden md:flex items-center gap-8 text-[13px] font-semibold tracking-[0.08em] uppercase text-[#2C1810]/80">
//           <button onClick={() => scrollToSection("choose-role")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1.5 cursor-pointer">
//             Moot Court <span className="text-[10px] text-[#D4AF37]">✦</span>
//           </button>
//           <button onClick={() => { window.location.hash = '#/evidence-analyzer'; }} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
//             Document Suite <span className="text-[10px] text-[#2C1810]/40">▾</span>
//           </button>
//           <button onClick={() => scrollToSection("drafting")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
//             Drafting & Templates <span className="text-[10px] text-[#2C1810]/40">▾</span>
//           </button>
//           <button onClick={() => scrollToSection("pricing")} className="hover:text-[#8C5A3C] transition-colors cursor-pointer">
//             Pricing
//           </button>
//         </div>

//         {/* Action Buttons */}
//         <div className="flex items-center gap-5">
//           <button className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#2C1810] hover:underline cursor-pointer">
//             Sign In
//           </button>
//           <button 
//             onClick={() => scrollToSection("choose-role")}
//             className="px-6 py-1.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(212,175,55,0.35)] transition-all duration-300 cursor-pointer"
//           >
//             Launch App
//           </button>
//         </div>
//       </nav>
//     </div>
//   );
// }

import { useState, useEffect } from "react";
import logo from "../../assets/12.svg";

export default function LandingNavbar({ scrollToSection }) {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;

      // 1. Morph into the rounded container when scrolled past 50px
      if (currentScrollY > 50) {
        setIsScrolled(true);
      } else {
        setIsScrolled(false);
      }

      // 2. Hide when scrolling down, show when scrolling up
      if (currentScrollY > lastScrollY && currentScrollY > 100) {
        setIsVisible(false); // Scrolling down
      } else {
        setIsVisible(true);  // Scrolling up or at top
      }

      setLastScrollY(currentScrollY);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [lastScrollY]);

  return (
    <div 
      className={`fixed inset-x-0 z-50 flex justify-center pointer-events-none transition-all duration-500 ease-in-out ${
        isVisible ? "translate-y-0" : "-translate-y-[150px]"
      } ${
        isScrolled ? "top-5 px-6" : "top-0 px-0"
      }`}
    >
      <nav 
        className={`pointer-events-auto flex items-center justify-between w-full transition-all duration-500 ease-in-out ${
          isScrolled 
            ? "max-w-6xl px-7 py-2 rounded-full bg-[#FAF9F7]/80 backdrop-blur-md border border-[#D4AF37]/30 shadow-[0_10px_30px_rgba(44,24,16,0.08)]" 
            : "max-w-full px-8 md:px-16 py-4 bg-transparent border-transparent shadow-none"
        }`}
      >
        
        {/* Logo + Emblem */}
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
        <div className="hidden md:flex items-center gap-8 text-[13px] font-semibold tracking-[0.08em] uppercase text-[#2C1810]/80">
          <button onClick={() => scrollToSection("choose-role")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1.5 cursor-pointer">
            Moot Court <span className="text-[10px] text-[#D4AF37]">✦</span>
          </button>
          <button onClick={() => { window.location.hash = '#/evidence-analyzer'; }} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
            Document Suite <span className="text-[10px] text-[#2C1810]/40">▾</span>
          </button>
          <button onClick={() => scrollToSection("drafting")} className="hover:text-[#8C5A3C] transition-colors flex items-center gap-1 cursor-pointer">
            Drafting & Templates <span className="text-[10px] text-[#2C1810]/40">▾</span>
          </button>
          <button onClick={() => scrollToSection("pricing")} className="hover:text-[#8C5A3C] transition-colors cursor-pointer">
            Pricing
          </button>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-5">
          <button className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#2C1810] hover:underline cursor-pointer">
            Sign In
          </button>
          <button 
            onClick={() => scrollToSection("choose-role")}
            className="px-6 py-1.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-[#FAF9F7] bg-[#2C1810] border border-[#D4AF37] rounded-full hover:bg-[#8C5A3C] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(212,175,55,0.35)] transition-all duration-300 cursor-pointer"
          >
            Launch App
          </button>
        </div>
      </nav>
    </div>
  );
}