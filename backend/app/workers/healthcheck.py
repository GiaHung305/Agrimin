import asyncio
import sys

from app.workers.health import read_worker_health


async def main() -> int:
    try:
        health = await read_worker_health()
    except Exception:
        return 1
    return 0 if health["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
