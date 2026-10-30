from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.db import get_db
from app.schemas import InstallationOut, InverterOut, SyntheseRapport
from app.report import get_report_data

router = APIRouter(prefix="/installations", tags=["installations"])


@router.get("", response_model=List[InstallationOut])
async def list_installations(user=Depends(get_current_user), db=Depends(get_db)):
    if user["role"] == "admin":
        async with db.execute("SELECT id, name, location FROM installations") as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT id, name, location FROM installations WHERE owner_user_id = ?",
            (user["id"],),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{installation_id}/inverters", response_model=List[InverterOut])
async def list_inverters(
    installation_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    async with db.execute(
        "SELECT owner_user_id FROM installations WHERE id = ?", (installation_id,)
    ) as cur:
        inst = await cur.fetchone()
    if not inst:
        raise HTTPException(404, "Installation not found")
    if user["role"] != "admin" and inst["owner_user_id"] != user["id"]:
        raise HTTPException(403, "Access denied")

    async with db.execute(
        "SELECT id, serial, model FROM inverters WHERE installation_id = ?",
        (installation_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{installation_id}/report-data", response_model=SyntheseRapport)
async def get_installation_report_data(
    installation_id: int,
    period: str = Query("month", pattern="^(month|year)$"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Fetch aggregated report data for an installation."""
    async with db.execute(
        "SELECT owner_user_id FROM installations WHERE id = ?", (installation_id,)
    ) as cur:
        inst = await cur.fetchone()
    if not inst:
        raise HTTPException(404, "Installation not found")
    if user["role"] != "admin" and inst["owner_user_id"] != user["id"]:
        raise HTTPException(403, "Access denied")
    
    report_data = await get_report_data(db, installation_id, period, year, month)
    return report_data


@router.get("/{installation_id}/report")

async def installation_report(
    installation_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Generate a simple PDF report for an installation suitable for an installer/steg."""
    async with db.execute(
        "SELECT id, name, location, owner_user_id FROM installations WHERE id = ?",
        (installation_id,),
    ) as cur:
        inst = await cur.fetchone()
    if not inst:
        raise HTTPException(404, "Installation not found")
    if user["role"] != "admin" and inst["owner_user_id"] != user["id"]:
        raise HTTPException(403, "Access denied")

    async with db.execute(
        "SELECT id, serial, model FROM inverters WHERE installation_id = ?",
        (installation_id,),
    ) as cur:
        inv_rows = await cur.fetchall()

    # Generate PDF
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from fastapi.responses import StreamingResponse

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, f"Installation Report: {inst['name']}")
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Installation ID: {inst['id']}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Location: {inst.get('location') or '—'}")
    y -= 10 * mm

    for inv in inv_rows:
        invd = dict(inv)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, f"Inverter: {invd['serial']} ({invd.get('model') or '—'})")
        y -= 6 * mm

        # latest metrics
        async with db.execute(
            "SELECT * FROM latest_metrics WHERE inverter_id = ?",
            (invd["id"],),
        ) as cur:
            lm = await cur.fetchone()

        c.setFont("Helvetica", 9)
        if lm:
            lm_d = dict(lm)
            fields = [
                ("PV V", "pv_v"),
                ("PV I", "pv_i"),
                ("PV2 V", "pv2_v"),
                ("PV2 I", "pv2_i"),
                ("PV P", "pv_p"),
                ("AC V", "ac_v"),
                ("AC I", "ac_i"),
                ("E Day kWh", "e_day"),
                ("E Total kWh", "e_total"),
            ]
            for label, key in fields:
                val = lm_d.get(key)
                c.drawString(25 * mm, y, f"{label}: {val if val is not None else '—'}")
                y -= 5 * mm
        else:
            c.drawString(25 * mm, y, "No metrics available")
            y -= 6 * mm

        # recent alerts (up to 5)
        async with db.execute(
            "SELECT id, code, message, raised_at, cleared_at FROM alerts WHERE inverter_id=? ORDER BY raised_at DESC LIMIT 5",
            (invd["id"],),
        ) as cur:
            alerts = await cur.fetchall()

        if alerts:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(25 * mm, y, "Recent alerts:")
            y -= 5 * mm
            c.setFont("Helvetica", 9)
            for a in alerts:
                a_d = dict(a)
                cleared = a_d["cleared_at"] or "open"
                c.drawString(
                    27 * mm,
                    y,
                    f"- [{a_d['code']}] {a_d.get('message') or ''} at {a_d['raised_at']} ({cleared})",
                )
                y -= 5 * mm
                if y < 30 * mm:
                    c.showPage()
                    y = height - 20 * mm
        else:
            c.setFont("Helvetica", 9)
            c.drawString(25 * mm, y, "No recent alerts")
            y -= 6 * mm

        y -= 6 * mm
        if y < 30 * mm:
            c.showPage()
            y = height - 20 * mm

    c.save()
    buf.seek(0)

    filename = f"installation_{installation_id}_report.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
