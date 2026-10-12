import redis.asyncio as redis
import os
import socket
import subprocess
import shutil

# Default to 127.0.0.1 to avoid Windows IPv6 localhost connection attempts
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

def is_redis_running(host="127.0.0.1", port=6379) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=0.5)
        s.close()
        return True
    except OSError:
        return False

def ensure_redis_server():
    """If Redis is not running and redis-server is installed on Windows, start it automatically."""
    if not is_redis_running():
        paths_to_check = [
            r"C:\Program Files\Redis\redis-server.exe",
            shutil.which("redis-server.exe"),
            shutil.which("redis-server"),
        ]
        server_bin = next((p for p in paths_to_check if p and os.path.exists(p)), None)
        if server_bin:
            server_dir = os.path.dirname(server_bin)
            cmd = [server_bin]
            if os.path.exists(os.path.join(server_dir, "redis.windows.conf")):
                cmd.append("redis.windows.conf")
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            cmd.extend(["--dir", data_dir, "--stop-writes-on-bgsave-error", "no"])
            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000200
                subprocess.Popen(cmd, creationflags=creationflags, cwd=server_dir)
                print(f"[Redis] Started local Redis server automatically: {server_bin}")
            except Exception as e:
                print(f"[Redis] Note: Could not auto-start Redis ({e}).")

# Attempt to ensure Redis is running
ensure_redis_server()

# Create a global async Redis client using RESP2 protocol (compatible with Redis 3.0+ and modern Redis)
redis_client = redis.from_url(REDIS_URL, decode_responses=True, protocol=2)

async def hset_mapping(key: str, mapping: dict):
    """
    Safely stores a mapping/dict into a Redis hash.
    Falls back to hmset if running against Redis < 4.0 (e.g. Windows native Redis 3.0).
    """
    try:
        return await redis_client.hset(key, mapping=mapping)
    except Exception:
        return await redis_client.hmset(key, mapping)
