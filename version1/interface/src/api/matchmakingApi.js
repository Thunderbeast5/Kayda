const API_URL = "http://localhost:5001/api/matchmaking";

export async function joinMatchmakingQueue(userId, username, preferredRole, rating = 1200) {
  // Normalize role: UI uses "prosecutor"/"defense", backend expects "PROSECUTION"/"DEFENSE"
  const roleMap = {
    prosecutor: "PROSECUTION",
    prosecution: "PROSECUTION",
    defense: "DEFENSE",
    judge: "ANY",
    observer: "ANY",
  };
  const normalizedRole = roleMap[preferredRole?.toLowerCase()] || "ANY";
  
  try {
    const response = await fetch(`${API_URL}/join`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        username: username,
        rating: rating,
        preferred_role: normalizedRole,
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
