# Kayda — Real-Time Multiplayer Moot Court System
## Full Architecture & Technical Documentation

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Module-by-Module Breakdown](#4-module-by-module-breakdown)
   - 4.1 Authentication
   - 4.2 Player Profile
   - 4.3 Matchmaking
   - 4.4 Game Session
   - 4.5 WebSocket Layer
   - 4.6 Game Engine
   - 4.7 Turn Manager
   - 4.8 Frontend Courtroom Interface
5. [Complete Data Flow — One Full Game](#5-complete-data-flow--one-full-game)
6. [Firestore Data Model](#6-firestore-data-model)
7. [Redis Data Model](#7-redis-data-model)
8. [WebSocket Event Reference](#8-websocket-event-reference)
9. [Phase & Turn System](#9-phase--turn-system)
10. [What is Implemented](#10-what-is-implemented)
11. [What Remains to be Implemented](#11-what-remains-to-be-implemented)
12. [Known Bugs Fixed](#12-known-bugs-fixed)

---

## 1. System Overview

Kayda is a **real-time, turn-based, multiplayer moot court simulation** platform.

Two human players are matched and placed into a live virtual courtroom. One plays as **Prosecution**, the other as **Defense**. They argue a real case from Indian law, taking turns in structured phases (Opening → Argument → Rebuttal → Judgment). An **AI Judge** (not yet integrated) will evaluate every argument and deliver a final verdict.

The system is **server-authoritative** — all game logic, turn management, and validation happen **only on the backend**. The frontend is a "dumb terminal" that sends actions and reacts to server events. The frontend never decides whose turn it is, what phase it is, or whether an action is valid.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 + Vite | Single-page application |
| **Frontend State** | React useState / Context | Auth, profile, courtroom state |
| **Real-time** | WebSocket (native browser API) | Live game events |
| **Backend Framework** | FastAPI (Python) | REST API + WebSocket server |
| **Authentication** | Firebase Auth | Google SSO + Email/Password |
| **User Profiles** | Firestore (`users` collection) | Player rating, stats, display name |
| **Game Sessions** | Firestore (`games` collection) | Persistent game state & event log |
| **Live Game State** | Redis (in-memory) | Ultra-fast turn/phase state during active game |
| **Matchmaking Queue** | Redis (sorted set + hash) | Pairing players by role & rating |
| **Cases** | Firestore (`cases` collection) | Real Indian law case data |
| **AI Agent** | Gemini / Vertex AI | (Planned) Evidence analysis + AI Judge |

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     BROWSER (React)                      │
│                                                          │
│  AuthContext ──► Firebase Auth ──► Firestore (users)    │
│      │                                                   │
│  LandingPage ──► RoleSelector ──► MatchmakingQueue      │
│                                        │                 │
│                            HTTP POST /api/matchmaking/join│
│                                        │                 │
│  CourtroomInterface ◄── WebSocket ─────┘                 │
│      │                 ws://localhost:5001/ws/games/{id} │
│      └── HTTP POST /api/games/{id}/ready                │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────┐
│                   FASTAPI BACKEND                        │
│                                                          │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │ Matchmaking API  │  │      Game API               │  │
│  │ /api/matchmaking │  │  /api/games/{id}            │  │
│  │ /join            │  │  /api/games/{id}/ready      │  │
│  │ /leave           │  │  /ws/games/{id}  (WS)       │  │
│  │ /status          │  └────────────┬────────────────┘  │
│  └──────┬───────────┘               │                   │
│         │                    GameConnectionManager       │
│  ┌──────▼───────────┐        (in-memory WS registry)    │
│  │ Matchmaking       │               │                   │
│  │ Worker (asyncio)  │        ┌──────▼──────────┐        │
│  │ Runs every 2s     │        │  Game Engine    │        │
│  └──────┬───────────┘        │  process_action │        │
│         │                    └──────┬──────────┘        │
│         │                           │                   │
│  ┌──────▼─────────────────────┐    │                   │
│  │         REDIS              │◄───┘                   │
│  │  matchmaking:queue (zset)  │                        │
│  │  matchmaking:user:{uid}    │  game:{id} (JSON state)│
│  └────────────────────────────┘                        │
│                                                          │
│  ┌──────────────────────────────┐                       │
│  │        FIRESTORE             │                       │
│  │  users/{uid}                 │                       │
│  │  games/{game_id}             │                       │
│  │  games/{id}/events/…         │                       │
│  │  cases/{case_id}             │                       │
│  └──────────────────────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Module-by-Module Breakdown

### 4.1 Authentication

**Files:** `backend/firebase.js`, `src/context/AuthContext.jsx`, `src/pages/AuthPage.jsx`

Firebase Auth manages identity. Two flows are supported:

- **Email + Password** — `registerWithEmail()` calls `createUserWithEmailAndPassword` and then writes a full profile doc to Firestore `users/{uid}`.
- **Google OAuth** — `loginWithGoogle()` calls `signInWithPopup`. If the user doc doesn't exist in Firestore, it creates one with defaults (rating: 1200, games: 0, etc.).

`AuthContext` wraps the entire app in a React context. It:
1. Subscribes to `onAuthStateChanged` from Firebase.
2. When a user logs in, immediately calls `getPlayerProfile(uid)` from Firestore.
3. **If no profile doc exists** (old accounts or missed registration), auto-creates one so the profile page never hangs.
4. Exposes `currentUser`, `userProfile`, `loading`, `signOut`, `refreshProfile` to all components.

> **Key Rule:** Any component that needs identity calls `useAuth()`. Nothing reads Firebase directly.

---

### 4.2 Player Profile

**Files:** `src/api/playerApi.js`, `src/pages/ProfilePage.jsx`

Each user has a document in `Firestore → users/{uid}`:

```json
{
  "uid": "abc123",
  "email": "user@example.com",
  "display_name": "Arjun Sharma",
  "firstName": "Arjun",
  "lastName": "Sharma",
  "rating": 1200,
  "games_played": 0,
  "wins": 0,
  "losses": 0,
  "draws": 0,
  "preferred_role": "defense",
  "avatar": null,
  "photoURL": null,
  "provider": "email",
  "createdAt": "<timestamp>"
}
```

The `rating` field (ELO-style, starting at 1200) is used for **matchmaking** — only players within 200 rating points are paired (relaxes to ANY after 30s wait).

`ProfilePage` reads `userProfile` from AuthContext and renders:
- Avatar + display name + rating
- Win/loss/draw ring chart
- Animated stat counters
- Editable display name and preferred role

---

### 4.3 Matchmaking

**Files:** `backend/matchmaking/api.py`, `backend/matchmaking/worker.py`, `backend/matchmaking/redis_client.py`, `src/api/matchmakingApi.js`, `src/components/landing/MatchmakingQueue.jsx`

This is a **polling-based matchmaking system** backed by Redis.

#### How a player joins:

1. Player clicks "Public Prosecutor" or "Defense Counsel" card in `RoleSelector.jsx`.
2. `MatchmakingQueue.jsx` mounts and immediately calls `joinMatchmakingQueue(userId, username, role, rating)`.
3. The role is **normalized** before sending: `"prosecutor"` → `"PROSECUTION"`, `"defense"` → `"DEFENSE"` (this was a critical bug fix — the raw UI label was being sent directly).
4. Backend `POST /api/matchmaking/join` stores the user in Redis:

```
Redis Hash:   matchmaking:user:{user_id}
  user_id, username, rating, preferred_role, joined_at, status="WAITING"

Redis Sorted Set:  matchmaking:queue
  member={user_id}, score={joined_at_timestamp}
```

5. Frontend polls `GET /api/matchmaking/status?user_id={uid}` every **2 seconds**.

#### How matching works (the Worker):

A background `asyncio` task (`matchmaking_loop`) runs inside the same FastAPI process, waking up every 2 seconds:

```python
async def matchmaking_loop():
    while True:
        await match_players()
        await asyncio.sleep(2)
```

`match_players()` reads all `WAITING` users from Redis and tries to pair them:

| Condition | Logic |
|-----------|-------|
| Same user | Skip |
| Role compatibility | PROSECUTION + DEFENSE → direct match |
| One is ANY | Assign the complement |
| Both ANY | Random assignment |
| Same strict role | Wait 30 seconds, then relax and assign randomly |

> **Why the 30-second relaxation?** In testing, two users from the same browser opened both as "defense". Without relaxation they would never match. After 30 seconds the system assigns one as prosecution anyway.

Once a pair is found:
1. Both removed from Redis queue.
2. A random case is selected from Firestore `cases`.
3. A `games` document is created in Firestore with `status: "WAITING_FOR_PLAYERS"`.
4. Both users' Redis hashes are updated: `status: "MATCH_FOUND"`, `game_id`, `your_role`, `opponent` info.
5. Next time the frontend polls, it gets `status: "MATCH_FOUND"` and redirects to the courtroom.

---

### 4.4 Game Session

**File:** `backend/matchmaking/worker.py` (creation), `backend/game/api.py` (management)

When a match is found, a Firestore `games` document is created:

```json
{
  "game_id": "0FaPjRxoikLZN1TE2XTv",
  "mode": "MULTIPLAYER",
  "case_id": "5",
  "status": "WAITING_FOR_PLAYERS",
  "phase": "CASE_INTRO",
  "current_turn": null,
  "round": 0,
  "created_by": "matchmaker",
  "players": [
    {
      "user_id": "JxzgDMhbjsh...",
      "display_name": "Arjun Sharma",
      "role": "PROSECUTION",
      "type": "HUMAN",
      "status": "WAITING"
    },
    {
      "user_id": "PvHwepBZtu...",
      "display_name": "Priya Nair",
      "role": "DEFENSE",
      "type": "HUMAN",
      "status": "WAITING"
    },
    {
      "role": "JUDGE",
      "type": "AI",
      "display_name": "AI Judge",
      "status": "READY"
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

**Game Lifecycle:**

```
WAITING_FOR_PLAYERS
        ↓  (both players connected + called /ready)
      ACTIVE
        ↓  (all phases completed)
     COMPLETED
```

---

### 4.5 WebSocket Layer

**Files:** `backend/game/api.py` (endpoint), `backend/game/manager.py` (registry)

The WebSocket endpoint is `ws://localhost:5001/ws/games/{game_id}?user_id={uid}`.

#### GameConnectionManager (manager.py)

An in-memory Python object that maps `game_id → { user_id → WebSocket }`:

```python
active_games: {
  "0FaPjRxo...": {
    "JxzgDM...": <WebSocket>,
    "PvHwep...": <WebSocket>
  }
}
```

`broadcast(game_id, message)` sends the same JSON message to **every** player in that game simultaneously.

#### Connection Lifecycle:

```
Client opens ws://…/ws/games/{id}?user_id={uid}
        ↓
Backend: verify user is in this game (reads Firestore)
        ↓ (if valid)
manager.connect(ws, game_id, user_id)  →  ws.accept()
        ↓
broadcast: { type: "PLAYER_CONNECTED", player: { user_id } }
        ↓
Client calls POST /api/games/{id}/ready?user_id={uid}
        ↓
Firestore transaction: mark player as READY
        ↓
broadcast: { type: "PLAYER_READY", player: { user_id } }
        ↓
[If all human players READY]
  → init_game_state() in Redis
  → broadcast: { type: "GAME_STARTED", phase, current_turn, scores }
```

#### Why a Firestore Transaction for /ready?

Both players call `/ready` simultaneously (race condition). Without a transaction, both could read the Firestore doc at the same time, see only themselves as READY, and neither would trigger `GAME_STARTED`. Using `@firestore.transactional`, one call wins the lock, updates, and the second one picks up the already-updated state.

#### React StrictMode Double-Mount Fix:

React 18 StrictMode mounts components **twice** in development (to catch side effects). This caused the WebSocket to be created, immediately closed by the cleanup function, and then show a browser error.

**Fix:** Wrap WS creation in `setTimeout(0)`. StrictMode's cleanup fires **synchronously**, so it calls `clearTimeout` before the next tick fires. The phantom first mount never creates a socket. The real second mount creates it normally.

```javascript
const timer = setTimeout(() => {
  ws = new WebSocket(wsUrl);
  // ...setup handlers
}, 0);

return () => {
  clearTimeout(timer);  // cancels phantom mount
  if (ws) ws.close();
};
```

---

### 4.6 Game Engine

**File:** `backend/game/engine/engine.py`

`GameEngine.process_action(game_id, user_id, action_payload)` is the heart of the game. Called every time a player sends a WebSocket message.

It returns: `(success, error_message, new_state, event_to_broadcast)`

**Validation steps:**
1. Load live state from Redis (`get_game_state`)
2. Check `status == "ACTIVE"`
3. Check `action_payload["action"]` exists
4. For turn-required actions, check `current_turn == user_id`
5. For submission actions, check the phase matches (e.g., `SUBMIT_OPENING` requires `phase == "OPENING"`)

**Supported actions:**

| Action | Phase Required | Turn Required |
|--------|---------------|--------------|
| `END_TURN` | CASE_INTRO | Yes |
| `SUBMIT_OPENING` | OPENING | Yes |
| `SUBMIT_ARGUMENT` | ARGUMENT | Yes |
| `SUBMIT_REBUTTAL` | REBUTTAL | Yes |

After a valid action:
1. **Record event** in Firestore `games/{id}/events` subcollection (fire-and-forget in thread pool)
2. **advance_turn()** — move to next player or next phase
3. **update_game_state()** — overwrite Redis
4. **sync_to_firestore_sync()** — update core fields in Firestore (fire-and-forget)
5. Return `event_to_broadcast` → caller broadcasts it to all players

---

### 4.7 Turn Manager

**File:** `backend/game/engine/turn_manager.py`

Controls the full lifecycle of phases and turns.

**Phase Sequence:**
```
CASE_INTRO → OPENING → ARGUMENT → REBUTTAL → JUDGMENT → COMPLETED
```

**Turn Order per Phase:**

| Phase | Turn Order |
|-------|-----------|
| CASE_INTRO | prosecution only (then END_TURN → advance phase) |
| OPENING | prosecution → defense |
| ARGUMENT | prosecution → defense |
| REBUTTAL | defense → prosecution |
| JUDGMENT | AI Judge only (no human turns) |
| COMPLETED | — |

`advance_turn(state)`:
- Finds current player's index in the phase's turn order
- If next player exists in same phase → switch to them
- If we've exhausted the order → call `_advance_phase(state)`

`_advance_phase(state)`:
- Looks up current phase in `PHASES` list
- Moves to next, sets `current_turn` to the first player of the new phase
- If `COMPLETED`, sets `status = "COMPLETED"` and clears turn

---

### 4.8 Frontend Courtroom Interface

**File:** `src/components/courtroom/CourtroomInterface.jsx`

Key state variables:

| State | Source | Purpose |
|-------|--------|---------|
| `messages` | `ACTION_SUBMITTED` WS events | Chat transcript |
| `activeSpeaker` | WS events → derived from `current_turn` | Who is highlighted on stage |
| `trialPhase` | WS events (`GAME_STARTED`, `TURN_CHANGED`) | Current phase (server truth) |
| `status` | `GAME_STARTED` | "idle" / "running" / "completed" |
| `userId` | Firebase Auth (`currentUser.uid`) | This player's identity |
| `wsRef` | useRef | Persistent WS reference across renders |

**Turn Detection:**
```javascript
isMyTurn = (gameId)
  ? activeSpeaker === userRole   // multiplayer: my role is speaking
  : activeSpeaker === null       // single-player: no AI agent is speaking
```

**Submitting an action:**
1. Input bar uses `isMyTurn` to enable/disable. When disabled: `"Opposing counsel is presenting..."`. When enabled: phase-appropriate prompt.
2. On submit, the `trialPhase` (from server) maps to the correct action:
   - `CASE_INTRO` → `END_TURN`
   - `OPENING` → `SUBMIT_OPENING`
   - `ARGUMENT` → `SUBMIT_ARGUMENT`
   - `REBUTTAL` → `SUBMIT_REBUTTAL`
3. Message is sent via `wsRef.current.send(JSON.stringify({ action, text }))`.
4. **No local optimistic update** — the message only appears when the `ACTION_SUBMITTED` broadcast comes back from the server. This ensures both players see it at the same moment.

---

## 5. Complete Data Flow — One Full Game

```
STEP 1: AUTHENTICATION
  User signs in via Firebase Auth
  → AuthContext fetches Firestore user profile
  → If no profile, auto-creates one

STEP 2: ROLE SELECTION
  User clicks "Public Prosecutor" on LandingPage
  → MatchmakingQueue mounts with preferredRole="prosecutor"
  → Role normalized: "prosecutor" → "PROSECUTION"
  → POST /api/matchmaking/join
  → Redis: matchmaking:user:{uid} = { status: WAITING, preferred_role: PROSECUTION, ... }
  → Redis: matchmaking:queue.add(uid, score=joinTime)

STEP 3: MATCHING (background worker, every 2s)
  matchmaking_loop() wakes up
  → reads all WAITING users from Redis
  → finds PROSECUTION + DEFENSE pair
  → creates games/{id} in Firestore (status: WAITING_FOR_PLAYERS)
  → updates both users' Redis hashes: status=MATCH_FOUND, game_id, your_role, opponent

STEP 4: FRONTEND DETECTS MATCH
  Poll returns status="MATCH_FOUND"
  → MatchmakingQueue shows "Match Found!" screen
  → After 2.5s, calls onMatchFound(game_id, assigned_role)
  → CourtroomInterface mounts with gameId + userRole

STEP 5: WEBSOCKET HANDSHAKE
  setTimeout(0) fires → new WebSocket(ws://…/ws/games/{id}?user_id={uid})
  → Backend: verify user is in game (Firestore lookup)
  → manager.connect() → ws.accept()
  → broadcast: PLAYER_CONNECTED
  → ws.onopen → POST /api/games/{id}/ready?user_id={uid}

STEP 6: GAME START (Firestore Transaction)
  /ready called by Player 1 (Firestore tx):
    - marks player 1 as READY
    - all_ready = False
  → broadcast: PLAYER_READY (player 1)

  /ready called by Player 2 (Firestore tx):
    - marks player 2 as READY
    - AI Judge is auto-READY
    - all_ready = True → sets status=ACTIVE, phase=CASE_INTRO
  → init_game_state() in Redis
  → broadcast: GAME_STARTED { phase: CASE_INTRO, current_turn: <prosecution_uid>, scores: {0,0} }

STEP 7: TURN TAKING
  Prosecution's browser:
    - isMyTurn = true (activeSpeaker = "prosecutor")
    - Input bar enabled: "Court is in session — begin when ready"
    - Player presses Send
    → WS send: { action: "END_TURN", text: "" }

  Backend receives END_TURN:
    - advance_turn() → CASE_INTRO has no more players → _advance_phase()
    - phase becomes OPENING, current_turn = prosecution_uid
    - broadcast: TURN_CHANGED { phase: OPENING, current_turn: prosecution_uid }

  Prosecution types opening statement, presses Send
    → WS send: { action: "SUBMIT_OPENING", text: "Your Honor, the evidence shows..." }

  Backend receives SUBMIT_OPENING:
    - validates phase == OPENING ✓
    - validates current_turn == user_id ✓
    - records event in Firestore games/{id}/events
    - advance_turn() → next is defense
    - update Redis state
    - broadcast: ACTION_SUBMITTED { action, player_id, payload: { content }, next_turn, phase }

  BOTH browsers receive ACTION_SUBMITTED:
    - handleEvent() adds message to chat for BOTH players simultaneously
    - Defense's input unlocks

STEP 8: PHASE COMPLETION
  After both players submit OPENING:
    - advance_turn() exhausts order → _advance_phase()
    - phase: ARGUMENT
    - broadcast: ACTION_SUBMITTED with new phase

  [ARGUMENT, REBUTTAL phases repeat similarly]

STEP 9: JUDGMENT (not yet implemented)
  After REBUTTAL completes → phase becomes JUDGMENT
  AI Judge evaluates all submitted arguments
  Delivers verdict
  → phase: COMPLETED, status: COMPLETED

STEP 10: GAME OVER
  broadcast: GAME_COMPLETED { winner, scores }
  Both players see result screen
  Firestore updates: wins/losses/ratings
```

---

## 6. Firestore Data Model

### `users/{uid}`
```json
{
  "uid": "string",
  "email": "string",
  "display_name": "string",
  "firstName": "string",
  "lastName": "string",
  "rating": 1200,
  "games_played": 0,
  "wins": 0,
  "losses": 0,
  "draws": 0,
  "preferred_role": "defense | prosecution",
  "avatar": "url | null",
  "photoURL": "url | null",
  "provider": "email | google",
  "createdAt": "timestamp"
}
```

### `games/{game_id}`
```json
{
  "mode": "MULTIPLAYER",
  "case_id": "string",
  "status": "WAITING_FOR_PLAYERS | ACTIVE | COMPLETED",
  "phase": "CASE_INTRO | OPENING | ARGUMENT | REBUTTAL | JUDGMENT | COMPLETED",
  "current_turn": "uid | null",
  "round": 1,
  "created_by": "matchmaker",
  "players": [
    {
      "user_id": "uid",
      "display_name": "string",
      "role": "PROSECUTION | DEFENSE | JUDGE",
      "type": "HUMAN | AI",
      "status": "WAITING | READY"
    }
  ],
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### `games/{game_id}/events/{event_id}`
Every player action is recorded here for audit trail and future AI evaluation:
```json
{
  "event_id": "EVT_abc12345",
  "user_id": "uid",
  "type": "SUBMIT_OPENING | SUBMIT_ARGUMENT | SUBMIT_REBUTTAL | END_TURN",
  "payload": { "content": "Your Honor, the defendant..." },
  "round": 1,
  "phase": "OPENING",
  "timestamp": "timestamp"
}
```

### `cases/{case_id}`
```json
{
  "id": "5",
  "title": "Sasikala Pushpa vs. State of Tamil Nadu",
  "fir_no": "LAWS(SC)-2019-5-25",
  "charge": "S.438 CrPC / IPC 193",
  "description": "...",
  "evidence": []
}
```

---

## 7. Redis Data Model

### Matchmaking Queue
```
Key:  matchmaking:queue          (Sorted Set)
      member = user_id
      score  = join_timestamp    → ordered oldest-first

Key:  matchmaking:user:{uid}     (Hash)
      user_id        = "uid"
      username       = "Arjun"
      rating         = "1200"
      preferred_role = "PROSECUTION"
      joined_at      = "1724395234.5"
      status         = "WAITING" | "MATCH_FOUND"
      game_id        = "0FaPj..."    (set on match)
      your_role      = "PROSECUTION" (set on match)
      opponent       = '{"username":"Priya","rating":1200}' (JSON string)
```

### Live Game State
```
Key:  game:{game_id}             (String → JSON)
{
  "game_id": "0FaPj...",
  "phase": "OPENING",
  "round": 1,
  "current_turn": "JxzgDM...",
  "players": {
    "prosecution": "JxzgDM...",
    "defense": "PvHwep..."
  },
  "scores": {
    "prosecution": 0,
    "defense": 0
  },
  "turn": {
    "player_id": "JxzgDM...",
    "started_at": 1724395234.5,
    "time_remaining": 120
  },
  "status": "ACTIVE"
}
```

**Why Redis for live state?**
- Firestore reads are ~50-100ms with network overhead.
- Redis reads are ~0.1ms (in-memory, same machine).
- Every player action needs an immediate state check (is it your turn? is the phase right?). Redis makes this near-instant.
- Firestore is only updated as an async background task for persistence.

---

## 8. WebSocket Event Reference

All events are JSON objects with a `type` field.

### Server → Client Events

| Event Type | When Sent | Payload |
|-----------|-----------|---------|
| `PLAYER_CONNECTED` | A player's WS connects | `{ player: { user_id } }` |
| `PLAYER_DISCONNECTED` | A player's WS drops | `{ player: { user_id } }` |
| `PLAYER_READY` | A player calls /ready | `{ player: { user_id } }` |
| `GAME_STARTED` | All players ready | `{ game_id, phase, current_turn, scores }` |
| `TURN_CHANGED` | END_TURN or phase advance | `{ current_turn, phase }` |
| `ACTION_SUBMITTED` | Valid player action processed | `{ action, player_id, payload: { content }, next_turn, phase }` |
| `JUDGE_RULING` | *(Planned)* AI judge evaluates | `{ ruling, score_delta, next_turn }` |
| `GAME_COMPLETED` | *(Planned)* All phases done | `{ winner, scores, verdict }` |
| `ERROR` | Invalid action received | `{ message }` |

### Client → Server Events

| Action | When Sent | Payload |
|--------|-----------|---------|
| `END_TURN` | CASE_INTRO phase, player ready | `{ action: "END_TURN", text: "" }` |
| `SUBMIT_OPENING` | OPENING phase, player's turn | `{ action: "SUBMIT_OPENING", text: "..." }` |
| `SUBMIT_ARGUMENT` | ARGUMENT phase, player's turn | `{ action: "SUBMIT_ARGUMENT", text: "..." }` |
| `SUBMIT_REBUTTAL` | REBUTTAL phase, player's turn | `{ action: "SUBMIT_REBUTTAL", text: "..." }` |

---

## 9. Phase & Turn System

```
Phase: CASE_INTRO
  Turn order: [prosecution]
  Action: END_TURN → advances to OPENING
  Purpose: Both players arrive and read the case details.

Phase: OPENING
  Turn order: [prosecution, defense]
  Action: SUBMIT_OPENING
  Purpose: Each counsel delivers their opening statement.

Phase: ARGUMENT
  Turn order: [prosecution, defense]
  Action: SUBMIT_ARGUMENT
  Purpose: Core arguments and evidence presentation.

Phase: REBUTTAL
  Turn order: [defense, prosecution]
  Action: SUBMIT_REBUTTAL
  Purpose: Defense rebuts first (as challenger), then prosecution.

Phase: JUDGMENT  ← NOT YET IMPLEMENTED
  Turn order: [] (AI Judge only)
  Action: AI evaluates all events from games/{id}/events
  Purpose: Deliver scored verdict.

Phase: COMPLETED
  Turn order: []
  status: "COMPLETED"
  Purpose: Game over. Show results.
```

---

## 10. What is Implemented

### ✅ Authentication
- Email + password registration with full profile creation
- Google OAuth sign-in with auto-profile creation
- Auto-creation of missing profile docs on login (handles old/legacy accounts)
- AuthContext with global state management

### ✅ Player Profile
- Firestore user document with ELO rating
- Profile page with animated stats, win-rate ring chart
- Avatar upload to Firebase Storage
- Display name and role editing

### ✅ Matchmaking
- Redis queue with sorted-set ordering
- Role-based pairing (PROSECUTION ↔ DEFENSE)
- Rating-based filtering (within 200 points)
- 30-second role relaxation for same-role pairs
- Frontend polling with 2-second interval
- Leave queue / cleanup on cancel
- Match found → game created in Firestore atomically

### ✅ Game Session
- Firestore game document with full player list
- Lifecycle: `WAITING_FOR_PLAYERS → ACTIVE → COMPLETED`
- Firestore transactional `/ready` endpoint (race-condition safe)
- Game state initialization in Redis on ACTIVE

### ✅ WebSocket Layer
- Authenticated WS connections (player must be in the game)
- In-memory `GameConnectionManager` with per-game rooms
- Broadcast to all players in a game
- PLAYER_CONNECTED, PLAYER_READY, GAME_STARTED events
- Reconnection-safe (StrictMode double-mount fixed)
- Auto-calls `/ready` on WS open

### ✅ Game Engine & Turn System
- Server-authoritative action validation
- Phase ↔ action mapping (wrong phase = rejected)
- Turn validation (wrong player = rejected)
- Automatic turn advancement after each submission
- Automatic phase advancement when all players submit
- All actions recorded in Firestore `events` subcollection
- Redis state updated synchronously, Firestore async (fire-and-forget)

### ✅ Courtroom Frontend
- Real-time chat panel showing both players' messages
- Courtroom stage with animated speakers
- Turn-aware input bar (disabled when not your turn)
- Phase-appropriate placeholder text
- Messages appear for BOTH players simultaneously via ACTION_SUBMITTED broadcast
- Single-player fallback (AI mock) when no gameId
- Observer mode (read-only transcript playback)

---

## 11. What Remains to be Implemented

### 🔴 HIGH PRIORITY

#### Step 8: AI Judge Evaluation
**What:** After every `SUBMIT_*` action, the AI Judge (Gemini) evaluates the submitted argument and returns a score + ruling.

**Details:**
- Reads the action text from the WS payload
- Sends to Gemini with the case context + legal precedents
- Evaluates on: legal coherence, relevance to charges, use of precedent, procedural correctness
- Returns: `score_delta` (0–10), `ruling_text` (judge's spoken comment)
- Broadcasts `JUDGE_RULING` event to both players
- Updates `scores.prosecution` or `scores.defense` in Redis

**Files to create/modify:**
- `backend/agents/judge/judge_agent.py` — new
- `backend/game/engine/engine.py` — call judge after each SUBMIT action

#### Step 9: Game Completion & Rating Update
**What:** When phase reaches `COMPLETED`:
- Calculate winner based on cumulative scores
- Broadcast `GAME_COMPLETED` with verdict + scores
- Update Firestore `users/{uid}` for both players:
  - Increment `games_played`, `wins` or `losses`
  - Update `rating` (ELO formula)
- Show results screen in frontend

#### Step 10: Frontend Result Screen
**What:** After GAME_COMPLETED event:
- Full-screen modal with verdict
- Judge's full summary
- Score breakdown per phase
- Rating change display
- "Play Again" / "Exit to Lobby" buttons

---

### 🟡 MEDIUM PRIORITY

#### Turn Timer
**What:** Each player has 120 seconds to submit. Timer visible on screen. On expiry, server auto-submits `END_TURN` for that player.
- `state.turn.time_remaining` is stored in Redis
- Backend timer via `asyncio.sleep` task per turn
- Frontend countdown UI

#### Objections System
**What:** At any time during opponent's turn, a player can raise an `OBJECTION`:
- `RAISE_OBJECTION` action (no turn restriction)
- Judge rules: `SUSTAINED` or `OVERRULED`
- If sustained, opponent loses remaining argument text; turn passes back
- Frontend: Sidebar "Raise Objection" button already exists (currently non-functional)

#### Evidence Presentation
**What:** Players can submit evidence during ARGUMENT phase:
- `PRESENT_EVIDENCE` action with `evidence_id`
- AI Evidence Analyzer (already built in `backend/agents/evidence/`) validates it
- Analyzed result shown in sidebar's LexiGraph Evidence panel

#### Reconnection Handling
**What:** If a player's internet drops mid-game:
- WS disconnect → `PLAYER_DISCONNECTED` broadcast
- Opponent sees notification
- Player reconnects within N seconds → WS reconnects, game state restored from Redis
- After N seconds of disconnect → forfeit

#### Spectator Mode
**What:** Other users can watch a live game as observers (read-only WS connection that receives all events but cannot send any actions).

---

### 🟢 LOWER PRIORITY (Polish)

#### Case Selection in Multiplayer
**What:** Currently a random case is selected by the matchmaker. Allow players to vote on a case before GAME_STARTED.

#### Chat Between Players
**What:** Out-of-character chat (separate from courtroom transcript) for coordination or sportsmanship.

#### Match History
**What:** A page showing past games with expandable transcript, scores, and AI judge ruling.

#### Leaderboard
**What:** Global ranking by ELO rating with filters by region, role preference.

#### Mobile Responsive Courtroom
**What:** The courtroom UI is desktop-first. A mobile-optimized layout is needed.

#### Notification System
**What:** When it's your turn and you've tabbed out, push/browser notification to bring you back.

---

## 12. Known Bugs Fixed

| Bug | Root Cause | Fix Applied |
|-----|-----------|-------------|
| Profile blank on email/password login | `getPlayerProfile` returned null, ProfilePage spun forever | Auto-create Firestore profile doc if missing; split spinner into authLoading + profileLoading states |
| Google sign-in: no rating in DB | loginWithGoogle didn't create Firestore doc for existing Google accounts | fetchProfile now creates the doc if it doesn't exist |
| Matchmaking: Chrome + Incognito never match | Both users defaulted to same role; same-role block was permanent | Added 30-second role relaxation; normalize "prosecutor" → "PROSECUTION" |
| "prosecutor" sent to backend | UI label `"prosecutor"` was sent raw; backend expected `"PROSECUTION"` | Role map in `matchmakingApi.js` normalizes before send |
| WebSocket error in React StrictMode | Double-mount created and immediately closed WS → browser error | `setTimeout(0)` defers creation past StrictMode cleanup |
| Messages not visible to opponent | Sender added message locally + ACTION_SUBMITTED added it again → double for sender, zero for opponent | Removed local optimistic add; ACTION_SUBMITTED broadcast is the single source of truth for all players |
| Input bar always disabled | `activeSpeaker !== null` check — in multiplayer your own turn sets `activeSpeaker = userRole` (not null) | Added `isMyTurn` prop: `activeSpeaker === userRole` in multiplayer |
| SUBMIT_OPENING rejected by backend | Frontend sent SUBMIT_OPENING when `trialPhase === "OPENING"` (UI string) but game started at CASE_INTRO and UI didn't track server phase correctly | `trialPhase` state is now set directly from GAME_STARTED/TURN_CHANGED WS events (server truth); action map uses this |
| Firestore race condition on /ready | Both players hitting /ready simultaneously → neither triggered GAME_STARTED | `@firestore.transactional` wraps the ready-update logic |
