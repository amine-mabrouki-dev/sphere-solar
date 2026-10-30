import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# On Windows the default (Proactor) event loop does not implement
# add_reader/add_writer, which aiomqtt/paho rely on. Force the selector loop
# so the MQTT worker can watch its socket. Must run before uvicorn builds the loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import Depends, FastAPI, HTTPException

from app.auth import create_access_token, hash_password, verify_password
from app.db import close_db, get_db, init_db
from app.mqtt_worker import add_broadcast_callback, init_publish_queue, mqtt_worker
from app.schemas import LoginRequest, TokenResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_publish_queue()

    # Wire the WebSocket broadcaster into the MQTT worker
    from app.api.websocket import broadcaster
    add_broadcast_callback(broadcaster)

    worker_task = asyncio.create_task(mqtt_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title="Solar PV Monitoring API", version="0.1.0", lifespan=lifespan)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(body: LoginRequest, db=Depends(get_db)):
    async with db.execute(
        "SELECT id, password_hash, role FROM users WHERE email = ?", (body.email,)
    ) as cur:
        row = await cur.fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_access_token(row["id"], row["role"])}


@app.post("/auth/seed", status_code=201, tags=["auth"])
async def seed_admin(body: LoginRequest, db=Depends(get_db)):
    """Create the first admin user. Fails if any user already exists."""
    async with db.execute("SELECT COUNT(*) AS n FROM users") as cur:
        row = await cur.fetchone()
    if row["n"] > 0:
        raise HTTPException(409, "Users already exist — use /auth/login")
    await db.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (?,?,'admin')",
        (body.email, hash_password(body.password)),
    )
    await db.commit()
    return {"status": "admin created", "email": body.email}


# ── Routers ───────────────────────────────────────────────────────────────────

from app.api.installations import router as installations_router
from app.api.inverters import router as inverters_router
from app.api.assistant import router as assistant_router
from app.api.websocket import router as ws_router
from app.api.performance import router as performance_router   # NOUVEAU : comparaison à la référence

app.include_router(installations_router)
app.include_router(inverters_router)
app.include_router(assistant_router)
app.include_router(ws_router)
app.include_router(performance_router)                          # NOUVEAU : GET /inverters/{id}/performance