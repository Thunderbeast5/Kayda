import { initializeApp } from "firebase/app";
import { getStorage, ref, uploadBytesResumable, getDownloadURL } from "firebase/storage";

// Web app's Firebase configuration targeting the existing backend project: mootcourt-d8d89
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: "mootcourt-d8d89.firebaseapp.com",
  projectId: "mootcourt-d8d89",
  storageBucket: "mootcourt-d8d89.appspot.com",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || ""
};

const isConfigured = !!(firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.storageBucket);

let app = null;
let storage = null;

if (isConfigured) {
  try {
    app = initializeApp(firebaseConfig);
    storage = getStorage(app);
    console.log("Firebase Storage initialized successfully.");
  } catch (error) {
    console.error("Failed to initialize Firebase:", error);
  }
} else {
  console.warn(
    "Firebase is NOT configured. File uploads will run in Simulated Demo Mode.\n" +
    "To connect to your live database, add the following environment variables to your .env file:\n" +
    "VITE_FIREBASE_API_KEY, VITE_FIREBASE_PROJECT_ID, VITE_FIREBASE_STORAGE_BUCKET"
  );
}

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
              mode: "firebase"
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
              mode: "simulated"
            });
          }, 400);
        } else {
          onProgress(progress);
        }
      }, 100);
    }
  });
}
