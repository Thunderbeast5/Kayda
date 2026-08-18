import { initializeApp } from "firebase/app";
import { getStorage, ref, uploadBytesResumable, getDownloadURL } from "firebase/storage";
import {
  getAuth,
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  updateProfile,
} from "firebase/auth";
import { getFirestore, doc, setDoc, getDoc, updateDoc, serverTimestamp } from "firebase/firestore";

// Web app's Firebase configuration targeting the existing backend project: mootcourt-d8d89
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: "mootcourt-d8d89.firebaseapp.com",
  projectId: "mootcourt-d8d89",
  storageBucket: "mootcourt-d8d89.appspot.com",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
};

const isConfigured = !!(firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.storageBucket);

let app = null;
let storage = null;
let auth = null;
let db = null;
let googleProvider = null;

if (isConfigured) {
  try {
    app = initializeApp(firebaseConfig);
    storage = getStorage(app);
    auth = getAuth(app);
    db = getFirestore(app);
    googleProvider = new GoogleAuthProvider();
    googleProvider.setCustomParameters({ prompt: "select_account" });
    // console.log("Firebase initialized successfully (Storage, Auth, Firestore).");
  } catch (error) {
    console.error("Failed to initialize Firebase:", error);
  }
} else {
  console.warn(
    "Firebase is NOT configured. App will run in limited demo mode.\n" +
    "Add the following to your .env file:\n" +
    "VITE_FIREBASE_API_KEY, VITE_FIREBASE_MESSAGING_SENDER_ID, VITE_FIREBASE_APP_ID"
  );
}

// ─── Auth Helpers ────────────────────────────────────────────────────────────

/**
 * Register a new user with email/password and persist extended profile to Firestore.
 */
export async function registerWithEmail({ email, password, firstName, lastName, age, mobile }) {
  if (!auth || !db) throw new Error("Firebase is not configured.");
  const cred = await createUserWithEmailAndPassword(auth, email, password);
  await updateProfile(cred.user, { displayName: `${firstName} ${lastName}` });
  await setDoc(doc(db, "users", cred.user.uid), {
    uid: cred.user.uid,
    email,
    firstName,
    lastName,
    age: Number(age),
    mobile,
    displayName: `${firstName} ${lastName}`,
    display_name: `${firstName} ${lastName}`,
    photoURL: cred.user.photoURL || null,
    avatar: cred.user.photoURL || null,
    rating: 1200,
    games_played: 0,
    wins: 0,
    losses: 0,
    draws: 0,
    preferred_role: "defense",
    createdAt: serverTimestamp(),
    provider: "email",
  });
  return cred.user;
}

/**
 * Sign in existing user with email + password.
 */
export async function loginWithEmail(email, password) {
  if (!auth) throw new Error("Firebase is not configured.");
  const cred = await signInWithEmailAndPassword(auth, email, password);
  return cred.user;
}

/**
 * Sign in / register via Google popup.
 * Requires COOP header: same-origin-allow-popups (set in vite.config.js).
 * Creates a Firestore profile doc on first sign-in.
 */
export async function loginWithGoogle() {
  if (!auth || !googleProvider || !db) throw new Error("Firebase is not configured.");
  const cred = await signInWithPopup(auth, googleProvider);
  // Create Firestore profile if this is a first-time Google sign-in
  const profileRef = doc(db, "users", cred.user.uid);
  const snap = await getDoc(profileRef);
  if (!snap.exists()) {
    const nameParts = (cred.user.displayName || "").split(" ");
    await setDoc(profileRef, {
      uid: cred.user.uid,
      email: cred.user.email,
      firstName: nameParts[0] || "",
      lastName: nameParts.slice(1).join(" ") || "",
      age: null,
      mobile: cred.user.phoneNumber || null,
      displayName: cred.user.displayName || "",
      display_name: cred.user.displayName || "",
      photoURL: cred.user.photoURL || null,
      avatar: cred.user.photoURL || null,
      rating: 1200,
      games_played: 0,
      wins: 0,
      losses: 0,
      draws: 0,
      preferred_role: "defense",
      createdAt: serverTimestamp(),
      provider: "google",
    });
  }
  return cred.user;
}

/**
 * Sign out the current user.
 */
export async function logoutUser() {
  if (!auth) throw new Error("Firebase is not configured.");
  await signOut(auth);
}

/**
 * Fetch the Firestore profile for a given uid.
 */
export async function getUserProfile(uid) {
  if (!db) return null;
  const snap = await getDoc(doc(db, "users", uid));
  return snap.exists() ? snap.data() : null;
}

/**
 * Subscribe to auth state changes.
 */
export function subscribeToAuth(callback) {
  if (!auth) return () => {};
  return onAuthStateChanged(auth, callback);
}

// ─── Storage Helper (unchanged) ───────────────────────────────────────────────

/**
 * Uploads a file (PDF) to Firebase Storage or runs a mock upload in demo mode.
 * @param {File} file - The file to upload.
 * @param {Function} onProgress - Callback for upload progress (0 to 100).
 * @returns {Promise<Object>} - Promise resolving with the file metadata and download URL.
 */
export function uploadCaseFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    // ─── Mode A: Real Firebase Upload ──────────────────────────────────────
    if (isConfigured && storage) {
      const storageRef = ref(storage, `case_briefs/${Date.now()}_${file.name}`);
      const uploadTask = uploadBytesResumable(storageRef, file);

      uploadTask.on(
        "state_changed",
        (snapshot) => {
          const progress = Math.round((snapshot.bytesTransferred / snapshot.totalBytes) * 100);
          onProgress(progress);
        },
        (error) => {
          console.error("Firebase upload failed:", error);
          reject(error);
        },
        () => {
          getDownloadURL(uploadTask.snapshot.ref).then((downloadURL) => {
            resolve({
              success: true,
              filename: file.name,
              url: downloadURL,
              mode: "firebase",
            });
          });
        }
      );
    }
    // ─── Mode B: Simulated Demo Upload ─────────────────────────────────────
    else {
      let progress = 0;
      const interval = setInterval(() => {
        progress += Math.floor(Math.random() * 15) + 5;
        if (progress >= 100) {
          progress = 100;
          clearInterval(interval);
          onProgress(100);
          setTimeout(() => {
            resolve({
              success: true,
              filename: file.name,
              url: "#mock-firebase-storage-url/" + file.name,
              mode: "simulated",
            });
          }, 400);
        } else {
          onProgress(progress);
        }
      }, 100);
    }
  });
}

export { auth, db, googleProvider };
