// import { useState, useEffect } from "react";
// import { useNavigate } from "react-router-dom";
// import { registerWithEmail, loginWithEmail, loginWithGoogle } from "../firebase";
// import { useAuth } from "../context/AuthContext";

// // ─── Inline SVG Icons ────────────────────────────────────────────────────────
// const GoogleIcon = () => (
//   <svg width="20" height="20" viewBox="0 0 48 48" fill="none">
//     <path d="M47.5 24.5c0-1.6-.1-3.2-.4-4.7H24v8.9h13.2c-.6 3-2.3 5.5-4.8 7.2v6h7.7c4.5-4.2 7.4-10.3 7.4-17.4z" fill="#4285F4"/>
//     <path d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.1 1.4-4.9 2.3-8.2 2.3-6.3 0-11.6-4.2-13.5-9.9H2.5v6.2C6.5 42.9 14.7 48 24 48z" fill="#34A853"/>
//     <path d="M10.5 28.6A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.1.7-4.6v-6.2H2.5A24 24 0 0 0 0 24c0 3.8.9 7.5 2.5 10.8l8-6.2z" fill="#FBBC05"/>
//     <path d="M24 9.5c3.5 0 6.7 1.2 9.2 3.6l6.9-6.9C35.9 2.4 30.4 0 24 0 14.7 0 6.5 5.1 2.5 13.2l8 6.2C12.4 13.7 17.7 9.5 24 9.5z" fill="#EA4335"/>
//   </svg>
// );

// const EyeIcon = ({ open }) => (
//   <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
//     {open ? (
//       <>
//         <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
//         <circle cx="12" cy="12" r="3"/>
//       </>
//     ) : (
//       <>
//         <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
//         <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
//         <line x1="1" y1="1" x2="23" y2="23"/>
//       </>
//     )}
//   </svg>
// );

// // ─── Field Component ──────────────────────────────────────────────────────────
// function Field({ label, id, type = "text", value, onChange, placeholder, error, rightEl }) {
//   return (
//     <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
//       <label
//         htmlFor={id}
//         style={{
//           fontSize: "11px",
//           fontWeight: 700,
//           letterSpacing: "0.1em",
//           textTransform: "uppercase",
//           color: "#6B4C3B",
//         }}
//       >
//         {label}
//       </label>
//       <div style={{ position: "relative" }}>
//         <input
//           id={id}
//           type={type}
//           value={value}
//           onChange={onChange}
//           placeholder={placeholder}
//           style={{
//             width: "100%",
//             padding: rightEl ? "11px 42px 11px 14px" : "11px 14px",
//             background: error ? "rgba(211,47,47,0.04)" : "rgba(44,24,16,0.03)",
//             border: `1.5px solid ${error ? "#D32F2F" : "rgba(212,175,55,0.35)"}`,
//             borderRadius: "10px",
//             fontFamily: "'Poppins', sans-serif",
//             fontSize: "14px",
//             color: "#2C1810",
//             outline: "none",
//             boxSizing: "border-box",
//             transition: "border-color 0.2s, box-shadow 0.2s",
//           }}
//           onFocus={e => {
//             e.target.style.borderColor = "#D4AF37";
//             e.target.style.boxShadow = "0 0 0 3px rgba(212,175,55,0.12)";
//           }}
//           onBlur={e => {
//             e.target.style.borderColor = error ? "#D32F2F" : "rgba(212,175,55,0.35)";
//             e.target.style.boxShadow = "none";
//           }}
//         />
//         {rightEl && (
//           <div style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", display: "flex", alignItems: "center" }}>
//             {rightEl}
//           </div>
//         )}
//       </div>
//       {error && (
//         <p style={{ fontSize: "11px", color: "#D32F2F", margin: 0, fontFamily: "'Poppins', sans-serif" }}>
//           {error}
//         </p>
//       )}
//     </div>
//   );
// }

// // ─── Main AuthPage ────────────────────────────────────────────────────────────
// export default function AuthPage() {
//   const { currentUser, loading: authLoading } = useAuth();
//   const navigate = useNavigate();
//   const [tab, setTab] = useState("signin"); // "signin" | "register"
//   const [loading, setLoading] = useState(false);
//   const [globalError, setGlobalError] = useState("");
//   const [showPw, setShowPw] = useState(false);
//   const [showConfirm, setShowConfirm] = useState(false);
//   const [mounted, setMounted] = useState(false);

//   // Sign-in form state
//   const [siEmail, setSiEmail] = useState("");
//   const [siPassword, setSiPassword] = useState("");
//   const [siErrors, setSiErrors] = useState({});

//   // Register form state
//   const [reg, setReg] = useState({
//     firstName: "", lastName: "", age: "",
//     mobile: "", email: "", password: "", confirm: "",
//   });
//   const [regErrors, setRegErrors] = useState({});

//   useEffect(() => {
//     if (!authLoading && currentUser) {
//       navigate("/", { replace: true });
//     }
//   }, [currentUser, authLoading, navigate]);

//   useEffect(() => {
//     setTimeout(() => setMounted(true), 50);
//   }, []);

//   // Show nothing while checking auth state
//   if (authLoading) return null;

//   const setRegField = (key) => (e) => {
//     setReg((r) => ({ ...r, [key]: e.target.value }));
//     setRegErrors((r) => ({ ...r, [key]: "" }));
//     setGlobalError("");
//   };

//   // ─── Validations ──────────────────────────────────────────────────────────
//   function validateSignIn() {
//     const err = {};
//     if (!siEmail) err.email = "Email is required";
//     else if (!/\S+@\S+\.\S+/.test(siEmail)) err.email = "Invalid email address";
//     if (!siPassword) err.password = "Password is required";
//     setSiErrors(err);
//     return Object.keys(err).length === 0;
//   }

//   function validateRegister() {
//     const err = {};
//     if (!reg.firstName.trim()) err.firstName = "First name is required";
//     if (!reg.lastName.trim()) err.lastName = "Last name is required";
//     if (!reg.age) err.age = "Age is required";
//     else if (isNaN(reg.age) || Number(reg.age) < 16 || Number(reg.age) > 100) err.age = "Enter a valid age (16–100)";
//     if (!reg.mobile) err.mobile = "Mobile number is required";
//     else if (!/^\+?[\d\s\-]{8,15}$/.test(reg.mobile)) err.mobile = "Enter a valid mobile number";
//     if (!reg.email) err.email = "Email is required";
//     else if (!/\S+@\S+\.\S+/.test(reg.email)) err.email = "Invalid email address";
//     if (!reg.password) err.password = "Password is required";
//     else if (reg.password.length < 8) err.password = "Minimum 8 characters";
//     if (!reg.confirm) err.confirm = "Please confirm your password";
//     else if (reg.confirm !== reg.password) err.confirm = "Passwords do not match";
//     setRegErrors(err);
//     return Object.keys(err).length === 0;
//   }

//   // ─── Handlers ─────────────────────────────────────────────────────────────
//   const handleSignIn = async (e) => {
//     e.preventDefault();
//     if (!validateSignIn()) return;
//     setLoading(true);
//     setGlobalError("");
//     try {
//       await loginWithEmail(siEmail, siPassword);
//       navigate("/", { replace: true });
//     } catch (err) {
//       setGlobalError(friendlyError(err.code));
//     } finally {
//       setLoading(false);
//     }
//   };

//   const handleRegister = async (e) => {
//     e.preventDefault();
//     if (!validateRegister()) return;
//     setLoading(true);
//     setGlobalError("");
//     try {
//       await registerWithEmail(reg);
//       navigate("/", { replace: true });
//     } catch (err) {
//       setGlobalError(friendlyError(err.code));
//     } finally {
//       setLoading(false);
//     }
//   };

//   const handleGoogle = async () => {
//     setLoading(true);
//     setGlobalError("");
//     try {
//       await loginWithGoogle();
//       navigate("/", { replace: true });
//     } catch (err) {
//       if (err.code !== "auth/popup-closed-by-user" && err.code !== "auth/cancelled-popup-request") {
//         setGlobalError(friendlyError(err.code));
//       }
//     } finally {
//       setLoading(false);
//     }
//   };


//   function friendlyError(code) {
//     const map = {
//       "auth/invalid-credential": "Invalid email or password. Please try again.",
//       "auth/user-not-found": "No account found with this email.",
//       "auth/wrong-password": "Incorrect password.",
//       "auth/email-already-in-use": "This email is already registered. Please sign in.",
//       "auth/weak-password": "Password is too weak. Use at least 8 characters.",
//       "auth/too-many-requests": "Too many attempts. Please try again later.",
//       "auth/network-request-failed": "Network error. Check your connection.",
//     };
//     return map[code] || "Something went wrong. Please try again.";
//   }

//   // ─── Styles ───────────────────────────────────────────────────────────────
//   const st = {
//     page: {
//       minHeight: "100vh",
//       background: "linear-gradient(135deg, #FAF9F7 0%, #F5EFE6 40%, #EDE0CC 100%)",
//       display: "flex",
//       alignItems: "center",
//       justifyContent: "center",
//       fontFamily: "'Poppins', sans-serif",
//       padding: "24px 16px",
//       position: "relative",
//       overflow: "hidden",
//     },
//     blob1: {
//       position: "absolute", top: "-120px", right: "-80px",
//       width: "500px", height: "500px",
//       borderRadius: "50%",
//       background: "radial-gradient(circle, rgba(212,175,55,0.12) 0%, transparent 70%)",
//       pointerEvents: "none",
//     },
//     blob2: {
//       position: "absolute", bottom: "-100px", left: "-60px",
//       width: "400px", height: "400px",
//       borderRadius: "50%",
//       background: "radial-gradient(circle, rgba(140,90,60,0.1) 0%, transparent 70%)",
//       pointerEvents: "none",
//     },
//     card: {
//       position: "relative",
//       width: "100%",
//       maxWidth: "480px",
//       background: "rgba(255,255,255,0.72)",
//       backdropFilter: "blur(24px)",
//       WebkitBackdropFilter: "blur(24px)",
//       border: "1.5px solid rgba(212,175,55,0.25)",
//       borderRadius: "24px",
//       boxShadow: "0 32px 80px rgba(44,24,16,0.12), 0 8px 24px rgba(44,24,16,0.06)",
//       padding: "40px 40px 36px",
//       opacity: mounted ? 1 : 0,
//       transform: mounted ? "translateY(0)" : "translateY(24px)",
//       transition: "opacity 0.5s ease, transform 0.5s ease",
//     },
//     brand: {
//       display: "flex",
//       flexDirection: "column",
//       alignItems: "center",
//       marginBottom: "28px",
//       gap: "4px",
//     },
//     crest: {
//       fontSize: "36px",
//       lineHeight: 1,
//       marginBottom: "4px",
//     },
//     brandName: {
//       fontFamily: "'Playfair Display', serif",
//       fontSize: "26px",
//       fontWeight: 700,
//       color: "#2C1810",
//       letterSpacing: "-0.02em",
//     },
//     brandSub: {
//       fontSize: "11px",
//       fontWeight: 600,
//       letterSpacing: "0.18em",
//       textTransform: "uppercase",
//       color: "#8C5A3C",
//     },
//     tabs: {
//       display: "flex",
//       background: "rgba(44,24,16,0.05)",
//       borderRadius: "12px",
//       padding: "4px",
//       marginBottom: "28px",
//     },
//     tab: (active) => ({
//       flex: 1,
//       padding: "9px 0",
//       borderRadius: "9px",
//       border: "none",
//       fontFamily: "'Poppins', sans-serif",
//       fontSize: "13px",
//       fontWeight: 600,
//       letterSpacing: "0.06em",
//       cursor: "pointer",
//       transition: "all 0.25s ease",
//       background: active ? "#2C1810" : "transparent",
//       color: active ? "#FAF9F7" : "#6B4C3B",
//       boxShadow: active ? "0 4px 12px rgba(44,24,16,0.2)" : "none",
//     }),
//     form: { display: "flex", flexDirection: "column", gap: "16px" },
//     grid2: {
//       display: "grid",
//       gridTemplateColumns: "1fr 1fr",
//       gap: "12px",
//     },
//     divider: {
//       display: "flex",
//       alignItems: "center",
//       gap: "12px",
//       margin: "4px 0",
//     },
//     divLine: {
//       flex: 1,
//       height: "1px",
//       background: "rgba(212,175,55,0.3)",
//     },
//     divText: {
//       fontSize: "11px",
//       color: "#A0856C",
//       fontWeight: 600,
//       letterSpacing: "0.08em",
//       textTransform: "uppercase",
//     },
//     googleBtn: {
//       display: "flex",
//       alignItems: "center",
//       justifyContent: "center",
//       gap: "10px",
//       width: "100%",
//       padding: "12px",
//       background: "white",
//       border: "1.5px solid rgba(212,175,55,0.35)",
//       borderRadius: "12px",
//       fontFamily: "'Poppins', sans-serif",
//       fontSize: "14px",
//       fontWeight: 600,
//       color: "#2C1810",
//       cursor: "pointer",
//       transition: "all 0.2s ease",
//     },
//     submitBtn: {
//       width: "100%",
//       padding: "14px",
//       background: "linear-gradient(135deg, #2C1810 0%, #4A2818 100%)",
//       border: "1.5px solid rgba(212,175,55,0.5)",
//       borderRadius: "12px",
//       fontFamily: "'Poppins', sans-serif",
//       fontSize: "14px",
//       fontWeight: 700,
//       letterSpacing: "0.08em",
//       textTransform: "uppercase",
//       color: "#FAF9F7",
//       cursor: loading ? "not-allowed" : "pointer",
//       opacity: loading ? 0.7 : 1,
//       transition: "all 0.2s ease",
//       display: "flex",
//       alignItems: "center",
//       justifyContent: "center",
//       gap: "8px",
//     },
//     errorBox: {
//       background: "rgba(211,47,47,0.07)",
//       border: "1px solid rgba(211,47,47,0.25)",
//       borderRadius: "10px",
//       padding: "10px 14px",
//       fontSize: "13px",
//       color: "#C62828",
//       fontFamily: "'Poppins', sans-serif",
//     },
//     switchText: {
//       textAlign: "center",
//       fontSize: "13px",
//       color: "#6B4C3B",
//       marginTop: "6px",
//     },
//     switchLink: {
//       color: "#8C5A3C",
//       fontWeight: 700,
//       cursor: "pointer",
//       textDecoration: "underline",
//       background: "none",
//       border: "none",
//       fontFamily: "'Poppins', sans-serif",
//       fontSize: "13px",
//     },
//     eyeBtn: {
//       background: "none",
//       border: "none",
//       cursor: "pointer",
//       padding: 0,
//       color: "#8C5A3C",
//       display: "flex",
//       alignItems: "center",
//     },
//   };

//   return (
//     <div style={st.page}>
//       {/* Decorative blobs */}
//       <div style={st.blob1} />
//       <div style={st.blob2} />

//       {/* Card */}
//       <div style={st.card}>
//         {/* Brand */}
//         <div style={st.brand}>
//           <span style={st.crest}>⚖️</span>
//           <span style={st.brandName}>Kayda</span>
//           <span style={st.brandSub}>Legal Intelligence Platform</span>
//         </div>

//         {/* Tabs */}
//         <div style={st.tabs} role="tablist">
//           <button
//             id="tab-signin"
//             role="tab"
//             aria-selected={tab === "signin"}
//             style={st.tab(tab === "signin")}
//             onClick={() => { setTab("signin"); setGlobalError(""); }}
//           >
//             Sign In
//           </button>
//           <button
//             id="tab-register"
//             role="tab"
//             aria-selected={tab === "register"}
//             style={st.tab(tab === "register")}
//             onClick={() => { setTab("register"); setGlobalError(""); }}
//           >
//             Register
//           </button>
//         </div>

//         {/* Global Error */}
//         {globalError && <div style={{ ...st.errorBox, marginBottom: "16px" }}>{globalError}</div>}

//         {/* ─── SIGN IN ─── */}
//         {tab === "signin" && (
//           <form id="signin-form" onSubmit={handleSignIn} style={st.form} noValidate>
//             <Field
//               label="Email Address"
//               id="si-email"
//               type="email"
//               value={siEmail}
//               onChange={e => { setSiEmail(e.target.value); setSiErrors(p => ({...p, email: ""})); setGlobalError(""); }}
//               placeholder="you@example.com"
//               error={siErrors.email}
//             />
//             <Field
//               label="Password"
//               id="si-password"
//               type={showPw ? "text" : "password"}
//               value={siPassword}
//               onChange={e => { setSiPassword(e.target.value); setSiErrors(p => ({...p, password: ""})); setGlobalError(""); }}
//               placeholder="••••••••"
//               error={siErrors.password}
//               rightEl={
//                 <button type="button" style={st.eyeBtn} onClick={() => setShowPw(v => !v)} aria-label="Toggle password">
//                   <EyeIcon open={showPw} />
//                 </button>
//               }
//             />

//             <button
//               id="signin-submit-btn"
//               type="submit"
//               style={st.submitBtn}
//               disabled={loading}
//               onMouseEnter={e => { if (!loading) { e.currentTarget.style.background = "linear-gradient(135deg, #4A2818 0%, #6B3A20 100%)"; e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(44,24,16,0.25)"; }}}
//               onMouseLeave={e => { e.currentTarget.style.background = "linear-gradient(135deg, #2C1810 0%, #4A2818 100%)"; e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; }}
//             >
//               {loading ? (
//                 <>
//                   <span style={{ width: "16px", height: "16px", borderRadius: "50%", border: "2px solid rgba(250,249,247,0.4)", borderTopColor: "#FAF9F7", animation: "spin 0.7s linear infinite", display: "inline-block" }} />
//                   Signing in…
//                 </>
//               ) : "Sign In"}
//             </button>

//             <div style={st.divider}>
//               <div style={st.divLine} />
//               <span style={st.divText}>or</span>
//               <div style={st.divLine} />
//             </div>

//             <button
//               id="google-signin-btn"
//               type="button"
//               style={st.googleBtn}
//               onClick={handleGoogle}
//               disabled={loading}
//               onMouseEnter={e => { e.currentTarget.style.background = "#f8f8f8"; e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 6px 20px rgba(44,24,16,0.1)"; }}
//               onMouseLeave={e => { e.currentTarget.style.background = "white"; e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; }}
//             >
//               <GoogleIcon />
//               Continue with Google
//             </button>

//             <p style={st.switchText}>
//               Don't have an account?{" "}
//               <button type="button" style={st.switchLink} onClick={() => { setTab("register"); setGlobalError(""); }}>
//                 Register now
//               </button>
//             </p>
//           </form>
//         )}

//         {/* ─── REGISTER ─── */}
//         {tab === "register" && (
//           <form id="register-form" onSubmit={handleRegister} style={st.form} noValidate>
//             <div style={st.grid2}>
//               <Field
//                 label="First Name"
//                 id="reg-firstname"
//                 value={reg.firstName}
//                 onChange={setRegField("firstName")}
//                 placeholder="Arjun"
//                 error={regErrors.firstName}
//               />
//               <Field
//                 label="Last Name"
//                 id="reg-lastname"
//                 value={reg.lastName}
//                 onChange={setRegField("lastName")}
//                 placeholder="Sharma"
//                 error={regErrors.lastName}
//               />
//             </div>

//             <div style={st.grid2}>
//               <Field
//                 label="Age"
//                 id="reg-age"
//                 type="number"
//                 value={reg.age}
//                 onChange={setRegField("age")}
//                 placeholder="24"
//                 error={regErrors.age}
//               />
//               <Field
//                 label="Mobile Number"
//                 id="reg-mobile"
//                 type="tel"
//                 value={reg.mobile}
//                 onChange={setRegField("mobile")}
//                 placeholder="+91 9876543210"
//                 error={regErrors.mobile}
//               />
//             </div>

//             <Field
//               label="Email Address"
//               id="reg-email"
//               type="email"
//               value={reg.email}
//               onChange={setRegField("email")}
//               placeholder="you@example.com"
//               error={regErrors.email}
//             />

//             <Field
//               label="Password"
//               id="reg-password"
//               type={showPw ? "text" : "password"}
//               value={reg.password}
//               onChange={setRegField("password")}
//               placeholder="Min. 8 characters"
//               error={regErrors.password}
//               rightEl={
//                 <button type="button" style={st.eyeBtn} onClick={() => setShowPw(v => !v)} aria-label="Toggle password">
//                   <EyeIcon open={showPw} />
//                 </button>
//               }
//             />

//             <Field
//               label="Confirm Password"
//               id="reg-confirm"
//               type={showConfirm ? "text" : "password"}
//               value={reg.confirm}
//               onChange={setRegField("confirm")}
//               placeholder="Re-enter password"
//               error={regErrors.confirm}
//               rightEl={
//                 <button type="button" style={st.eyeBtn} onClick={() => setShowConfirm(v => !v)} aria-label="Toggle confirm password">
//                   <EyeIcon open={showConfirm} />
//                 </button>
//               }
//             />

//             <button
//               id="register-submit-btn"
//               type="submit"
//               style={st.submitBtn}
//               disabled={loading}
//               onMouseEnter={e => { if (!loading) { e.currentTarget.style.background = "linear-gradient(135deg, #4A2818 0%, #6B3A20 100%)"; e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(44,24,16,0.25)"; }}}
//               onMouseLeave={e => { e.currentTarget.style.background = "linear-gradient(135deg, #2C1810 0%, #4A2818 100%)"; e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; }}
//             >
//               {loading ? (
//                 <>
//                   <span style={{ width: "16px", height: "16px", borderRadius: "50%", border: "2px solid rgba(250,249,247,0.4)", borderTopColor: "#FAF9F7", animation: "spin 0.7s linear infinite", display: "inline-block" }} />
//                   Creating account…
//                 </>
//               ) : "Create Account"}
//             </button>

//             <div style={st.divider}>
//               <div style={st.divLine} />
//               <span style={st.divText}>or</span>
//               <div style={st.divLine} />
//             </div>

//             <button
//               id="google-register-btn"
//               type="button"
//               style={st.googleBtn}
//               onClick={handleGoogle}
//               disabled={loading}
//               onMouseEnter={e => { e.currentTarget.style.background = "#f8f8f8"; e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 6px 20px rgba(44,24,16,0.1)"; }}
//               onMouseLeave={e => { e.currentTarget.style.background = "white"; e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; }}
//             >
//               <GoogleIcon />
//               Sign up with Google
//             </button>

//             <p style={st.switchText}>
//               Already have an account?{" "}
//               <button type="button" style={st.switchLink} onClick={() => { setTab("signin"); setGlobalError(""); }}>
//                 Sign in
//               </button>
//             </p>
//           </form>
//         )}
//       </div>

//       <style>{`
//         @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Poppins:wght@400;500;600;700&display=swap');
//         @keyframes spin { to { transform: rotate(360deg); } }
//         input::placeholder { color: rgba(107,76,59,0.45); }
//         input[type=number]::-webkit-inner-spin-button,
//         input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
//       `}</style>
//     </div>
//   );
// }

import { useState, useEffect } from "react";
import { registerWithEmail, loginWithEmail, loginWithGoogle } from "../firebase";
import { useAuth } from "../context/AuthContext";

// ─── Inline SVG Icons ────────────────────────────────────────────────────────
const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" fill="none">
    <path d="M47.5 24.5c0-1.6-.1-3.2-.4-4.7H24v8.9h13.2c-.6 3-2.3 5.5-4.8 7.2v6h7.7c4.5-4.2 7.4-10.3 7.4-17.4z" fill="#4285F4"/>
    <path d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.1 1.4-4.9 2.3-8.2 2.3-6.3 0-11.6-4.2-13.5-9.9H2.5v6.2C6.5 42.9 14.7 48 24 48z" fill="#34A853"/>
    <path d="M10.5 28.6A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.1.7-4.6v-6.2H2.5A24 24 0 0 0 0 24c0 3.8.9 7.5 2.5 10.8l8-6.2z" fill="#FBBC05"/>
    <path d="M24 9.5c3.5 0 6.7 1.2 9.2 3.6l6.9-6.9C35.9 2.4 30.4 0 24 0 14.7 0 6.5 5.1 2.5 13.2l8 6.2C12.4 13.7 17.7 9.5 24 9.5z" fill="#EA4335"/>
  </svg>
);

const EyeIcon = ({ open }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {open ? (
      <>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
        <circle cx="12" cy="12" r="3"/>
      </>
    ) : (
      <>
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
        <line x1="1" y1="1" x2="23" y2="23"/>
      </>
    )}
  </svg>
);

const ShieldIcon = () => (
  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#2C1810" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mb-1">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  </svg>
);

// ─── Field Component ──────────────────────────────────────────────────────────
function Field({ label, id, type = "text", value, onChange, placeholder, error, rightEl }) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={id}
        className="text-[10px] font-bold tracking-[0.08em] uppercase text-[#6B4C3B]"
      >
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className={`w-full text-[13px] text-[#2C1810] font-['Poppins'] outline-none rounded-lg transition-all duration-200 placeholder:text-[#6B4C3B]/45
            ${rightEl ? "py-2 pl-3 pr-9" : "py-2 px-3"}
            ${error 
              ? "bg-[#D32F2F]/[0.04] border-[1.5px] border-[#D32F2F] focus:border-[#D32F2F] focus:ring-2 focus:ring-[#D32F2F]/20" 
              : "bg-[#2C1810]/[0.02] border-[1.5px] border-[#D4AF37]/35 focus:border-[#D4AF37] focus:ring-2 focus:ring-[#D4AF37]/15"
            }`}
        />
        {rightEl && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
            {rightEl}
          </div>
        )}
      </div>
      {error && (
        <p className="text-[10px] text-[#D32F2F] m-0 mt-0.5 font-['Poppins']">
          {error}
        </p>
      )}
    </div>
  );
}

// ─── Main AuthPage ────────────────────────────────────────────────────────────
export default function AuthPage() {
  const { currentUser, loading: authLoading } = useAuth();
  const [tab, setTab] = useState("signin"); 
  const [loading, setLoading] = useState(false);
  const [globalError, setGlobalError] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [mounted, setMounted] = useState(false);

  const [siEmail, setSiEmail] = useState("");
  const [siPassword, setSiPassword] = useState("");
  const [siErrors, setSiErrors] = useState({});

  const [reg, setReg] = useState({
    firstName: "", lastName: "", age: "",
    mobile: "", email: "", password: "", confirm: "",
  });
  const [regErrors, setRegErrors] = useState({});

  useEffect(() => {
    if (!authLoading && currentUser) {
      window.location.hash = "#/";
    }
  }, [currentUser, authLoading]);

  useEffect(() => {
    setTimeout(() => setMounted(true), 50);
  }, []);

  if (authLoading) return null;

  const setRegField = (key) => (e) => {
    setReg((r) => ({ ...r, [key]: e.target.value }));
    setRegErrors((r) => ({ ...r, [key]: "" }));
    setGlobalError("");
  };

  function validateSignIn() {
    const err = {};
    if (!siEmail) err.email = "Required";
    else if (!/\S+@\S+\.\S+/.test(siEmail)) err.email = "Invalid email";
    if (!siPassword) err.password = "Required";
    setSiErrors(err);
    return Object.keys(err).length === 0;
  }

  function validateRegister() {
    const err = {};
    if (!reg.firstName.trim()) err.firstName = "Required";
    if (!reg.lastName.trim()) err.lastName = "Required";
    if (!reg.age) err.age = "Required";
    else if (isNaN(reg.age) || Number(reg.age) < 16 || Number(reg.age) > 100) err.age = "Invalid age";
    if (!reg.mobile) err.mobile = "Required";
    else if (!/^\+?[\d\s\-]{8,15}$/.test(reg.mobile)) err.mobile = "Invalid mobile";
    if (!reg.email) err.email = "Required";
    else if (!/\S+@\S+\.\S+/.test(reg.email)) err.email = "Invalid email";
    if (!reg.password) err.password = "Required";
    else if (reg.password.length < 8) err.password = "Min 8 chars";
    if (!reg.confirm) err.confirm = "Required";
    else if (reg.confirm !== reg.password) err.confirm = "Mismatch";
    setRegErrors(err);
    return Object.keys(err).length === 0;
  }

  const handleSignIn = async (e) => {
    e.preventDefault();
    if (!validateSignIn()) return;
    setLoading(true);
    setGlobalError("");
    try {
      await loginWithEmail(siEmail, siPassword);
      window.location.hash = "#/";
    } catch (err) {
      setGlobalError(friendlyError(err.code));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!validateRegister()) return;
    setLoading(true);
    setGlobalError("");
    try {
      await registerWithEmail(reg);
      window.location.hash = "#/";
    } catch (err) {
      setGlobalError(friendlyError(err.code));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setLoading(true);
    setGlobalError("");
    try {
      await loginWithGoogle();
      window.location.hash = "#/";
    } catch (err) {
      if (err.code !== "auth/popup-closed-by-user" && err.code !== "auth/cancelled-popup-request") {
        setGlobalError(friendlyError(err.code));
      }
    } finally {
      setLoading(false);
    }
  };

  function friendlyError(code) {
    const map = {
      "auth/invalid-credential": "Invalid credentials.",
      "auth/user-not-found": "No account found.",
      "auth/wrong-password": "Incorrect password.",
      "auth/email-already-in-use": "Email already registered.",
      "auth/weak-password": "Use at least 8 characters.",
      "auth/too-many-requests": "Too many attempts.",
    };
    return map[code] || "Something went wrong.";
  }

  return (
    <>
      {/* Include fonts so the custom font families work correctly */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Poppins:wght@400;500;600;700&display=swap');
        input[type=number]::-webkit-inner-spin-button,
        input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
      `}</style>

      <div className="flex w-full h-screen font-['Poppins'] bg-[#FAF9F7] overflow-hidden m-0 p-0">
        
        {/* ─── LEFT SIDE: IMAGE ─── */}
        <div 
          className="hidden md:flex flex-1 relative bg-cover bg-center flex-col justify-end p-10 text-white"
          style={{ backgroundImage: "url('https://images.unsplash.com/photo-1649653084130-06638e40ca25?fm=jpg&q=60&w=3000&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1yZWxhdGVkfDE1fHx8ZW58MHx8fHx8')" }}
        >
          <div className="absolute inset-0 bg-gradient-to-b from-[#2C1810]/20 to-[#2C1810]/80 z-10"></div>
          <div className="relative z-20">
            <h2 className="font-['Playfair_Display'] text-4xl mb-2 font-bold m-0">Precision in Law.</h2>
            <p className="text-sm opacity-85 max-w-[80%] m-0">
              Empowering legal professionals with next-generation intelligence and data-driven insights.
            </p>
          </div>
        </div>

        {/* ─── RIGHT SIDE: FORM ─── */}
        <div className="flex-1 flex items-center justify-center p-4 md:p-8 bg-[#FAF9F7] box-border">
          <div 
            className={`w-full max-w-[400px] flex flex-col justify-center h-full transition-all duration-500 ease-out 
              ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
          >
            {/* Brand */}
            {/* <div className="flex flex-col items-center mb-4 gap-1">
              <ShieldIcon />
              <span className="font-['Playfair_Display'] text-2xl font-bold text-[#2C1810] tracking-[-0.02em]">
                Kayda
              </span>
              <span className="text-[10px] font-semibold tracking-[0.15em] uppercase text-[#8C5A3C]">
                Legal Intelligence Platform
              </span>
            </div> */}

            {/* Tabs */}
            <div className="flex bg-[#2C1810]/5 rounded-[10px] p-[3px] mb-4" role="tablist">
              <button
                id="tab-signin"
                role="tab"
                aria-selected={tab === "signin"}
                className={`flex-1 py-2 rounded-lg border-none font-['Poppins'] text-xs font-semibold tracking-[0.04em] cursor-pointer transition-all duration-200 
                  ${tab === "signin" ? "bg-[#2C1810] text-[#FAF9F7] shadow-[0_2px_8px_rgba(44,24,16,0.15)]" : "bg-transparent text-[#6B4C3B]"}`}
                onClick={() => { setTab("signin"); setGlobalError(""); }}
              >
                Sign In
              </button>
              <button
                id="tab-register"
                role="tab"
                aria-selected={tab === "register"}
                className={`flex-1 py-2 rounded-lg border-none font-['Poppins'] text-xs font-semibold tracking-[0.04em] cursor-pointer transition-all duration-200 
                  ${tab === "register" ? "bg-[#2C1810] text-[#FAF9F7] shadow-[0_2px_8px_rgba(44,24,16,0.15)]" : "bg-transparent text-[#6B4C3B]"}`}
                onClick={() => { setTab("register"); setGlobalError(""); }}
              >
                Register
              </button>
            </div>

            {/* Global Error */}
            {/* Global Error */}
            {globalError && (
              <div className="bg-[#D32F2F]/[0.07] border border-[#D32F2F]/25 rounded-lg py-2 px-3 text-xs text-[#C62828] font-['Poppins'] mb-2.5">
                {globalError}
              </div>
            )}

            {/* ─── FORMS SLIDER CONTAINER ─── */}
            <div className="relative grid w-full">
              
              {/* ─── SIGN IN ─── */}
              <div 
                className={`col-start-1 row-start-1 flex flex-col justify-center transition-all duration-500 ease-out ${
                  tab === "signin" 
                    ? "opacity-100 translate-y-0 z-10" 
                    : "opacity-0 translate-y-8 -z-10 pointer-events-none"
                }`}
              >
                <form id="signin-form" onSubmit={handleSignIn} className="flex flex-col gap-2.5" noValidate>
                  <Field
                    label="Email Address"
                    id="si-email"
                    type="email"
                    value={siEmail}
                    onChange={e => { setSiEmail(e.target.value); setSiErrors(p => ({...p, email: ""})); setGlobalError(""); }}
                    placeholder="you@example.com"
                    error={siErrors.email}
                  />
                  <Field
                    label="Password"
                    id="si-password"
                    type={showPw ? "text" : "password"}
                    value={siPassword}
                    onChange={e => { setSiPassword(e.target.value); setSiErrors(p => ({...p, password: ""})); setGlobalError(""); }}
                    placeholder="••••••••"
                    error={siErrors.password}
                    rightEl={
                      <button type="button" className="bg-none border-none cursor-pointer p-0 text-[#8C5A3C] flex items-center outline-none" onClick={() => setShowPw(v => !v)}>
                        <EyeIcon open={showPw} />
                      </button>
                    }
                  />

                  <button
                    id="signin-submit-btn"
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 bg-gradient-to-br from-[#2C1810] to-[#4A2818] border border-[#D4AF37]/50 rounded-[10px] font-['Poppins'] text-[13px] font-bold tracking-[0.06em] uppercase text-[#FAF9F7] cursor-pointer transition-all duration-200 flex items-center justify-center gap-1.5 mt-0.5 hover:from-[#4A2818] hover:to-[#6B3A20] hover:-translate-y-[1px] disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {loading ? "Signing in..." : "Sign In"}
                  </button>

                  <div className="flex items-center gap-2 my-1">
                    <div className="flex-1 h-[1px] bg-[#D4AF37]/30" />
                    <span className="text-[10px] text-[#A0856C] font-semibold tracking-[0.08em] uppercase">or</span>
                    <div className="flex-1 h-[1px] bg-[#D4AF37]/30" />
                  </div>

                  <button
                    id="google-signin-btn"
                    type="button"
                    onClick={handleGoogle}
                    disabled={loading}
                    className="w-full py-2.5 bg-white border border-[#D4AF37]/40 rounded-[10px] font-['Poppins'] text-[13px] font-semibold text-[#2C1810] cursor-pointer transition-all duration-200 flex items-center justify-center gap-2 hover:bg-gray-50 hover:-translate-y-[1px]"
                  >
                    <GoogleIcon />
                    Continue with Google
                  </button>

                  <p className="text-center text-xs text-[#6B4C3B] m-0 mt-1">
                    Don't have an account?{" "}
                    <button type="button" className="text-[#8C5A3C] font-bold cursor-pointer underline bg-none border-none font-['Poppins'] text-xs p-0" onClick={() => { setTab("register"); setGlobalError(""); }}>
                      Register now
                    </button>
                  </p>
                </form>
              </div>

              {/* ─── REGISTER ─── */}
              <div 
                className={`col-start-1 row-start-1 flex flex-col justify-center transition-all duration-500 ease-out ${
                  tab === "register" 
                    ? "opacity-100 translate-y-0 z-10" 
                    : "opacity-0 -translate-y-8 -z-10 pointer-events-none"
                }`}
              >
                <form id="register-form" onSubmit={handleRegister} className="flex flex-col gap-2.5" noValidate>
                  <div className="grid grid-cols-2 gap-2">
                    <Field
                      label="First Name"
                      id="reg-firstname"
                      value={reg.firstName}
                      onChange={setRegField("firstName")}
                      placeholder="Arjun"
                      error={regErrors.firstName}
                    />
                    <Field
                      label="Last Name"
                      id="reg-lastname"
                      value={reg.lastName}
                      onChange={setRegField("lastName")}
                      placeholder="Sharma"
                      error={regErrors.lastName}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <Field
                      label="Age"
                      id="reg-age"
                      type="number"
                      value={reg.age}
                      onChange={setRegField("age")}
                      placeholder="24"
                      error={regErrors.age}
                    />
                    <Field
                      label="Mobile Number"
                      id="reg-mobile"
                      type="tel"
                      value={reg.mobile}
                      onChange={setRegField("mobile")}
                      placeholder="+91 9876543210"
                      error={regErrors.mobile}
                    />
                  </div>

                  <Field
                    label="Email Address"
                    id="reg-email"
                    type="email"
                    value={reg.email}
                    onChange={setRegField("email")}
                    placeholder="you@example.com"
                    error={regErrors.email}
                  />

                  <div className="grid grid-cols-2 gap-2">
                    <Field
                      label="Password"
                      id="reg-password"
                      type={showPw ? "text" : "password"}
                      value={reg.password}
                      onChange={setRegField("password")}
                      placeholder="Min 8 chars"
                      error={regErrors.password}
                      rightEl={
                        <button type="button" className="bg-none border-none cursor-pointer p-0 text-[#8C5A3C] flex items-center outline-none" onClick={() => setShowPw(v => !v)}>
                          <EyeIcon open={showPw} />
                        </button>
                      }
                    />

                    <Field
                      label="Confirm"
                      id="reg-confirm"
                      type={showConfirm ? "text" : "password"}
                      value={reg.confirm}
                      onChange={setRegField("confirm")}
                      placeholder="Re-enter"
                      error={regErrors.confirm}
                      rightEl={
                        <button type="button" className="bg-none border-none cursor-pointer p-0 text-[#8C5A3C] flex items-center outline-none" onClick={() => setShowConfirm(v => !v)}>
                          <EyeIcon open={showConfirm} />
                        </button>
                      }
                    />
                  </div>

                  <button
                    id="register-submit-btn"
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 bg-gradient-to-br from-[#2C1810] to-[#4A2818] border border-[#D4AF37]/50 rounded-[10px] font-['Poppins'] text-[13px] font-bold tracking-[0.06em] uppercase text-[#FAF9F7] cursor-pointer transition-all duration-200 flex items-center justify-center gap-1.5 mt-0.5 hover:from-[#4A2818] hover:to-[#6B3A20] hover:-translate-y-[1px] disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    {loading ? "Creating account..." : "Create Account"}
                  </button>

                  <div className="flex items-center gap-2 my-1">
                    <div className="flex-1 h-[1px] bg-[#D4AF37]/30" />
                    <span className="text-[10px] text-[#A0856C] font-semibold tracking-[0.08em] uppercase">or</span>
                    <div className="flex-1 h-[1px] bg-[#D4AF37]/30" />
                  </div>

                  <button
                    id="google-register-btn"
                    type="button"
                    onClick={handleGoogle}
                    disabled={loading}
                    className="w-full py-2.5 bg-white border border-[#D4AF37]/40 rounded-[10px] font-['Poppins'] text-[13px] font-semibold text-[#2C1810] cursor-pointer transition-all duration-200 flex items-center justify-center gap-2 hover:bg-gray-50 hover:-translate-y-[1px]"
                  >
                    <GoogleIcon />
                    Sign up with Google
                  </button>

                  <p className="text-center text-xs text-[#6B4C3B] m-0 mt-1">
                    Already have an account?{" "}
                    <button type="button" className="text-[#8C5A3C] font-bold cursor-pointer underline bg-none border-none font-['Poppins'] text-xs p-0" onClick={() => { setTab("signin"); setGlobalError(""); }}>
                      Sign in
                    </button>
                  </p>
                </form>
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </>
  );
}