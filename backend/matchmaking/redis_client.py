import redis.asyncio as redis
import os

# We will use the default localhost redis for now. Can be configured via env var.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a global async Redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
