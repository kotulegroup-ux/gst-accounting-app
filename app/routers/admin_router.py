from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
from app.database import get_db, hash_password
from app.auth import get_current_user, get_active_client_id, log_audit

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/clients", response_class=HTMLResponse)
async def list_clients(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            c.*,
            u.username as login_username,
            (SELECT COUNT(*) FROM invoices WHERE client_id = c.id) as invoices_count,
            (SELECT COALESCE(SUM(grand_total), 0) FROM invoices WHERE client_id = c.id) as total_sales
        FROM clients c
        LEFT JOIN users u ON u.client_id = c.id
        ORDER BY c.id ASC
    """)
    clients = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM clients WHERE id = ?", (request.session.get("admin_active_client_id"),))
    active_client = cursor.fetchone()
    active_client = dict(active_client) if active_client else (clients[0] if clients else None)

    conn.close()

    return templates.TemplateResponse(request=request, name="admin/clients_list.html", context={
        "user": user,
        "clients": clients,
        "all_clients": clients,
        "active_client": active_client,
        "msg": request.query_params.get("msg")
    })

@router.post("/switch-client")
async def switch_client(request: Request, client_id: int = Form(...)):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    request.session["admin_active_client_id"] = client_id
    referer = request.headers.get("referer") or "/"
    return RedirectResponse(referer, status_code=302)

@router.get("/clients/new", response_class=HTMLResponse)
async def new_client_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients ORDER BY id ASC")
    all_clients = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM clients WHERE id = ?", (request.session.get("admin_active_client_id"),))
    active_client = cursor.fetchone()
    active_client = dict(active_client) if active_client else None
    conn.close()

    return templates.TemplateResponse(request=request, name="admin/client_form.html", context={
        "user": user,
        "edit_client": None,
        "all_clients": all_clients,
        "active_client": active_client
    })

@router.post("/clients/new")
async def create_client(
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
    password: str = Form(...),
    bank_name: str = Form(None),
    account_no: str = Form(None),
    ifsc_code: str = Form(None),
    branch: str = Form(None),
    upi_id: str = Form(None),
    invoice_prefix: str = Form("INV/26-27/")
):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO clients (
            business_name, trade_name, gstin, state_code, state_name,
            address, city, pincode, phone, email,
            bank_name, account_no, ifsc_code, branch, upi_id,
            invoice_prefix, next_invoice_no, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (
        business_name.strip(), (trade_name or "").strip(), (gstin or "").strip().upper(),
        state_code.strip(), state_name.strip(), (address or "").strip(),
        (city or "").strip(), (pincode or "").strip(), phone.strip(),
        (email or "").strip(), (bank_name or "").strip(), (account_no or "").strip(),
        (ifsc_code or "").strip().upper(), (branch or "").strip(), (upi_id or "").strip(),
        (invoice_prefix or "INV/26-27/").strip(), now
    ))
    client_id = cursor.lastrowid

    username = phone.strip()
    pwd_hash = hash_password(password.strip())
    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role, client_id, is_active, created_at)
        VALUES (?, ?, ?, 'client', ?, 1, ?)
    """, (username, pwd_hash, business_name.strip(), client_id, now))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "CLIENT", client_id, f"Registered new client: {business_name}")

    request.session["admin_active_client_id"] = client_id
    return RedirectResponse("/admin/clients?msg=Client+registered+successfully", status_code=302)

@router.get("/clients/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_page(request: Request, client_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    client_row = cursor.fetchone()
    if not client_row:
        conn.close()
        return RedirectResponse("/admin/clients", status_code=302)

    cursor.execute("SELECT * FROM clients ORDER BY id ASC")
    all_clients = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="admin/client_form.html", context={
        "user": user,
        "edit_client": dict(client_row),
        "all_clients": all_clients,
        "active_client": dict(client_row)
    })

@router.post("/clients/{client_id}/edit")
async def update_client(
    request: Request,
    client_id: int,
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
    password: str = Form(None),
    bank_name: str = Form(None),
    account_no: str = Form(None),
    ifsc_code: str = Form(None),
    branch: str = Form(None),
    upi_id: str = Form(None),
    invoice_prefix: str = Form("INV/26-27/")
):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

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

    cursor.execute("UPDATE users SET username = ?, full_name = ? WHERE client_id = ?", (phone.strip(), business_name.strip(), client_id))

    if password and password.strip():
        pwd_hash = hash_password(password.strip())
        cursor.execute("UPDATE users SET password_hash = ? WHERE client_id = ?", (pwd_hash, client_id))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "CLIENT", client_id, f"Updated profile for: {business_name}")

    return RedirectResponse("/admin/clients?msg=Client+updated+successfully", status_code=302)

@router.post("/clients/{client_id}/delete")
async def delete_client(request: Request, client_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT business_name FROM clients WHERE id = ?", (client_id,))
    cl = cursor.fetchone()
    name = cl["business_name"] if cl else f"ID {client_id}"

    cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    cursor.execute("DELETE FROM users WHERE client_id = ?", (client_id,))
    conn.commit()

    if request.session.get("admin_active_client_id") == client_id:
        cursor.execute("SELECT id FROM clients ORDER BY id ASC LIMIT 1")
        next_c = cursor.fetchone()
        request.session["admin_active_client_id"] = next_c["id"] if next_c else None

    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "DELETE", "CLIENT", client_id, f"Deleted client business: {name}")

    return RedirectResponse("/admin/clients?msg=Client+deleted", status_code=302)

@router.get("/audit-log", response_class=HTMLResponse)
async def audit_log(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200")
    logs = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM clients ORDER BY id ASC")
    all_clients = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM clients WHERE id = ?", (request.session.get("admin_active_client_id"),))
    active_client = cursor.fetchone()
    active_client = dict(active_client) if active_client else None
    conn.close()

    return templates.TemplateResponse(request=request, name="admin/audit_log.html", context={
        "user": user,
        "logs": logs,
        "all_clients": all_clients,
        "active_client": active_client
    })
