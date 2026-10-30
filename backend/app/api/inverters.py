import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user, require_admin
from app.db import get_db
from app.mqtt_worker import publish_command
from app.schemas import AlertOut, CommandRequest, LatestMetricsOut, ReadingOut

router = APIRouter(prefix="/inverters", tags=["inverters"])

ALLOWED_ACTIONS = {"reboot", "set_interval"}


async def _check_access(inverter_id: int, user: dict, db) -> dict:
    async with db.execute(
        """SELECT inv.id, inv.serial, inst.id AS site_id, inst.owner_user_id
           FROM inverters inv
           JOIN installations inst ON inst.id = inv.installation_id
           WHERE inv.id = ?""",
        (inverter_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Inverter not found")
    if user["role"] != "admin" and row["owner_user_id"] != user["id"]:
        raise HTTPException(403, "Access denied")
    return dict(row)


@router.get("/{inverter_id}/latest", response_model=LatestMetricsOut)
async def get_latest(
    inverter_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    async with db.execute(
        "SELECT * FROM latest_metrics WHERE inverter_id = ?", (inverter_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "No data yet for this inverter")
    
    row_dict = dict(row)
    
    # Reset e_day if the day has changed since the last reading (using UTC dates)
    if row_dict.get("ts") and row_dict.get("e_day") is not None:
        last_reading_date_utc = datetime.utcfromtimestamp(row_dict["ts"]).date()
        current_date_utc = datetime.utcfromtimestamp(time.time()).date()
        if last_reading_date_utc < current_date_utc:
            row_dict["e_day"] = None  # Reset to None so it shows as "—" or waits for new data
    
    return row_dict


@router.get("/{inverter_id}/history", response_model=List[ReadingOut])
async def get_history(
    inverter_id: int,
    from_ts: Optional[int] = Query(None, alias="from"),
    to_ts:   Optional[int] = Query(None, alias="to"),
    limit:   int           = Query(500, le=5000),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    conds  = ["inverter_id = ?"]
    params = [inverter_id]
    if from_ts is not None:
        conds.append("ts >= ?"); params.append(from_ts)
    if to_ts is not None:
        conds.append("ts <= ?"); params.append(to_ts)
    params.append(limit)

    sql = f"SELECT * FROM readings WHERE {' AND '.join(conds)} ORDER BY ts DESC LIMIT ?"
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{inverter_id}/energy")
async def get_energy(
    inverter_id: int,
    period:  str           = Query("day", pattern="^(day|month)$"),
    from_ts: Optional[int] = Query(None, alias="from"),
    to_ts:   Optional[int] = Query(None, alias="to"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    conds  = ["inverter_id = ?", "e_day IS NOT NULL"]
    params = [inverter_id]
    if from_ts is not None:
        conds.append("ts >= ?"); params.append(from_ts)
    if to_ts is not None:
        conds.append("ts <= ?"); params.append(to_ts)
    where = " AND ".join(conds)

    if period == "day":
        # For each day, take the MAX e_day. e_day only rises during the day and
        # the firmware resets it on the same UTC day boundary used here, so the
        # max is robust to an end-of-day reboot reporting e_day = 0.
        sql = f"""
            SELECT date(ts, 'unixepoch') AS bucket, MAX(e_day) AS energy_kwh
            FROM readings
            WHERE {where}
            GROUP BY date(ts, 'unixepoch')
            ORDER BY bucket
        """
    else:
        # For months, sum the daily max values
        sql = f"""
            WITH daily_values AS (
                SELECT date(ts, 'unixepoch') AS d, MAX(e_day) AS daily_value
                FROM readings
                WHERE {where}
                GROUP BY date(ts, 'unixepoch')
            )
            SELECT substr(d, 1, 7) AS bucket, SUM(daily_value) AS energy_kwh
            FROM daily_values
            GROUP BY bucket
            ORDER BY bucket
        """

    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{inverter_id}/alerts", response_model=List[AlertOut])
async def get_alerts(
    inverter_id: int,
    only_open:  Optional[bool] = Query(None, alias="open"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    await _check_access(inverter_id, user, db)
    if only_open is True:
        sql = "SELECT * FROM alerts WHERE inverter_id=? AND cleared_at IS NULL ORDER BY raised_at DESC"
    elif only_open is False:
        sql = "SELECT * FROM alerts WHERE inverter_id=? AND cleared_at IS NOT NULL ORDER BY raised_at DESC"
    else:
        sql = "SELECT * FROM alerts WHERE inverter_id=? ORDER BY raised_at DESC"

    async with db.execute(sql, (inverter_id,)) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/{inverter_id}/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    inverter_id: int,
    alert_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Acknowledge/dismiss an open alert (alerts latch until dismissed)."""
    await _check_access(inverter_id, user, db)
    now = int(time.time())
    async with db.execute(
        "UPDATE alerts SET cleared_at=? WHERE id=? AND inverter_id=? AND cleared_at IS NULL",
        (now, alert_id, inverter_id),
    ) as cur:
        changed = cur.rowcount
    await db.commit()
    if not changed:
        raise HTTPException(404, "Open alert not found")
    return {"status": "dismissed", "alert_id": alert_id, "cleared_at": now}


@router.post("/{inverter_id}/command", status_code=202)
async def send_command(
    inverter_id: int,
    cmd: CommandRequest,
    user=Depends(require_admin),
    db=Depends(get_db),
):
    if cmd.action not in ALLOWED_ACTIONS:
        raise HTTPException(400, f"Action not allowed; valid: {sorted(ALLOWED_ACTIONS)}")

    inv = await _check_access(inverter_id, user, db)
    topic = f"site/{inv['site_id']}/inv/{inv['serial']}/cmd"
    await publish_command(topic, cmd.model_dump(exclude_none=True))
    return {"status": "queued", "topic": topic}
