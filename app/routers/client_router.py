from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db
from app.auth import get_current_user, get_active_client_id, log_audit
from app.reports import get_party_ledger

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def get_context(request: Request):
    user = get_current_user(request)
    if not user:
        return None, None, []

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM clients ORDER BY id ASC")
    all_clients = [dict(r) for r in cursor.fetchall()]

    active_client_id = get_active_client_id(request, user)
    active_client = None

    if active_client_id:
        cursor.execute("SELECT * FROM clients WHERE id = ?", (active_client_id,))
        row = cursor.fetchone()
        if row:
            active_client = dict(row)

    if not active_client and all_clients:
        active_client = all_clients[0]
        if user["role"] == "admin":
            request.session["admin_active_client_id"] = active_client["id"]

    conn.close()
    return user, active_client, all_clients

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not active_client:
        if user["role"] == "admin":
            return RedirectResponse("/admin/clients", status_code=302)
        return templates.TemplateResponse(request=request, name="client/dashboard.html", context={
            "user": user, "active_client": None, "all_clients": []
        })

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(grand_total), 0) as total, COALESCE(SUM(total_tax), 0) as tax
        FROM invoices WHERE client_id = ?
    """, (client_id,))
    sales_stat = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(grand_total), 0) as total, COALESCE(SUM(total_tax), 0) as tax
        FROM purchases WHERE client_id = ?
    """, (client_id,))
    pur_stat = cursor.fetchone()

    cursor.execute("SELECT id FROM parties WHERE client_id = ? AND party_type IN ('debtor', 'both')", (client_id,))
    debtor_ids = [r["id"] for r in cursor.fetchall()]

    debtors_balance = 0.0
    for p_id in debtor_ids:
        _, _, bal, bal_type, _, _ = get_party_ledger(client_id, p_id)
        if bal_type == "Dr":
            debtors_balance += bal
        else:
            debtors_balance -= bal

    cursor.execute("SELECT id FROM parties WHERE client_id = ? AND party_type IN ('creditor', 'both')", (client_id,))
    creditor_ids = [r["id"] for r in cursor.fetchall()]

    creditors_balance = 0.0
    for p_id in creditor_ids:
        _, _, bal, bal_type, _, _ = get_party_ledger(client_id, p_id)
        if bal_type == "Cr":
            creditors_balance += bal
        else:
            creditors_balance -= bal

    cursor.execute("""
        SELECT * FROM invoices WHERE client_id = ? ORDER BY invoice_date DESC, id DESC LIMIT 5
    """, (client_id,))
    recent_sales = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT * FROM purchases WHERE client_id = ? ORDER BY bill_date DESC, id DESC LIMIT 5
    """, (client_id,))
    recent_purchases = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT * FROM payments WHERE client_id = ? ORDER BY payment_date DESC, id DESC LIMIT 5
    """, (client_id,))
    recent_payments = [dict(r) for r in cursor.fetchall()]

    conn.close()

    stats = {
        "sales_count": sales_stat["cnt"],
        "total_sales": sales_stat["total"],
        "sales_tax": sales_stat["tax"],
        "purchases_count": pur_stat["cnt"],
        "total_purchases": pur_stat["total"],
        "purchases_tax": pur_stat["tax"],
        "debtors_balance": max(0.0, round(debtors_balance, 2)),
        "creditors_balance": max(0.0, round(creditors_balance, 2))
    }

    return templates.TemplateResponse(request=request, name="client/dashboard.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "stats": stats,
        "recent_sales": recent_sales,
        "recent_purchases": recent_purchases,
        "recent_payments": recent_payments,
        "msg": request.query_params.get("msg")
    })

@router.get("/profile", response_class=HTMLResponse)
async def company_profile_page(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(request=request, name="client/company_profile.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "msg": request.query_params.get("msg")
    })

@router.post("/profile")
async def update_company_profile(
    request: Request,
    business_name: str = Form(...),
    trade_name: str = Form(None),
    gstin: str = Form(None),
    state_code: str = Form(...),
    state_name: str = Form(...),
    address: str = Form(None),
    city: str = Form(None),
    pincode: str = Form(None),
    phone: str = Form(...),
    email: str = Form(None),
    bank_name: str = Form(None),
    account_no: str = Form(None),
    ifsc_code: str = Form(None),
    branch: str = Form(None),
    upi_id: str = Form(None),
    invoice_prefix: str = Form("INV/26-27/")
):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clients SET
            business_name = ?, trade_name = ?, gstin = ?, state_code = ?, state_name = ?,
            address = ?, city = ?, pincode = ?, phone = ?, email = ?,
            bank_name = ?, account_no = ?, ifsc_code = ?, branch = ?, upi_id = ?,
            invoice_prefix = ?
        WHERE id = ?
    """, (
        business_name.strip(), (trade_name or "").strip(), (gstin or "").strip().upper(),
        state_code.strip(), state_name.strip(), (address or "").strip(),
        (city or "").strip(), (pincode or "").strip(), phone.strip(),
        (email or "").strip(), (bank_name or "").strip(), (account_no or "").strip(),
        (ifsc_code or "").strip().upper(), (branch or "").strip(), (upi_id or "").strip(),
        (invoice_prefix or "INV/26-27/").strip(), client_id
    ))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "PROFILE", client_id, "Updated company profile & GST details")

    return RedirectResponse("/profile?msg=Company+profile+saved+successfully", status_code=302)
