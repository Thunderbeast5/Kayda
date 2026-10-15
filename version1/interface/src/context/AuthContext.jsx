import { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
  subscribeToAuth,
  logoutUser,
} from "../firebase";
import { getPlayerProfile } from "../api/playerApi";
import { listCases } from "../api/caseApi";
import { doc, setDoc, serverTimestamp } from "firebase/firestore";
import { db } from "../firebase";

const AuthContext = createContext(null);

const DEMO_USER = {
  uid: "demo-advocate-001",
  email: "counsel@mootcourt.demo",
  displayName: "Counsel Aditi Rao",
};

const DEMO_PROFILE = {
  uid: "demo-advocate-001",
  email: "counsel@mootcourt.demo",
  firstName: "Aditi",
  lastName: "Rao",
  displayName: "Counsel Aditi Rao",
  display_name: "Counsel Aditi Rao",
  photoURL: null,
  avatar: null,
  rating: 1250,
  games_played: 5,
  wins: 4,
  losses: 1,
  draws: 0,
  preferred_role: "defense",
  provider: "demo",
};

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async (uid, user = null) => {
    try {
      let profile = await getPlayerProfile(uid);

      if (!profile && user && db) {
        const nameParts = (user.displayName || "").split(" ");
        await setDoc(doc(db, "users", uid), {
          uid,
          email: user.email || "",
          firstName: nameParts[0] || "",
          lastName: nameParts.slice(1).join(" ") || "",
          displayName: user.displayName || user.email || "",
          display_name: user.displayName || user.email || "",
          photoURL: user.photoURL || null,
          avatar: user.photoURL || null,
          rating: 1200,
          games_played: 0,
          wins: 0,
          losses: 0,
          draws: 0,
          preferred_role: "defense",
          createdAt: serverTimestamp(),
          provider: user.providerData?.[0]?.providerId || "unknown",
        });
        profile = await getPlayerProfile(uid);
      }

      setUserProfile(profile);
    } catch (err) {
      console.error("[AuthContext] fetchProfile error:", err);
      setUserProfile(null);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToAuth(async (user) => {
      if (user) {
        setCurrentUser(user);
        await fetchProfile(user.uid, user);
        listCases().catch((err) => console.error("Initial listCases check error:", err));
      } else {
        const isDemo = localStorage.getItem("mootcourt_demo_user") === "true";
        if (isDemo) {
          setCurrentUser(DEMO_USER);
          setUserProfile(DEMO_PROFILE);
        } else {
          setCurrentUser(null);
          setUserProfile(null);
        }
      }
      setLoading(false);
    });
    return unsubscribe;
  }, [fetchProfile]);

  const loginAsDemo = useCallback(() => {
    localStorage.setItem("mootcourt_demo_user", "true");
    setCurrentUser(DEMO_USER);
    setUserProfile(DEMO_PROFILE);
  }, []);

  /** Re-fetch the profile after edits (call from ProfilePage, etc.) */
  const refreshProfile = useCallback(async () => {
    if (currentUser) {
      if (currentUser.uid === DEMO_USER.uid) {
        return;
      }
      await fetchProfile(currentUser.uid);
    }
  }, [currentUser, fetchProfile]);

  const signOut = async () => {
    localStorage.removeItem("mootcourt_demo_user");
    try {
      await logoutUser();
    } catch (e) {
      // ignore in demo mode
    }
    setCurrentUser(null);
    setUserProfile(null);
    window.location.href = "/auth";
  };

  return (
    <AuthContext.Provider value={{ currentUser, userProfile, loading, signOut, refreshProfile, loginAsDemo }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
