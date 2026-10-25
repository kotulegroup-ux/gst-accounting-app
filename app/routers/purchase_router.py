import json
from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db
from app.auth import get_current_user, log_audit
from app.gst_utils import calculate_item_taxes
from app.routers.client_router import get_context

router = APIRouter(prefix="/purchases")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("", response_class=HTMLResponse)
async def list_purchases(request: Request, q: str = None, from_date: str = None, to_date: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM purchases WHERE client_id = ?"
    params = [client_id]

    if q and q.strip():
        query += " AND (bill_number LIKE ? OR party_name LIKE ?)"
        term = f"%{q.strip()}%"
        params.extend([term, term])
    if from_date:
        query += " AND bill_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND bill_date <= ?"
        params.append(to_date)

    query += " ORDER BY bill_date DESC, id DESC"
    cursor.execute(query, params)
    purchases = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(request=request, name="client/purchases_list.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "purchases": purchases,
        "query_search": q,
        "from_date": from_date,
        "to_date": to_date,
        "msg": request.query_params.get("msg")
    })

@router.get("/new", response_class=HTMLResponse)
async def new_purchase_page(request: Request):
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

    return templates.TemplateResponse(request=request, name="client/purchase_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "today_date": today_date,
        "purchase": None,
        "existing_items_json": "[]"
    })

@router.post("/new")
async def create_purchase(request: Request):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    form_data = await request.form()

    party_id = int(form_data.get("party_id"))
    bill_number = form_data.get("bill_number").strip()
    bill_date = form_data.get("bill_date").strip()
    is_interstate_val = int(form_data.get("is_interstate", 0))
    itc_eligible = int(form_data.get("itc_eligible", 1))
    notes = (form_data.get("notes") or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM parties WHERE id = ? AND client_id = ?", (party_id, client_id))
    party = cursor.fetchone()
    if not party:
        conn.close()
        return RedirectResponse("/purchases?err=Supplier+not+found", status_code=302)

    party_name = party["name"]
    party_gstin = party["gstin"] or ""

    descriptions = form_data.getlist("item_description[]")
    hsn_list = form_data.getlist("hsn_sac[]")
    quantities = form_data.getlist("quantity[]")
    units = form_data.getlist("unit[]")
    rates = form_data.getlist("unit_price[]")
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
        gst_r = float(gst_rates[i]) if i < len(gst_rates) and gst_rates[i] else 18.0

        taxable = round(qty * rate, 2)
        taxes = calculate_item_taxes(taxable, gst_r, bool(is_interstate_val))

        total_taxable += taxes["taxable_value"]
        total_cgst += taxes["cgst_amount"]
        total_sgst += taxes["sgst_amount"]
        total_igst += taxes["igst_amount"]

        items_to_insert.append((
            desc, hsn, qty, unit, rate, taxes["taxable_value"],
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
        INSERT INTO purchases (
            client_id, bill_number, bill_date, party_id, party_name, party_gstin,
            is_interstate, taxable_amount, cgst_amount, sgst_amount, igst_amount,
            total_tax, round_off, grand_total, paid_amount, itc_eligible, notes,
            created_by_user_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?)
    """, (
        client_id, bill_number, bill_date, party_id, party_name, party_gstin,
        is_interstate_val, total_taxable, total_cgst, total_sgst, total_igst,
        total_tax, round_off, rounded_grand_total, itc_eligible, notes,
        user["id"], now, now
    ))
    purchase_id = cursor.lastrowid

    for item in items_to_insert:
        cursor.execute("""
            INSERT INTO purchase_items (
                purchase_id, item_description, hsn_sac, quantity, unit, unit_price,
                taxable_value, gst_rate, cgst_rate, cgst_amount,
                sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (purchase_id, *item))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "CREATE", "PURCHASE", purchase_id, f"Recorded purchase bill {bill_number} for ₹ {rounded_grand_total}")

    return RedirectResponse("/purchases?msg=Purchase+bill+recorded+successfully", status_code=302)

@router.get("/{purchase_id}/edit", response_class=HTMLResponse)
async def edit_purchase_page(request: Request, purchase_id: int):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    pur = cursor.fetchone()
    if not pur:
        conn.close()
        return RedirectResponse("/purchases?err=Purchase+not+found", status_code=302)

    pur = dict(pur)
    cursor.execute("SELECT * FROM parties WHERE client_id = ? AND party_type IN ('creditor', 'both') ORDER BY name ASC", (pur["client_id"],))
    parties = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM purchase_items WHERE purchase_id = ? ORDER BY id ASC", (purchase_id,))
    items = [dict(r) for r in cursor.fetchall()]
    items_json = json.dumps(items)

    conn.close()

    return templates.TemplateResponse(request=request, name="client/purchase_form.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "parties": parties,
        "purchase": pur,
        "today_date": pur["bill_date"],
        "existing_items_json": items_json
    })

@router.post("/{purchase_id}/edit")
async def update_purchase(request: Request, purchase_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    form_data = await request.form()
    party_id = int(form_data.get("party_id"))
    bill_number = form_data.get("bill_number").strip()
    bill_date = form_data.get("bill_date").strip()
    is_interstate_val = int(form_data.get("is_interstate", 0))
    itc_eligible = int(form_data.get("itc_eligible", 1))
    notes = (form_data.get("notes") or "").strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    old_pur = cursor.fetchone()
    if not old_pur:
        conn.close()
        return RedirectResponse("/purchases?err=Purchase+not+found", status_code=302)

    client_id = old_pur["client_id"]
    cursor.execute("SELECT * FROM parties WHERE id = ?", (party_id,))
    party = cursor.fetchone()
    party_name = party["name"] if party else old_pur["party_name"]
    party_gstin = party["gstin"] if party else old_pur["party_gstin"]

    descriptions = form_data.getlist("item_description[]")
    hsn_list = form_data.getlist("hsn_sac[]")
    quantities = form_data.getlist("quantity[]")
    units = form_data.getlist("unit[]")
    rates = form_data.getlist("unit_price[]")
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
        gst_r = float(gst_rates[i]) if i < len(gst_rates) and gst_rates[i] else 18.0

        taxable = round(qty * rate, 2)
        taxes = calculate_item_taxes(taxable, gst_r, bool(is_interstate_val))

        total_taxable += taxes["taxable_value"]
        total_cgst += taxes["cgst_amount"]
        total_sgst += taxes["sgst_amount"]
        total_igst += taxes["igst_amount"]

        items_to_insert.append((
            desc, hsn, qty, unit, rate, taxes["taxable_value"],
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
        UPDATE purchases SET
            bill_number = ?, bill_date = ?, party_id = ?, party_name = ?, party_gstin = ?,
            is_interstate = ?, taxable_amount = ?, cgst_amount = ?, sgst_amount = ?,
            igst_amount = ?, total_tax = ?, round_off = ?, grand_total = ?, itc_eligible = ?,
            notes = ?, updated_at = ?
        WHERE id = ?
    """, (
        bill_number, bill_date, party_id, party_name, party_gstin,
        is_interstate_val, total_taxable, total_cgst, total_sgst,
        total_igst, total_tax, round_off, rounded_grand_total, itc_eligible,
        notes, now, purchase_id
    ))

    cursor.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
    for item in items_to_insert:
        cursor.execute("""
            INSERT INTO purchase_items (
                purchase_id, item_description, hsn_sac, quantity, unit, unit_price,
                taxable_value, gst_rate, cgst_rate, cgst_amount,
                sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (purchase_id, *item))

    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "UPDATE", "PURCHASE", purchase_id, f"Corrected purchase bill {bill_number} (Amount: ₹ {rounded_grand_total})")

    return RedirectResponse("/purchases?msg=Purchase+bill+updated+successfully", status_code=302)

@router.post("/{purchase_id}/delete")
async def delete_purchase(request: Request, purchase_id: int):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
    pur = cursor.fetchone()
    if not pur:
        conn.close()
        return RedirectResponse("/purchases", status_code=302)

    bill_num = pur["bill_number"]
    client_id = pur["client_id"]

    cursor.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
    conn.commit()
    conn.close()

    log_audit(client_id, user["id"], user["full_name"], "DELETE", "PURCHASE", purchase_id, f"Deleted purchase bill {bill_num}")

    return RedirectResponse("/purchases?msg=Purchase+bill+deleted", status_code=302)
