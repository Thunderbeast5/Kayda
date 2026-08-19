const API_URL = "http://localhost:5001/api/matchmaking";

export async function joinMatchmakingQueue(userId, username, preferredRole) {
  try {
    const response = await fetch(`${API_URL}/join`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        username: username,
        rating: 1200, // Default for now
        preferred_role: preferredRole.toUpperCase(),
      }),
    });
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error joining matchmaking queue:", error);
    throw error;
  }
}

export async function leaveMatchmakingQueue(userId) {
  try {
    const response = await fetch(`${API_URL}/leave`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
      }),
    });
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error leaving matchmaking queue:", error);
    throw error;
  }
}

export async function pollMatchmakingStatus(userId) {
  try {
    const response = await fetch(`${API_URL}/status?user_id=${userId}`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error polling matchmaking status:", error);
    throw error;
  }
}
