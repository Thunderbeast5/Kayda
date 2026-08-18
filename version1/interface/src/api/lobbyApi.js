import {
  doc,
  setDoc,
  getDoc,
  updateDoc,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../firebase";
import { createGameFromLobby } from "./gameApi";

// ─── Constants ────────────────────────────────────────────────────────────────

export const LOBBY_STATUS = {
  WAITING: "WAITING",
  PLAYER_JOINED: "PLAYER_JOINED",
  READY: "READY",
  STARTED: "STARTED",
  COMPLETED: "COMPLETED",
};

// ─── Utility ──────────────────────────────────────────────────────────────────

function generateLobbyId() {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let result = "L";
  for (let i = 0; i < 5; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// ─── Lobby API ────────────────────────────────────────────────────────────────

/**
 * Creates a new multiplayer lobby.
 */
export async function createLobby(hostId, hostRole, hostDisplayName) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobbyId = generateLobbyId();

  const lobbyData = {
    lobby_id: lobbyId,
    host: {
      user_id: hostId,
      role: hostRole || null,
      display_name: hostDisplayName || "Host",
      ready: false,
    },
    guest: {
      user_id: null,
      role: null,
      display_name: null,
      ready: false,
    },
    status: LOBBY_STATUS.WAITING,
    settings: {
      case_id: null,
      game_id: null,
    },
    created_at: serverTimestamp(),
    updated_at: serverTimestamp(),
  };

  await setDoc(doc(db, "lobbies", lobbyId), lobbyData);
  return lobbyId;
}

/**
 * Gets the current state of a lobby.
 */
export async function getLobby(lobbyId) {
  if (!db) return null;

  const snap = await getDoc(doc(db, "lobbies", lobbyId));
  if (!snap.exists()) return null;

  return { ...snap.data() };
}

/**
 * Guest joins the lobby.
 */
export async function joinLobby(lobbyId, guestId, guestRole, guestDisplayName) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobby = await getLobby(lobbyId);
  if (!lobby) throw new Error("Lobby not found.");
  if (lobby.guest.user_id && lobby.guest.user_id !== guestId) {
    throw new Error("Lobby is already full.");
  }

  // Ensure guest isn't picking the same role as host if roles are specified
  if (guestRole && lobby.host.role && guestRole === lobby.host.role) {
    throw new Error(`The role ${guestRole} is already taken by the host.`);
  }

  const updates = {
    "guest.user_id": guestId,
    "guest.role": guestRole || null,
    "guest.display_name": guestDisplayName || "Guest",
    status: LOBBY_STATUS.PLAYER_JOINED,
    updated_at: serverTimestamp(),
  };

  await updateDoc(doc(db, "lobbies", lobbyId), updates);
}

/**
 * Sets the case for the lobby (usually by the host).
 */
export async function setLobbyCase(lobbyId, caseId) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobby = await getLobby(lobbyId);
  if (!lobby) throw new Error("Lobby not found.");
  if (lobby.status === LOBBY_STATUS.STARTED || lobby.status === LOBBY_STATUS.COMPLETED) {
    throw new Error("Cannot change case after game has started.");
  }

  // Changing case un-readies everyone to ensure they agree
  await updateDoc(doc(db, "lobbies", lobbyId), {
    "settings.case_id": caseId,
    "host.ready": false,
    "guest.ready": false,
    status: lobby.guest.user_id ? LOBBY_STATUS.PLAYER_JOINED : LOBBY_STATUS.WAITING,
    updated_at: serverTimestamp(),
  });
}

/**
 * Update user role in the lobby.
 */
export async function updateLobbyRole(lobbyId, userId, newRole) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobby = await getLobby(lobbyId);
  if (!lobby) throw new Error("Lobby not found.");
  if (lobby.status === LOBBY_STATUS.STARTED) {
    throw new Error("Cannot change role after game has started.");
  }

  let isHost = false;
  if (lobby.host.user_id === userId) {
    isHost = true;
  } else if (lobby.guest.user_id === userId) {
    isHost = false;
  } else {
    throw new Error("User is not in this lobby.");
  }

  // Check collision
  if (isHost && lobby.guest.role === newRole) {
     throw new Error(`The role ${newRole} is already taken by the guest.`);
  }
  if (!isHost && lobby.host.role === newRole) {
     throw new Error(`The role ${newRole} is already taken by the host.`);
  }

  const updates = {
    updated_at: serverTimestamp(),
  };

  // Un-ready everyone if roles change
  updates["host.ready"] = false;
  updates["guest.ready"] = false;
  updates["status"] = lobby.guest.user_id ? LOBBY_STATUS.PLAYER_JOINED : LOBBY_STATUS.WAITING;

  if (isHost) {
    updates["host.role"] = newRole;
  } else {
    updates["guest.role"] = newRole;
  }

  await updateDoc(doc(db, "lobbies", lobbyId), updates);
}

/**
 * Mark a user as ready or unready.
 * If both become ready, transitions status to READY.
 */
export async function setReady(lobbyId, userId, isReady) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobby = await getLobby(lobbyId);
  if (!lobby) throw new Error("Lobby not found.");

  let isHost = false;
  if (lobby.host.user_id === userId) {
    isHost = true;
  } else if (lobby.guest.user_id === userId) {
    isHost = false;
  } else {
    throw new Error("User is not in this lobby.");
  }

  const newHostReady = isHost ? isReady : lobby.host.ready;
  const newGuestReady = !isHost ? isReady : lobby.guest.ready;

  let newStatus = lobby.status;
  
  if (newHostReady && newGuestReady) {
    if (!lobby.settings.case_id) {
       throw new Error("Cannot ready up: No case selected.");
    }
    const finalHostRole = lobby.host.role; 
    const finalGuestRole = lobby.guest.role;

    if (!finalHostRole || !finalGuestRole) {
       throw new Error("Cannot ready up: Both players must select a role.");
    }
    if (finalHostRole === finalGuestRole) {
       throw new Error("Cannot ready up: Players must select different roles.");
    }

    newStatus = LOBBY_STATUS.READY;
  } else if (lobby.guest.user_id) {
    newStatus = LOBBY_STATUS.PLAYER_JOINED;
  } else {
    newStatus = LOBBY_STATUS.WAITING;
  }

  const updates = {
    updated_at: serverTimestamp(),
    status: newStatus,
  };

  if (isHost) {
    updates["host.ready"] = isReady;
  } else {
    updates["guest.ready"] = isReady;
  }

  await updateDoc(doc(db, "lobbies", lobbyId), updates);
}

/**
 * Starts the game. Only allowed if status is READY.
 * Creates the actual Game document and links it.
 */
export async function startGame(lobbyId) {
  if (!db) throw new Error("Firebase is not configured.");

  const lobby = await getLobby(lobbyId);
  if (!lobby) throw new Error("Lobby not found.");
  if (lobby.status !== LOBBY_STATUS.READY) {
    throw new Error("Both players must be ready to start the game.");
  }

  if (!lobby.settings.case_id || !lobby.host.role || !lobby.guest.role) {
     throw new Error("Missing case or roles.");
  }

  // Create the actual Game document
  const gameId = await createGameFromLobby(lobby);

  // Update lobby status to started and link game
  await updateDoc(doc(db, "lobbies", lobbyId), {
    status: LOBBY_STATUS.STARTED,
    "settings.game_id": gameId,
    updated_at: serverTimestamp(),
  });

  return gameId;
}
