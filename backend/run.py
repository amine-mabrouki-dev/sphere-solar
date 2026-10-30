"""Cross-platform launcher for the Solar PV Monitoring backend.

On Windows the default (Proactor) asyncio loop does not implement
add_reader/add_writer, which aiomqtt/paho need. uvicorn hardcodes the Proactor
loop for single-process runs, ignoring the global policy, so we build the loop
ourselves here and hand uvicorn the already-running selector loop.

Usage:  python run.py        (host/port come from HOST/PORT env or defaults)
"""
import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


def load_env_file(path: str) -> None:
    """Load KEY=VALUE lines from .env into os.environ (shell values win).

    app/llm.py reads OLLAMA_API_KEY at import time, so this must run before
    uvicorn imports app.main.
    """
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


def main() -> None:
    load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config("app.main:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    # asyncio.run() creates the loop via the policy set above (selector on Windows);
    # Server.serve() then runs on that loop instead of creating its own.
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
