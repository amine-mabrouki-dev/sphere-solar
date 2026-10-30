import asyncio
import json
import logging
import os
import ssl
from datetime import datetime
from typing import Callable, Awaitable

import aiomqtt

from app.schemas import TelemetryPayload

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
MQTT_TLS  = os.getenv("MQTT_TLS", "0") == "1"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")  # path to broker ca.crt (optional)

# Filled by main.py on startup; called for every ingested telemetry row.
_broadcast_callbacks: list[Callable[[int, dict], Awaitable[None]]] = []

# REST endpoint puts (topic, json_str) here; worker publishes them.
_publish_queue: asyncio.Queue | None = None


def add_broadcast_callback(cb: Callable[[int, dict], Awaitable[None]]) -> None:
    _broadcast_callbacks.append(cb)


def init_publish_queue() -> None:
    global _publish_queue
    _publish_queue = asyncio.Queue()


async def publish_command(topic: str, payload: dict) -> None:
    if _publish_queue is None:
        raise RuntimeError("MQTT worker not started")
    await _publish_queue.put((topic, json.dumps(payload)))


async def _broadcast(inverter_id: int, data: dict) -> None:
    for cb in list(_broadcast_callbacks):
        try:
            await cb(inverter_id, data)
        except Exception:
            pass


# ── DB helpers ────────────────────────────────────────────────────────────────

METRIC_FIELDS = [
    "pv_v", "pv_i", "pv_p",
    "pv2_v", "pv2_i",
    "ac_v", "ac_i", "freq",
    "e_day", "e_total",
    "batt_v", "batt_i", "batt_soc",
    "temp", "alarm",
]

ALARM_MESSAGES = {
    7:   "Défaut général de l'onduleur",
    101: "Surtension DC - tension PV trop élevée",
    102: "Sous-tension DC - tension PV trop faible",
    103: "Courant DC excessif",
    203: "Surtension AC - tension réseau trop élevée",
    204: "Sous-fréquence réseau",
    301: "Défaut d'isolement - fuite à la terre détectée",
    302: "Défaut résiduel - courant de fuite élevé",
    305: "Perte de connexion réseau AC",
    401: "Erreur de communication interne",
    501: "Mise à jour firmware en cours",
}


def _alarm_message(alarm: int) -> str:
    return ALARM_MESSAGES.get(alarm, f"Alarm code {alarm} - consulter le manuel")


async def _resolve_inverter_id(db, site_id: int, serial: str) -> int:
    async with db.execute("SELECT id FROM inverters WHERE serial = ?", (serial,)) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]

    # Auto-register: find or create the installation
    async with db.execute(
        "SELECT id FROM installations WHERE name = ?", (f"site-{site_id}",)
    ) as cur:
        inst = await cur.fetchone()

    if inst:
        inst_id = inst["id"]
    else:
        cur = await db.execute(
            "INSERT INTO installations (name, location, owner_user_id) VALUES (?,?,1)",
            (f"site-{site_id}", f"auto site {site_id}"),
        )
        inst_id = cur.lastrowid

    cur = await db.execute(
        "INSERT INTO inverters (installation_id, serial, model) VALUES (?,?,?)",
        (inst_id, serial, "auto-registered"),
    )
    await db.commit()
    return cur.lastrowid


async def _send_energy_sync_commands(db, client) -> None:
    async with db.execute(
        "SELECT inv.serial, inst.id AS site_id, latest.e_total, latest.e_day, latest.ts "
        "FROM latest_metrics latest "
        "JOIN inverters inv ON inv.id = latest.inverter_id "
        "JOIN installations inst ON inst.id = inv.installation_id"
    ) as cur:
        async for row in cur:
            if row["e_total"] is None:
                continue
            cmd = {
                "sync_energy": True,
                "e_total": row["e_total"],
            }
            if row["e_day"] is not None:
                ts = row["ts"]
                if ts is not None and datetime.utcfromtimestamp(ts).date() == datetime.utcnow().date():
                    cmd["e_day"] = row["e_day"]
                    cmd["day_key"] = int(ts // 86400)
            topic = f"site/{row['site_id']}/inv/{row['serial']}/cmd"
            await client.publish(topic, json.dumps(cmd))
            logger.info("Sent energy sync to %s: %s", topic, cmd)


async def _handle_telemetry(db, payload: TelemetryPayload) -> None:
    inverter_id = await _resolve_inverter_id(db, payload.site_id, payload.inv)

    # Protect against boot-time reset messages that report 0 for cumulative
    # counters. If we already have a prior latest_metrics row, keep its
    # non-zero cumulative totals instead of overwriting them with a reboot
    # snapshot.
    prev_e_day = None
    prev_e_total = None
    prev_ts = None
    async with db.execute(
        "SELECT ts, e_day, e_total FROM latest_metrics WHERE inverter_id = ?",
        (inverter_id,),
    ) as cur:
        row = await cur.fetchone()
    if row:
        prev_ts = row["ts"]
        prev_e_day = row["e_day"]
        prev_e_total = row["e_total"]

    if payload.e_total == 0 and prev_e_total not in (None, 0):
        logger.info(
            "Ignoring reboot e_total=0 for inverter %s, keeping previous %s",
            inverter_id,
            prev_e_total,
        )
        payload = payload.copy(update={"e_total": None})

    same_day = (
        prev_ts is not None
        and datetime.utcfromtimestamp(payload.ts).date() == datetime.utcfromtimestamp(prev_ts).date()
    )

    baseline_e_day = None
    if same_day and prev_e_total not in (None, 0) and prev_e_day not in (None, 0):
        baseline_e_day = prev_e_total - prev_e_day

    if payload.e_total is not None and prev_e_total not in (None, 0) and payload.e_total < prev_e_total:
        logger.info(
            "Ignoring decreased e_total=%s for inverter %s, keeping previous %s",
            payload.e_total,
            inverter_id,
            prev_e_total,
        )
        payload = payload.copy(update={"e_total": None})

    if payload.e_day == 0 and prev_e_day not in (None, 0) and same_day:
        logger.info(
            "Detected reboot-reset e_day=0 for inverter %s on same day",
            inverter_id,
        )
        if baseline_e_day is not None and payload.e_total is not None:
            estimated = round(payload.e_total - baseline_e_day, 2)
            if estimated >= 0:
                logger.info(
                    "Estimating e_day=%s from e_total for inverter %s",
                    estimated,
                    inverter_id,
                )
                payload = payload.copy(update={"e_day": estimated})
            else:
                payload = payload.copy(update={"e_day": None})
        else:
            payload = payload.copy(update={"e_day": None})

    if payload.e_day is not None and prev_e_day not in (None, 0) and same_day and payload.e_day < prev_e_day:
        logger.info(
            "Detected decreased e_day=%s for inverter %s on same day",
            payload.e_day,
            inverter_id,
        )
        if baseline_e_day is not None and payload.e_total is not None:
            estimated = round(payload.e_total - baseline_e_day, 2)
            if estimated >= prev_e_day:
                logger.info(
                    "Estimating e_day=%s from e_total for inverter %s",
                    estimated,
                    inverter_id,
                )
                payload = payload.copy(update={"e_day": estimated})
            else:
                payload = payload.copy(update={"e_day": None})
        else:
            payload = payload.copy(update={"e_day": None})

    if payload.e_day is None and baseline_e_day is not None and payload.e_total is not None:
        estimated = round(payload.e_total - baseline_e_day, 2)
        if estimated >= 0:
            logger.info(
                "Filling missing e_day=%s from e_total for inverter %s",
                estimated,
                inverter_id,
            )
            payload = payload.copy(update={"e_day": estimated})

    values = [getattr(payload, f) for f in METRIC_FIELDS]

    # INSERT into full history
    cols = "inverter_id, ts, " + ", ".join(METRIC_FIELDS)
    placeholders = ", ".join(["?"] * (len(METRIC_FIELDS) + 2))
    await db.execute(
        f"INSERT INTO readings ({cols}) VALUES ({placeholders})",
        [inverter_id, payload.ts] + values,
    )

    # UPSERT latest_metrics (one row per inverter)
    cols_lm = ", ".join(METRIC_FIELDS)
    ph_lm = ", ".join(["?"] * len(METRIC_FIELDS))
    set_clause = ", ".join(
        f"{f} = COALESCE(excluded.{f}, latest_metrics.{f})" for f in METRIC_FIELDS
    )
    await db.execute(
        f"""INSERT INTO latest_metrics (inverter_id, ts, {cols_lm}, updated_at)
            VALUES (?, ?, {ph_lm}, unixepoch())
            ON CONFLICT(inverter_id) DO UPDATE SET
              ts = excluded.ts, {set_clause}, updated_at = excluded.updated_at""",
        [inverter_id, payload.ts] + values,
    )

    # Alert: latch on a non-zero alarm. Alerts stay open until a user dismisses
    # them (POST /inverters/{id}/alerts/{id}/dismiss). A healthy reading does NOT
    # auto-clear, so transient faults remain visible/actionable.
    alarm = payload.alarm or 0
    if alarm:
        async with db.execute(
            "SELECT id FROM alerts WHERE inverter_id=? AND code=? AND cleared_at IS NULL",
            (inverter_id, alarm),
        ) as cur:
            if not await cur.fetchone():
                await db.execute(
                    "INSERT INTO alerts (inverter_id, code, message, raised_at) VALUES (?,?,?,?)",
                    (inverter_id, alarm, _alarm_message(alarm), payload.ts),
                )

    await db.commit()
    await _broadcast(inverter_id, {"inverter_id": inverter_id, **payload.model_dump()})


# ── Worker loop ───────────────────────────────────────────────────────────────

async def mqtt_worker() -> None:
    from app.db import _db  # import lazily — db is initialised before this runs

    backoff = 1
    client_kwargs: dict = {"hostname": MQTT_HOST, "port": MQTT_PORT}
    if MQTT_USER:
        client_kwargs["username"] = MQTT_USER
        client_kwargs["password"] = MQTT_PASS
    if MQTT_TLS:
        client_kwargs["tls_params"] = aiomqtt.TLSParameters(
            ca_certs=MQTT_CA_CERT or None,   # None -> system trust store (e.g. Let's Encrypt)
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    while True:
        try:
            async with aiomqtt.Client(**client_kwargs) as client:
                backoff = 1
                await client.subscribe("site/+/inv/+/telemetry")
                await client.subscribe("site/+/inv/+/status")
                logger.info("MQTT connected → subscribed to site/+/inv/+/{telemetry,status}")

                await _send_energy_sync_commands(_db, client)

                async def _outbox():
                    while True:
                        topic, msg = await _publish_queue.get()
                        await client.publish(topic, msg)

                outbox_task = asyncio.create_task(_outbox())
                try:
                    async for message in client.messages:
                        topic = str(message.topic)
                        if not topic.endswith("/telemetry"):
                            continue
                        try:
                            raw = json.loads(message.payload)
                            payload = TelemetryPayload(**raw)
                        except Exception as exc:
                            logger.warning("Bad telemetry on %s: %s", topic, exc)
                            continue
                        from app.db import _db as db
                        await _handle_telemetry(db, payload)
                finally:
                    outbox_task.cancel()

        except aiomqtt.MqttError as exc:
            logger.error("MQTT error: %s — retry in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Unexpected MQTT worker error: %s", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
