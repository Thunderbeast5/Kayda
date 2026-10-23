import { createContext, useContext, useEffect, useState, useCallback } from "react";
import {
  subscribeToAuth,
  logoutUser,
  ensureUserAvatar,
} from "../firebase";
import { getPlayerProfile } from "../api/playerApi";
import { listCases } from "../api/caseApi";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async (uid, user = null) => {
    try {
      if (user) await ensureUserAvatar(user);
      const profile = await getPlayerProfile(uid);
      setUserProfile(profile);
    } catch (err) {
      console.error("[AuthContext] fetchProfile error:", err);
      setUserProfile(null);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToAuth((user) => {
      setCurrentUser(user);
      setLoading(false);
      if (user) {
        setUserProfile(null);
        fetchProfile(user.uid, user);
        // Auto-seed/verify cases collection in Firestore
        listCases().catch((err) => console.error("Initial listCases check error:", err));
      } else {
        setUserProfile(null);
      }
    });
    return unsubscribe;
  }, [fetchProfile]);

  /** Re-fetch the profile after edits (call from ProfilePage, etc.) */
  const refreshProfile = useCallback(async () => {
    if (currentUser) {
      await fetchProfile(currentUser.uid);
    }
  }, [currentUser, fetchProfile]);

  const signOut = async () => {
    await logoutUser();
    setCurrentUser(null);
    setUserProfile(null);
    // Navigate to auth page after sign out
    window.location.href = "/auth";
  };

  return (
    <AuthContext.Provider value={{ currentUser, userProfile, loading, signOut, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
