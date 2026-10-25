import json
from datetime import datetime
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db
from app.auth import get_current_user, get_active_client_id, log_audit
from app.gst_utils import is_interstate, calculate_item_taxes, amount_to_words_indian
from app.routers.client_router import get_context

router = APIRouter(prefix="/sales")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("", response_class=HTMLResponse)
async def list_sales(request: Request, q: str = None, from_date: str = None, to_date: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM invoices WHERE client_id = ?"
    params = [client_id]

    if q and q.strip():
        query += " AND (invoice_number LIKE ? OR party_name LIKE ?)"
        term = f"%{q.strip()}%"
        params.extend([term, term])
    if from_date:
        query += " AND invoice_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND invoice_date <= ?"
        params.append(to_date)

    query += " ORDER BY invoice_date DESC, id DESC"
    cursor.execute(query, params)
    invoices = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="client/sales_list.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "invoices": invoices,
        "query_search": q,
        "from_date": from_date,
        "to_date": to_date,
        "msg": request.query_params.get("msg")
    })

@router.get("/new", response_class=HTMLResponse)
async def new_invoice_page(request: Request):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN ('debtor', 'both') ORDER BY name ASC", (client_id,))
    parties = [dict(r) for r in cursor.fetchall()]

    prefix = active_client.get("invoice_prefix") or "INV/"
    next_no = active_client.get("next_invoice_no") or 1
    suggested = f"{prefix}{str(next_no).zfill(3)}"

    today_date = datetime.now().strftime("%Y-%m-%d")
    conn.close()

    return templates.TemplateResponse(request=request, name="client/sale_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "suggested_invoice_no": suggested,
        "today_date": today_date,
        "invoice": None,
        "existing_items_json": "[]"
    })

@router.post("/new")
async def create_invoice(request: Request):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    form_data = await request.form()

    party_id = int(form_data.get("party_id"))
    invoice_number = form_data.get("invoice_number").strip()
    invoice_date = form_data.get("invoice_date").strip()
    place_of_supply = form_data.get("place_of_supply").strip()
    is_interstate_val = int(form_data.get("is_interstate", 0))
    notes = (form_data.get("notes") or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM parties WHERE id = ? AND client_id = ?", (party_id, client_id))
    party = cursor.fetchone()
    if not party:
        conn.close()
        return RedirectResponse("/sales?err=Party+not+found", status_code=302)

    party_name = party["name"]
    party_gstin = party["gstin"] or ""

    descriptions = form_data.getlist("item_description[]")
    hsn_list = form_data.getlist("hsn_sac[]")
    quantities = form_data.getlist("quantity[]")
    units = form_data.getlist("unit[]")
    rates = form_data.getlist("unit_price[]")
    discounts = form_data.getlist("discount_pct[]")
    gst_rates = form_data.getlist("gst_rate[]")

    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    items_to_insert = []

    for i in range(len(descriptions)):
        desc = descriptions[i].strip()
        if not desc:
            continue
        hsn = hsn_list[i].strip() if i < len(hsn_list) else ""
        qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
        unit = units[i] if i < len(units) else "PCS"
        rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
        disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
        gst_r = float(gst_rates[i]) if i < len(gst_rates) and gst_rates[i] else 18.0

        base = qty * rate
        taxable = round(base - (base * (disc / 100.0)), 2)

        taxes = calculate_item_taxes(taxable, gst_r, bool(is_interstate_val))
        total_taxable += taxes["taxable_value"]
        total_cgst += taxes["cgst_amount"]
        total_sgst += taxes["sgst_amount"]
        total_igst += taxes["igst_amount"]

        items_to_insert.append((
            desc, hsn, qty, unit, rate, disc, taxes["taxable_value"],
            gst_r, taxes["cgst_rate"], taxes["cgst_amount"],
            taxes["sgst_rate"], taxes["sgst_amount"],
            taxes["igst_rate"], taxes["igst_amount"],
            taxes["total_amount"]
        ))

    total_tax = round(total_cgst + total_sgst + total_igst, 2)
    raw_grand_total = total_taxable + total_tax
    rounded_grand_total = round(raw_grand_total)
    round_off = round(rounded_grand_total - raw_grand_total, 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO invoices (
            client_id, invoice_number, invoice_date, party_id, party_name, party_gstin,
            place_of_supply, is_interstate, taxable_amount, cgst_amount, sgst_amount,
            igst_amount, total_tax, round_off, grand_total, paid_amount, status, notes,
            created_by_user_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'unpaid', ?, ?, ?, ?)
    """, (
        client_id, invoice_number, invoice_date, party_id, party_name, party_gstin,
        place_of_supply, is_interstate_val, total_taxable, total_cgst, total_sgst,
        total_igst, total_tax, round_off, rounded_grand_total, notes,
        user["id"], now, now
    ))
    invoice_id = cursor.lastrowid

    for item in items_to_insert:
        cursor.execute("""
            INSERT INTO invoice_items (
                invoice_id, item_description, hsn_sac, quantity, unit, unit_price,
                discount_pct, taxable_value, gst_rate, cgst_rate, cgst_amount,
                sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (invoice_id, *item))

    cursor.execute("UPDATE clients SET next_invoice_no = next_invoice_no + 1 WHERE id = ?", (client_id,))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "INVOICE", invoice_id, f"Created invoice {invoice_number} for ₹ {rounded_grand_total}")

    return RedirectResponse(f"/sales/{invoice_id}/print?msg=Invoice+generated+successfully", status_code=302)

@router.get("/{invoice_id}", response_class=HTMLResponse)
async def view_invoice(request: Request, invoice_id: int):
    return RedirectResponse(f"/sales/{invoice_id}/print", status_code=302)

@router.get("/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice(request: Request, invoice_id: int):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        return RedirectResponse("/sales?err=Invoice+not+found", status_code=302)

    inv = dict(inv)
    if user["role"] != "admin" and inv["client_id"] != active_client["id"]:
        conn.close()
        return RedirectResponse("/sales?err=Access+denied", status_code=302)

    cursor.execute("SELECT * FROM clients WHERE id = ?", (inv["client_id"],))
    client_dict = dict(cursor.fetchone())

    cursor.execute("SELECT * FROM parties WHERE id = ?", (inv["party_id"],))
    party = cursor.fetchone()
    party_dict = dict(party) if party else {"name": inv["party_name"], "gstin": inv["party_gstin"]}

    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id ASC", (invoice_id,))
    items = [dict(r) for r in cursor.fetchall()]

    conn.close()

    words = amount_to_words_indian(inv["grand_total"])

    return templates.TemplateResponse(request=request, name="client/invoice_view.html", context={
        "user": user,
        "client": client_dict,
        "active_client": active_client,
        "all_clients": all_clients,
        "invoice": inv,
        "party": party_dict,
        "items": items,
        "amount_words": words,
        "msg": request.query_params.get("msg")
    })

@router.get("/{invoice_id}/edit", response_class=HTMLResponse)
async def edit_invoice_page(request: Request, invoice_id: int):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        return RedirectResponse("/sales?err=Invoice+not+found", status_code=302)

    inv = dict(inv)
    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN ('debtor', 'both') ORDER BY name ASC", (inv["client_id"],))
    parties = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id ASC", (invoice_id,))
    items = [dict(r) for r in cursor.fetchall()]
    items_json = json.dumps(items)

    conn.close()

    return templates.TemplateResponse(request=request, name="client/sale_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "invoice": inv,
        "today_date": inv["invoice_date"],
        "suggested_invoice_no": inv["invoice_number"],
        "existing_items_json": items_json
    })

@router.post("/{invoice_id}/edit")
async def update_invoice(request: Request, invoice_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    form_data = await request.form()
    party_id = int(form_data.get("party_id"))
    invoice_number = form_data.get("invoice_number").strip()
    invoice_date = form_data.get("invoice_date").strip()
    place_of_supply = form_data.get("place_of_supply").strip()
    is_interstate_val = int(form_data.get("is_interstate", 0))
    notes = (form_data.get("notes") or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    old_inv = cursor.fetchone()
    if not old_inv:
        conn.close()
        return RedirectResponse("/sales?err=Invoice+not+found", status_code=302)

    client_id = old_inv["client_id"]
    cursor.execute("SELECT * FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    party_name = party["name"] if party else old_inv["party_name"]
    party_gstin = party["gstin"] if party else old_inv["party_gstin"]

    descriptions = form_data.getlist("item_description[]")
    hsn_list = form_data.getlist("hsn_sac[]")
    quantities = form_data.getlist("quantity[]")
    units = form_data.getlist("unit[]")
    rates = form_data.getlist("unit_price[]")
    discounts = form_data.getlist("discount_pct[]")
    gst_rates = form_data.getlist("gst_rate[]")

    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    items_to_insert = []

    for i in range(len(descriptions)):
        desc = descriptions[i].strip()
        if not desc:
            continue
        hsn = hsn_list[i].strip() if i < len(hsn_list) else ""
        qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
        unit = units[i] if i < len(units) else "PCS"
        rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
        disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
        gst_r = float(gst_rates[i]) if i < len(gst_rates) and gst_rates[i] else 18.0

        base = qty * rate
        taxable = round(base - (base * (disc / 100.0)), 2)

        taxes = calculate_item_taxes(taxable, gst_r, bool(is_interstate_val))
        total_taxable += taxes["taxable_value"]
        total_cgst += taxes["cgst_amount"]
        total_sgst += taxes["sgst_amount"]
        total_igst += taxes["igst_amount"]

        items_to_insert.append((
            desc, hsn, qty, unit, rate, disc, taxes["taxable_value"],
            gst_r, taxes["cgst_rate"], taxes["cgst_amount"],
            taxes["sgst_rate"], taxes["sgst_amount"],
            taxes["igst_rate"], taxes["igst_amount"],
            taxes["total_amount"]
        ))

    total_tax = round(total_cgst + total_sgst + total_igst, 2)
    raw_grand_total = total_taxable + total_tax
    rounded_grand_total = round(raw_grand_total)
    round_off = round(rounded_grand_total - raw_grand_total, 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE invoices SET
            invoice_number = ?, invoice_date = ?, party_id = ?, party_name = ?, party_gstin = ?,
            place_of_supply = ?, is_interstate = ?, taxable_amount = ?, cgst_amount = ?, sgst_amount = ?,
            igst_amount = ?, total_tax = ?, round_off = ?, grand_total = ?, notes = ?, updated_at = ?
        WHERE id = ?
    """, (
        invoice_number, invoice_date, party_id, party_name, party_gstin,
        place_of_supply, is_interstate_val, total_taxable, total_cgst, total_sgst,
        total_igst, total_tax, round_off, rounded_grand_total, notes, now, invoice_id
    ))

    cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    for item in items_to_insert:
        cursor.execute("""
            INSERT INTO invoice_items (
                invoice_id, item_description, hsn_sac, quantity, unit, unit_price,
                discount_pct, taxable_value, gst_rate, cgst_rate, cgst_amount,
                sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (invoice_id, *item))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "INVOICE", invoice_id, f"Corrected invoice {invoice_number} (Amount: ₹ {rounded_grand_total})")

    return RedirectResponse(f"/sales/{invoice_id}/print?msg=Invoice+corrected+and+updated+successfully", status_code=302)

@router.post("/{invoice_id}/delete")
async def delete_invoice(request: Request, invoice_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        return RedirectResponse("/sales", status_code=302)

    inv_num = inv["invoice_number"]
    client_id = inv["client_id"]

    cursor.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "DELETE", "INVOICE", invoice_id, f"Deleted invoice {inv_num}")

    return RedirectResponse("/sales?msg=Invoice+deleted", status_code=302)
