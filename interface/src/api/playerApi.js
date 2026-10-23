import { doc, getDoc, updateDoc } from "firebase/firestore";
import { ref, uploadBytes, getDownloadURL } from "firebase/storage";
import { updateProfile } from "firebase/auth";
import { db, auth } from "../firebase";
import { getStorage } from "firebase/storage";
import { DEFAULT_AVATAR, isGooglePhoto } from "../data/avatars";

// Default player fields — used to backfill old Firestore docs missing these keys
const PLAYER_DEFAULTS = {
  display_name: "",
  avatar: null,
  rating: 1200,
  games_played: 0,
  wins: 0,
  losses: 0,
  draws: 0,
  preferred_role: "defense",
};

/**
 * Fetch the full player profile, merging defaults for any missing fields.
 * Returns null if the document doesn't exist.
 */
export async function getPlayerProfile(uid) {
  if (!db) return null;
  const snap = await getDoc(doc(db, "users", uid));
  if (!snap.exists()) return null;

  const data = snap.data();

  // Merge defaults for fields that might be missing on older docs
  const profile = { ...PLAYER_DEFAULTS, ...data };

  // If display_name is still empty, derive it from legacy fields
  if (!profile.display_name) {
    profile.display_name =
      data.displayName ||
      `${data.firstName || ""} ${data.lastName || ""}`.trim() ||
      data.email ||
      "Player";
  }

  // Never expose a Google account photo as the app's profile avatar.
  if (!profile.avatar || isGooglePhoto(profile.avatar)) {
    profile.avatar = !isGooglePhoto(data.photoURL) && data.photoURL
      ? data.photoURL
      : DEFAULT_AVATAR;
  }

  return profile;
}

/**
 * Partial update — only writes the provided fields.
 * Allowed editable fields: display_name, avatar, preferred_role
 */
export async function updatePlayerProfile(uid, updates) {
  if (!db) throw new Error("Firebase is not configured.");

  // Only allow safe editable keys
  const ALLOWED = ["display_name", "avatar", "preferred_role"];
  const safe = {};
  for (const key of ALLOWED) {
    if (updates[key] !== undefined) {
      safe[key] = updates[key];
    }
  }

  if (Object.keys(safe).length === 0) return;

  if (safe.avatar) {
    safe.photoURL = safe.avatar;
  }
  await updateDoc(doc(db, "users", uid), safe);
  if (safe.avatar && auth?.currentUser?.uid === uid) {
    await updateProfile(auth.currentUser, { photoURL: safe.avatar });
  }
}

/**
 * Upload an avatar image to Firebase Storage and update the Firestore profile.
 * Returns the public download URL.
 */
export async function uploadAvatar(uid, file) {
  if (!db) throw new Error("Firebase is not configured.");

  const storage = getStorage();
  const ext = file.name.split(".").pop();
  const storageRef = ref(storage, `avatars/${uid}.${ext}`);

  await uploadBytes(storageRef, file);
  const downloadURL = await getDownloadURL(storageRef);

  // Persist URL to Firestore profile
  await updateDoc(doc(db, "users", uid), {
    avatar: downloadURL,
    photoURL: downloadURL,
  });
  if (auth?.currentUser?.uid === uid) {
    await updateProfile(auth.currentUser, { photoURL: downloadURL });
  }

  return downloadURL;
}

/**
 * Returns just the game-stats slice of the profile.
 */
export async function getPlayerStats(uid) {
  const profile = await getPlayerProfile(uid);
  if (!profile) return null;

  return {
    rating: profile.rating,
    games_played: profile.games_played,
    wins: profile.wins,
    losses: profile.losses,
    draws: profile.draws,
  };
}
