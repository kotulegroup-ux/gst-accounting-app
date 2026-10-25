from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db
from app.auth import get_current_user, log_audit
from app.reports import get_party_ledger
from app.routers.client_router import get_context

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/parties", response_class=HTMLResponse)
async def list_parties(request: Request, type: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM parties WHERE client_id = ?"
    params = [client_id]

    if type in ("debtor", "creditor"):
        query += " AND (party_type = ? OR party_type = 'both')"
        params.append(type)

    query += " ORDER BY name ASC"
    cursor.execute(query, params)
    parties = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for p in parties:
        _, _, closing_bal, closing_type, _, _ = get_party_ledger(client_id, p["id"])
        p["closing_balance"] = closing_bal
        p["closing_type"] = closing_type

    return templates.TemplateResponse(request=request, name="client/parties_list.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "filter_type": type,
        "msg": request.query_params.get("msg")
    })

@router.get("/parties/new", response_class=HTMLResponse)
async def new_party_page(request: Request, type: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(request=request, name="client/party_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "party": None,
        "default_type": type or "debtor"
    })

@router.post("/parties/new")
async def create_party(
    request: Request,
    party_type: str = Form("debtor"),
    name: str = Form(...),
    trade_name: str = Form(None),
    gstin: str = Form(None),
    state_code: str = Form(...),
    state_name: str = Form(...),
    address: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    opening_balance: float = Form(0.0),
    opening_balance_type: str = Form("Dr")
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO parties (
            client_id, party_type, name, trade_name, gstin, state_code, state_name,
            address, phone, email, opening_balance, opening_balance_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id, party_type, name.strip(), (trade_name or "").strip(),
        (gstin or "").strip().upper(), state_code.strip(), state_name.strip(),
        (address or "").strip(), (phone or "").strip(), (email or "").strip(),
        opening_balance, opening_balance_type, now
    ))
    party_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "PARTY", party_id, f"Added {party_type}: {name}")

    return RedirectResponse("/parties?msg=Party+added+successfully", status_code=302)

@router.get("/parties/{party_id}/edit", response_class=HTMLResponse)
async def edit_party_page(request: Request, party_id: int):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    conn.close()

    if not party:
        return RedirectResponse("/parties", status_code=302)

    return templates.TemplateResponse(request=request, name="client/party_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "party": dict(party)
    })

@router.post("/parties/{party_id}/edit")
async def update_party(
    request: Request,
    party_id: int,
    party_type: str = Form("debtor"),
    name: str = Form(...),
    trade_name: str = Form(None),
    gstin: str = Form(None),
    state_code: str = Form(...),
    state_name: str = Form(...),
    address: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    opening_balance: float = Form(0.0),
    opening_balance_type: str = Form("Dr")
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE parties SET
            party_type = ?, name = ?, trade_name = ?, gstin = ?, state_code = ?, state_name = ?,
            address = ?, phone = ?, email = ?, opening_balance = ?, opening_balance_type = ?
        WHERE id = ?
    """, (
        party_type, name.strip(), (trade_name or "").strip(),
        (gstin or "").strip().upper(), state_code.strip(), state_name.strip(),
        (address or "").strip(), (phone or "").strip(), (email or "").strip(),
        opening_balance, opening_balance_type, party_id
    ))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "PARTY", party_id, f"Updated party: {name}")

    return RedirectResponse("/parties?msg=Party+updated+successfully", status_code=302)

@router.post("/parties/{party_id}/delete")
async def delete_party(request: Request, party_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name, client_id FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    if not party:
        conn.close()
        return RedirectResponse("/parties", status_code=302)

    name = party["name"]
    client_id = party["client_id"]

    try:
        cursor.execute("DELETE FROM parties WHERE id = ?", (party_id,))
        conn.commit()
        log_audit(client_id, user["id"], user["full_name"], "DELETE", "PARTY", party_id, f"Deleted party: {name}")
        msg = "Party+deleted+successfully"
    except Exception as e:
        msg = "Cannot+delete+party+with+existing+invoices+or+payments"

    conn.close()
    return RedirectResponse(f"/parties?msg={msg}", status_code=302)

@router.get("/ledger", response_class=HTMLResponse)
async def ledger_statement(request: Request, party_id: int = None, start_date: str = None, end_date: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parties WHERE client_id = ? ORDER BY name ASC", (client_id,))
    all_parties = [dict(r) for r in cursor.fetchall()]
    conn.close()

    party = None
    ledger_entries = []
    closing_bal = 0.0
    closing_type = "Dr"
    total_debit = 0.0
    total_credit = 0.0

    if party_id:
        party, ledger_entries, closing_bal, closing_type, total_debit, total_credit = get_party_ledger(
            client_id, party_id, start_date, end_date
        )

    current_time = datetime.now().strftime("%d-%b-%Y %I:%M %p")

    return templates.TemplateResponse(request=request, name="client/ledger.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "all_parties": all_parties,
        "party": party,
        "ledger_entries": ledger_entries,
        "closing_balance": closing_bal,
        "closing_type": closing_type,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "current_time": current_time
    })
