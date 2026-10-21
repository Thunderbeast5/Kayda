import {
  doc,
  getDoc,
  collection,
  getDocs,
  addDoc,
  updateDoc,
  query,
  where,
  orderBy,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../firebase";

// ─── Constants ────────────────────────────────────────────────────────────────

export const GAME_MODES = {
  SINGLE_PLAYER: "SINGLE_PLAYER",
  MULTIPLAYER: "MULTIPLAYER",
};

export const GAME_STATUS = {
  WAITING: "WAITING",
  IN_PROGRESS: "IN_PROGRESS",
  COMPLETED: "COMPLETED",
  ABANDONED: "ABANDONED",
};

export const PLAYER_ROLES = {
  DEFENSE: "DEFENSE",
  PROSECUTION: "PROSECUTION",
  JUDGE: "JUDGE",
};

export const PLAYER_TYPES = {
  HUMAN: "HUMAN",
  AI: "AI",
};

// ─── Game Creation ────────────────────────────────────────────────────────────

/**
 * Create a new game.
 *
 * For SINGLE_PLAYER:
 *   - Human gets the chosen role
 *   - AI fills the remaining roles (PROSECUTION + JUDGE or DEFENSE + JUDGE)
 *
 * For MULTIPLAYER (future):
 *   - Creates a WAITING game; second player joins later via matchmaking
 *
 * @param {Object} opts
 * @param {string} opts.mode        — SINGLE_PLAYER | MULTIPLAYER
 * @param {string} opts.caseId      — ID of the case to play
 * @param {string} opts.role        — Role the human player wants (DEFENSE | PROSECUTION)
 * @param {string} opts.userId      — UID of the creating player
 * @param {string} opts.displayName — Display name for the player
 * @returns {string} The created game document ID
 */
export async function createGame({ mode, caseId, role, userId, displayName }) {
  if (!db) throw new Error("Firebase is not configured.");

  const players = [];

  if (mode === GAME_MODES.SINGLE_PLAYER) {
    // Human player
    players.push({
      user_id: userId,
      role: role,
      type: PLAYER_TYPES.HUMAN,
      display_name: displayName || "Player",
    });

    // AI fills the opposite courtroom role
    const oppositeRole =
      role === PLAYER_ROLES.DEFENSE
        ? PLAYER_ROLES.PROSECUTION
        : PLAYER_ROLES.DEFENSE;

    players.push({
      role: oppositeRole,
      type: PLAYER_TYPES.AI,
      display_name: `AI ${oppositeRole.charAt(0) + oppositeRole.slice(1).toLowerCase()}`,
    });

    // AI Judge
    players.push({
      role: PLAYER_ROLES.JUDGE,
      type: PLAYER_TYPES.AI,
      display_name: "AI Judge",
    });
  } else if (mode === GAME_MODES.MULTIPLAYER) {
    // Creator joins as their chosen role; game waits for second player
    players.push({
      user_id: userId,
      role: role,
      type: PLAYER_TYPES.HUMAN,
      display_name: displayName || "Player",
    });

    // AI Judge (always AI in multiplayer too)
    players.push({
      role: PLAYER_ROLES.JUDGE,
      type: PLAYER_TYPES.AI,
      display_name: "AI Judge",
    });
  }

  const gameDoc = {
    mode,
    case_id: caseId,
    players,
    status: mode === GAME_MODES.SINGLE_PLAYER ? GAME_STATUS.IN_PROGRESS : GAME_STATUS.WAITING,
    current_turn: null,
    round: 0,
    created_by: userId,
    created_at: serverTimestamp(),
    updated_at: serverTimestamp(),
  };

  const ref = await addDoc(collection(db, "games"), gameDoc);
  return ref.id;
}

/**
 * Creates a multiplayer game directly from a finalized lobby.
 * 
 * @param {Object} lobby The finalized lobby object
 * @returns {string} The created game document ID
 */
export async function createGameFromLobby(lobby) {
  if (!db) throw new Error("Firebase is not configured.");

  const players = [
    {
      user_id: lobby.host.user_id,
      role: lobby.host.role,
      type: PLAYER_TYPES.HUMAN,
      display_name: lobby.host.display_name || "Host",
    },
    {
      user_id: lobby.guest.user_id,
      role: lobby.guest.role,
      type: PLAYER_TYPES.HUMAN,
      display_name: lobby.guest.display_name || "Guest",
    },
    {
      role: PLAYER_ROLES.JUDGE,
      type: PLAYER_TYPES.AI,
      display_name: "AI Judge",
    }
  ];

  const gameDoc = {
    mode: GAME_MODES.MULTIPLAYER,
    case_id: lobby.settings.case_id,
    players,
    status: GAME_STATUS.IN_PROGRESS,
    current_turn: null,
    round: 0,
    created_by: lobby.host.user_id,
    created_at: serverTimestamp(),
    updated_at: serverTimestamp(),
  };

  const ref = await addDoc(collection(db, "games"), gameDoc);
  return ref.id;
}

// ─── Read APIs ────────────────────────────────────────────────────────────────

/**
 * Fetch a single game by ID.
 * Returns the game object or null.
 */
export async function getGame(gameId) {
  if (!db) return null;

  const snap = await getDoc(doc(db, "games", gameId));
  if (!snap.exists()) return null;

  return { ...snap.data(), game_id: snap.id };
}

/**
 * Fetch all games the user has participated in, newest first.
 *
 * Firestore limitation: `array-contains` on a nested field doesn't work directly,
 * so we query by `created_by` as the primary filter and can expand later with
 * a `player_uids` array field for multi-user queries.
 */
export async function listMyGames(uid) {
  if (!db) return [];

  const q = query(
    collection(db, "games"),
    where("created_by", "==", uid),
    orderBy("created_at", "desc")
  );
  const snapshot = await getDocs(q);

  return snapshot.docs.map((d) => ({ ...d.data(), game_id: d.id }));
}

/**
 * List games waiting for a second player (for matchmaking).
 */
export async function listWaitingGames() {
  if (!db) return [];

  const q = query(
    collection(db, "games"),
    where("mode", "==", GAME_MODES.MULTIPLAYER),
    where("status", "==", GAME_STATUS.WAITING),
    orderBy("created_at", "desc")
  );
  const snapshot = await getDocs(q);

  return snapshot.docs.map((d) => ({ ...d.data(), game_id: d.id }));
}

// ─── Update APIs ──────────────────────────────────────────────────────────────

/**
 * Update the game's status.
 */
export async function updateGameStatus(gameId, status) {
  if (!db) throw new Error("Firebase is not configured.");

  await updateDoc(doc(db, "games", gameId), {
    status,
    updated_at: serverTimestamp(),
  });
}

/**
 * Advance the game turn.
 */
export async function advanceTurn(gameId, { currentTurn, round }) {
  if (!db) throw new Error("Firebase is not configured.");

  const updates = { updated_at: serverTimestamp() };
  if (currentTurn !== undefined) updates.current_turn = currentTurn;
  if (round !== undefined) updates.round = round;

  await updateDoc(doc(db, "games", gameId), updates);
}

/**
 * Join a multiplayer game as the second player.
 * Fills the empty opposing role and moves status to IN_PROGRESS.
 */
export async function joinGame(gameId, { userId, displayName }) {
  if (!db) throw new Error("Firebase is not configured.");

  const game = await getGame(gameId);
  if (!game) throw new Error("Game not found.");
  if (game.status !== GAME_STATUS.WAITING) throw new Error("Game is not waiting for players.");

  // Determine which role is missing
  const humanPlayer = game.players.find((p) => p.type === PLAYER_TYPES.HUMAN);
  const oppositeRole =
    humanPlayer.role === PLAYER_ROLES.DEFENSE
      ? PLAYER_ROLES.PROSECUTION
      : PLAYER_ROLES.DEFENSE;

  const updatedPlayers = [
    ...game.players,
    {
      user_id: userId,
      role: oppositeRole,
      type: PLAYER_TYPES.HUMAN,
      display_name: displayName || "Player 2",
    },
  ];

  await updateDoc(doc(db, "games", gameId), {
    players: updatedPlayers,
    status: GAME_STATUS.IN_PROGRESS,
    updated_at: serverTimestamp(),
  });
}
