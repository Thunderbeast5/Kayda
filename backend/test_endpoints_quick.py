import asyncio
import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent
_agents_dir = _backend_dir / "agents"
for _p in [str(_backend_dir), str(_agents_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx
from app_orchestrator import app

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/api/health")
        print("Health Status:", r1.status_code, r1.json())

        r2 = await client.get("/api/cases")
        cases = r2.json()
        print(f"Cases ({len(cases)} found):")
        for c in cases[:5]:
            print(f"  • {c['id']}: {c['title']} | charge={c.get('primary_charge')}")

        r3 = await client.get("/api/simulate/8efffec1/events")
        data = r3.json()
        events = data.get("events", [])
        print(f"\n8efffec1 Event Stream ({len(events)} events):")
        for idx, e in enumerate(events):
            etype = e.get("type")
            spk = e.get("agent") or e.get("to") or ""
            res = e.get("result") or ""
            phase = e.get("phase") or ""
            print(f"  [{idx+1}] type={etype} agent={spk} result={res} phase={phase}")

if __name__ == "__main__":
    asyncio.run(main())
