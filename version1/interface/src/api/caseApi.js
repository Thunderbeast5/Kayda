import {
  doc,
  setDoc,
  getDoc,
  collection,
  getDocs,
  query,
  orderBy,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../firebase";
import { SEED_CASES } from "../data/seedCases";

// ─── Read APIs ────────────────────────────────────────────────────────────────

/**
 * Fetch all cases from Firestore, sorted by title.
 * Returns an array of case objects.
 */
export async function listCases() {
  if (!db) return [];

  const q = query(collection(db, "cases"), orderBy("title"));
  let snapshot = await getDocs(q);

  // If the collection is empty, auto-seed with default cases
  if (snapshot.empty) {
    console.log("No cases found in Firestore. Auto-seeding initial cases...");
    try {
      await seedCases();
      snapshot = await getDocs(q);
    } catch (err) {
      console.error("Auto-seeding cases failed:", err);
    }
  }

  return snapshot.docs.map((d) => ({ ...d.data(), case_id: d.id }));
}

/**
 * Fetch a single case by its ID.
 * Returns the case object or null if not found.
 */
export async function getCase(caseId) {
  if (!db) return null;

  const snap = await getDoc(doc(db, "cases", caseId));
  if (!snap.exists()) return null;

  return { ...snap.data(), case_id: snap.id };
}

// ─── Seed Utility ─────────────────────────────────────────────────────────────

/**
 * One-time utility to populate the `cases` Firestore collection with starter
 * cases from seedCases.js.
 *
 * Safe to call multiple times — uses setDoc (upsert) keyed on case_id.
 *
 * Usage (from browser console or a dev page):
 *   import { seedCases } from './api/caseApi';
 *   seedCases().then(n => console.log(`Seeded ${n} cases`));
 */
export async function seedCases() {
  if (!db) throw new Error("Firebase is not configured.");

  let count = 0;
  for (const caseData of SEED_CASES) {
    const { case_id, ...rest } = caseData;
    await setDoc(doc(db, "cases", case_id), {
      ...rest,
      created_at: serverTimestamp(),
    });
    count++;
  }

  return count;
}
