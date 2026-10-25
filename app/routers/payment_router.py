from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db
from app.auth import get_current_user, log_audit
from app.routers.client_router import get_context

router = APIRouter(prefix="/payments")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/in", response_class=HTMLResponse)
async def list_payments_in(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM payments WHERE client_id = ? AND payment_type = 'received' ORDER BY payment_date DESC, id DESC
    """, (client_id,))
    payments = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="client/payments_in_list.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "payments": payments,
        "msg": request.query_params.get("msg")
    })

@router.get("/in/new", response_class=HTMLResponse)
async def new_payment_in_page(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN ('debtor', 'both') ORDER BY name ASC", (client_id,))
    parties = [dict(r) for r in cursor.fetchall()]
    today_date = datetime.now().strftime("%Y-%m-%d")
    conn.close()

    return templates.TemplateResponse(request=request, name="client/payment_in_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "today_date": today_date,
        "payment": None
    })

@router.post("/in/new")
async def create_payment_in(
    request: Request,
    party_id: int = Form(...),
    payment_date: str = Form(...),
    amount: float = Form(...),
    payment_mode: str = Form("Bank"),
    reference_no: str = Form(None),
    remarks: str = Form(None)
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    party_name = party["name"] if party else "Unknown Party"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO payments (
            client_id, payment_type, payment_date, party_id, party_name,
            amount, payment_mode, reference_no, remarks,
            created_by_user_id, created_at, updated_at
        ) VALUES (?, 'received', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id, payment_date, party_id, party_name,
        amount, payment_mode, (reference_no or "").strip(), (remarks or "").strip(),
        user["id"], now, now
    ))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "PAYMENT_IN", payment_id, f"Recorded receipt of ₹ {amount} from {party_name}")

    return RedirectResponse("/payments/in?msg=Payment+receipt+recorded+successfully", status_code=302)

@router.get("/out", response_class=HTMLResponse)
async def list_payments_out(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM payments WHERE client_id = ? AND payment_type = 'made' ORDER BY payment_date DESC, id DESC
    """, (client_id,))
    payments = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="client/payments_out_list.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "payments": payments,
        "msg": request.query_params.get("msg")
    })

@router.get("/out/new", response_class=HTMLResponse)
async def new_payment_out_page(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN ('creditor', 'both') ORDER BY name ASC", (client_id,))
    parties = [dict(r) for r in cursor.fetchall()]
    today_date = datetime.now().strftime("%Y-%m-%d")
    conn.close()

    return templates.TemplateResponse(request=request, name="client/payment_out_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "today_date": today_date,
        "payment": None
    })

@router.post("/out/new")
async def create_payment_out(
    request: Request,
    party_id: int = Form(...),
    payment_date: str = Form(...),
    amount: float = Form(...),
    payment_mode: str = Form("Bank"),
    reference_no: str = Form(None),
    remarks: str = Form(None)
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    party_name = party["name"] if party else "Unknown Party"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO payments (
            client_id, payment_type, payment_date, party_id, party_name,
            amount, payment_mode, reference_no, remarks,
            created_by_user_id, created_at, updated_at
        ) VALUES (?, 'made', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id, payment_date, party_id, party_name,
        amount, payment_mode, (reference_no or "").strip(), (remarks or "").strip(),
        user["id"], now, now
    ))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "PAYMENT_OUT", payment_id, f"Recorded payment of ₹ {amount} to {party_name}")

    return RedirectResponse("/payments/out?msg=Payment+disbursement+recorded+successfully", status_code=302)

@router.get("/{payment_id}/edit", response_class=HTMLResponse)
async def edit_payment_page(request: Request, payment_id: int):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    pmt = cursor.fetchone()
    if not pmt:
        conn.close()
        return RedirectResponse("/", status_code=302)

    pmt = dict(pmt)
    ptype = 'debtor' if pmt["payment_type"] == 'received' else 'creditor'
    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN (?, 'both') ORDER BY name ASC", (pmt["client_id"], ptype))
    parties = [dict(r) for r in cursor.fetchall()]
    conn.close()

    tpl = "client/payment_in_form.html" if pmt["payment_type"] == 'received' else "client/payment_out_form.html"

    return templates.TemplateResponse(request=request, name=tpl, context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "payment": pmt,
        "today_date": pmt["payment_date"]
    })

@router.post("/{payment_id}/edit")
async def update_payment(
    request: Request,
    payment_id: int,
    payment_type: str = Form(...),
    party_id: int = Form(...),
    payment_date: str = Form(...),
    amount: float = Form(...),
    payment_mode: str = Form("Bank"),
    reference_no: str = Form(None),
    remarks: str = Form(None)
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    old_pmt = cursor.fetchone()
    if not old_pmt:
        conn.close()
        return RedirectResponse("/", status_code=302)

    client_id = old_pmt["client_id"]
    cursor.execute("SELECT name FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    party_name = party["name"] if party else old_pmt["party_name"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE payments SET
            payment_type = ?, payment_date = ?, party_id = ?, party_name = ?,
            amount = ?, payment_mode = ?, reference_no = ?, remarks = ?, updated_at = ?
        WHERE id = ?
    """, (
        payment_type, payment_date, party_id, party_name,
        amount, payment_mode, (reference_no or "").strip(), (remarks or "").strip(), now, payment_id
    ))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "PAYMENT", payment_id, f"Corrected payment entry: ₹ {amount} for {party_name}")

    dest = "/payments/in" if payment_type == "received" else "/payments/out"
    return RedirectResponse(f"{dest}?msg=Payment+entry+updated+successfully", status_code=302)

@router.post("/{payment_id}/delete")
async def delete_payment(request: Request, payment_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    pmt = cursor.fetchone()
    if not pmt:
        conn.close()
        return RedirectResponse("/", status_code=302)

    client_id = pmt["client_id"]
    ptype = pmt["payment_type"]
    desc = f"Deleted payment of ₹ {pmt['amount']} ({pmt['party_name']})"

    cursor.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "DELETE", "PAYMENT", payment_id, desc)

    dest = "/payments/in" if ptype == "received" else "/payments/out"
    return RedirectResponse(f"{dest}?msg=Payment+entry+deleted", status_code=302)
