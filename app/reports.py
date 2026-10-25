"""
Reporting Engine: Ledger statements, GSTR-1, GSTR-3B computation, and Excel export.
"""
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from app.database import get_db

def get_party_ledger(client_id: int, party_id: int, start_date: str = None, end_date: str = None):
    """
    Computes a chronological ledger statement for a debtor or creditor.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Fetch party details
    cursor.execute("SELECT * FROM parties WHERE id = ? AND client_id = ?", (party_id, client_id))
    party = cursor.fetchone()
    if not party:
        conn.close()
        return None, [], 0.0, "Dr"

    party = dict(party)
    opening_bal = float(party.get("opening_balance") or 0.0)
    opening_type = party.get("opening_balance_type", "Dr")

    # Fetch Invoices (Sales) -> Debits the customer (Increases receivable)
    cursor.execute("""
        SELECT 
            id as ref_id, invoice_date as tx_date, invoice_number as voucher_no,
            'Sales Invoice' as voucher_type, grand_total as debit, 0.0 as credit,
            notes as narration
        FROM invoices
        WHERE client_id = ? AND party_id = ?
    """, (client_id, party_id))
    invoices = [dict(r) for r in cursor.fetchall()]

    # Fetch Purchases -> Credits the supplier (Increases payable)
    cursor.execute("""
        SELECT 
            id as ref_id, bill_date as tx_date, bill_number as voucher_no,
            'Purchase Bill' as voucher_type, 0.0 as debit, grand_total as credit,
            notes as narration
        FROM purchases
        WHERE client_id = ? AND party_id = ?
    """, (client_id, party_id))
    purchases = [dict(r) for r in cursor.fetchall()]

    # Fetch Payments Received (Debtor pays -> Credit debtor)
    cursor.execute("""
        SELECT 
            id as ref_id, payment_date as tx_date, COALESCE(reference_no, 'RCPT-' || id) as voucher_no,
            'Payment Received (' || payment_mode || ')' as voucher_type, 0.0 as debit, amount as credit,
            remarks as narration
        FROM payments
        WHERE client_id = ? AND party_id = ? AND payment_type = 'received'
    """, (client_id, party_id))
    payments_in = [dict(r) for r in cursor.fetchall()]

    # Fetch Payments Made (Pay to Creditor -> Debit creditor)
    cursor.execute("""
        SELECT 
            id as ref_id, payment_date as tx_date, COALESCE(reference_no, 'PMT-' || id) as voucher_no,
            'Payment Made (' || payment_mode || ')' as voucher_type, amount as debit, 0.0 as credit,
            remarks as narration
        FROM payments
        WHERE client_id = ? AND party_id = ? AND payment_type = 'made'
    """, (client_id, party_id))
    payments_out = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # Combine all transactions
    all_txs = invoices + purchases + payments_in + payments_out

    # Filter by date if specified
    if start_date:
        all_txs = [t for t in all_txs if t["tx_date"] >= start_date]
    if end_date:
        all_txs = [t for t in all_txs if t["tx_date"] <= end_date]

    # Sort chronologically
    all_txs.sort(key=lambda x: (x["tx_date"], x["voucher_no"]))

    # Calculate running balance
    # Convention: Debit balance is positive (>0), Credit balance is negative (<0)
    current_net = opening_bal if opening_type == "Dr" else -opening_bal

    ledger_entries = []
    total_debit = 0.0
    total_credit = 0.0

    for tx in all_txs:
        d = float(tx["debit"] or 0)
        c = float(tx["credit"] or 0)
        total_debit += d
        total_credit += c
        current_net += (d - c)

        bal_type = "Dr" if current_net >= 0 else "Cr"
        bal_display = abs(current_net)

        tx_entry = dict(tx)
        tx_entry["running_balance"] = round(bal_display, 2)
        tx_entry["running_type"] = bal_type
        ledger_entries.append(tx_entry)

    closing_balance = abs(current_net)
    closing_type = "Dr" if current_net >= 0 else "Cr"

    return party, ledger_entries, round(closing_balance, 2), closing_type, round(total_debit, 2), round(total_credit, 2)

def get_gstr1_report(client_id: int, start_date: str = None, end_date: str = None):
    """
    Generates GSTR-1 outward supplies summary:
    - B2B Invoices (parties with valid GSTIN)
    - B2C Invoices (unregistered / without GSTIN)
    - HSN Summary
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT inv.*, p.gstin as party_gstin_actual, p.state_code as party_state_code, p.state_name as party_state_name
        FROM invoices inv
        JOIN parties p ON inv.party_id = p.id
        WHERE inv.client_id = ?
    """
    params = [client_id]
    if start_date:
        query += " AND inv.invoice_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND inv.invoice_date <= ?"
        params.append(end_date)
    query += " ORDER BY inv.invoice_date ASC, inv.invoice_number ASC"

    cursor.execute(query, params)
    invoices = [dict(r) for r in cursor.fetchall()]

    b2b = []
    b2c = []
    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    total_invoice_val = 0.0

    for inv in invoices:
        gstin = (inv.get("party_gstin") or inv.get("party_gstin_actual") or "").strip()
        total_taxable += float(inv["taxable_amount"] or 0)
        total_cgst += float(inv["cgst_amount"] or 0)
        total_sgst += float(inv["sgst_amount"] or 0)
        total_igst += float(inv["igst_amount"] or 0)
        total_invoice_val += float(inv["grand_total"] or 0)

        if gstin and len(gstin) == 15:
            b2b.append(inv)
        else:
            b2c.append(inv)

    # HSN Summary
    hsn_query = """
        SELECT 
            it.hsn_sac,
            it.item_description,
            it.unit,
            SUM(it.quantity) as total_qty,
            SUM(it.taxable_value) as total_taxable,
            SUM(it.cgst_amount) as total_cgst,
            SUM(it.sgst_amount) as total_sgst,
            SUM(it.igst_amount) as total_igst,
            SUM(it.total_amount) as total_value
        FROM invoice_items it
        JOIN invoices inv ON it.invoice_id = inv.id
        WHERE inv.client_id = ?
    """
    hsn_params = [client_id]
    if start_date:
        hsn_query += " AND inv.invoice_date >= ?"
        hsn_params.append(start_date)
    if end_date:
        hsn_query += " AND inv.invoice_date <= ?"
        hsn_params.append(end_date)
    hsn_query += " GROUP BY it.hsn_sac, it.unit ORDER BY it.hsn_sac ASC"

    cursor.execute(hsn_query, hsn_params)
    hsn_summary = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "b2b": b2b,
        "b2c": b2c,
        "hsn_summary": hsn_summary,
        "totals": {
            "taxable_amount": round(total_taxable, 2),
            "cgst_amount": round(total_cgst, 2),
            "sgst_amount": round(total_sgst, 2),
            "igst_amount": round(total_igst, 2),
            "total_tax": round(total_cgst + total_sgst + total_igst, 2),
            "grand_total": round(total_invoice_val, 2)
        }
    }

def get_gstr3b_report(client_id: int, start_date: str = None, end_date: str = None):
    """
    Generates GSTR-3B Tax Return Summary:
    1. Table 3.1: Tax on Outward Supplies (Sales)
    2. Table 4: Eligible Input Tax Credit (ITC) from Inward Supplies (Purchases)
    3. Table 5.1: Net GST Tax Payable
    """
    conn = get_db()
    cursor = conn.cursor()

    # 1. Outward Supplies (Invoices)
    inv_query = """
        SELECT 
            SUM(taxable_amount) as taxable_amount,
            SUM(cgst_amount) as cgst_amount,
            SUM(sgst_amount) as sgst_amount,
            SUM(igst_amount) as igst_amount,
            SUM(total_tax) as total_tax,
            SUM(grand_total) as grand_total
        FROM invoices
        WHERE client_id = ?
    """
    inv_params = [client_id]
    if start_date:
        inv_query += " AND invoice_date >= ?"
        inv_params.append(start_date)
    if end_date:
        inv_query += " AND invoice_date <= ?"
        inv_params.append(end_date)

    cursor.execute(inv_query, inv_params)
    outward = dict(cursor.fetchone() or {})
    for k in ["taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_tax", "grand_total"]:
        outward[k] = round(float(outward.get(k) or 0.0), 2)

    # 2. Eligible Inward Supplies / ITC (Purchases where itc_eligible = 1)
    pur_query = """
        SELECT 
            SUM(taxable_amount) as taxable_amount,
            SUM(cgst_amount) as cgst_amount,
            SUM(sgst_amount) as sgst_amount,
            SUM(igst_amount) as igst_amount,
            SUM(total_tax) as total_tax,
            SUM(grand_total) as grand_total
        FROM purchases
        WHERE client_id = ? AND itc_eligible = 1
    """
    pur_params = [client_id]
    if start_date:
        pur_query += " AND bill_date >= ?"
        pur_params.append(start_date)
    if end_date:
        pur_query += " AND bill_date <= ?"
        pur_params.append(end_date)

    cursor.execute(pur_query, pur_params)
    itc = dict(cursor.fetchone() or {})
    for k in ["taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_tax", "grand_total"]:
        itc[k] = round(float(itc.get(k) or 0.0), 2)

    conn.close()

    # 3. Net Tax Payable (Liability minus ITC)
    net_cgst = max(0.0, outward["cgst_amount"] - itc["cgst_amount"])
    net_sgst = max(0.0, outward["sgst_amount"] - itc["sgst_amount"])
    net_igst = max(0.0, outward["igst_amount"] - itc["igst_amount"])
    net_total = round(net_cgst + net_sgst + net_igst, 2)

    # Excess ITC available to carry forward
    excess_cgst = max(0.0, itc["cgst_amount"] - outward["cgst_amount"])
    excess_sgst = max(0.0, itc["sgst_amount"] - outward["sgst_amount"])
    excess_igst = max(0.0, itc["igst_amount"] - outward["igst_amount"])

    return {
        "outward": outward,
        "itc": itc,
        "net_payable": {
            "cgst": round(net_cgst, 2),
            "sgst": round(net_sgst, 2),
            "igst": round(net_igst, 2),
            "total": net_total
        },
        "excess_itc": {
            "cgst": round(excess_cgst, 2),
            "sgst": round(excess_sgst, 2),
            "igst": round(excess_igst, 2),
            "total": round(excess_cgst + excess_sgst + excess_igst, 2)
        }
    }

def export_gstr1_excel(client_dict: dict, report: dict, filepath: str):
    """Generates a professional multi-sheet Excel file for GSTR-1."""
    wb = openpyxl.Workbook()

    # Style presets
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Dark Blue
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
    sub_font = Font(name="Segoe UI", size=10, bold=False, color="4B5563")
    total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    total_font = Font(name="Segoe UI", size=11, bold=True, color="0F172A")
    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Sheet 1: B2B Invoices
    ws_b2b = wb.active
    ws_b2b.title = "B2B Supplies"
    ws_b2b.append([f"GSTR-1 (Table 4) B2B Invoices - {client_dict.get('business_name')} (GSTIN: {client_dict.get('gstin')})"])
    ws_b2b.cell(row=1, column=1).font = title_font

    headers_b2b = [
        "Receiver GSTIN", "Receiver Name", "Invoice No", "Invoice Date",
        "Place of Supply", "Reverse Charge", "Taxable Value (₹)",
        "CGST (₹)", "SGST (₹)", "IGST (₹)", "Invoice Value (₹)"
    ]
    ws_b2b.append([]) # blank
    ws_b2b.append(headers_b2b)
    header_row_idx = 3

    for col_idx in range(1, len(headers_b2b) + 1):
        cell = ws_b2b.cell(row=header_row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    r_idx = 4
    for inv in report["b2b"]:
        ws_b2b.append([
            inv.get("party_gstin") or inv.get("party_gstin_actual") or "",
            inv.get("party_name"),
            inv.get("invoice_number"),
            inv.get("invoice_date"),
            inv.get("place_of_supply"),
            "N",
            inv.get("taxable_amount"),
            inv.get("cgst_amount"),
            inv.get("sgst_amount"),
            inv.get("igst_amount"),
            inv.get("grand_total")
        ])
        for c_idx in range(1, len(headers_b2b) + 1):
            ws_b2b.cell(row=r_idx, column=c_idx).border = border_thin
        r_idx += 1

    # Sheet 2: B2C Invoices
    ws_b2c = wb.create_sheet(title="B2C Supplies")
    ws_b2c.append([f"GSTR-1 (Table 7) B2C Invoices - {client_dict.get('business_name')}"])
    ws_b2c.cell(row=1, column=1).font = title_font
    ws_b2c.append([])
    headers_b2c = [
        "Customer Name", "Invoice No", "Invoice Date", "Place of Supply",
        "Taxable Value (₹)", "CGST (₹)", "SGST (₹)", "IGST (₹)", "Invoice Value (₹)"
    ]
    ws_b2c.append(headers_b2c)
    for col_idx in range(1, len(headers_b2c) + 1):
        cell = ws_b2c.cell(row=3, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    r_b2c = 4
    for inv in report["b2c"]:
        ws_b2c.append([
            inv.get("party_name"),
            inv.get("invoice_number"),
            inv.get("invoice_date"),
            inv.get("place_of_supply"),
            inv.get("taxable_amount"),
            inv.get("cgst_amount"),
            inv.get("sgst_amount"),
            inv.get("igst_amount"),
            inv.get("grand_total")
        ])
        for c_idx in range(1, len(headers_b2c) + 1):
            ws_b2c.cell(row=r_b2c, column=c_idx).border = border_thin
        r_b2c += 1

    # Sheet 3: HSN Summary
    ws_hsn = wb.create_sheet(title="HSN Summary")
    ws_hsn.append([f"GSTR-1 (Table 12) HSN-wise Summary - {client_dict.get('business_name')}"])
    ws_hsn.cell(row=1, column=1).font = title_font
    ws_hsn.append([])
    headers_hsn = [
        "HSN / SAC", "Description", "UQC", "Total Qty", "Taxable Value (₹)",
        "CGST (₹)", "SGST (₹)", "IGST (₹)", "Total Value (₹)"
    ]
    ws_hsn.append(headers_hsn)
    for col_idx in range(1, len(headers_hsn) + 1):
        cell = ws_hsn.cell(row=3, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    r_hsn = 4
    for item in report["hsn_summary"]:
        ws_hsn.append([
            item.get("hsn_sac") or "N/A",
            item.get("item_description") or "",
            item.get("unit") or "PCS",
            item.get("total_qty") or 0,
            item.get("total_taxable") or 0,
            item.get("total_cgst") or 0,
            item.get("total_sgst") or 0,
            item.get("total_igst") or 0,
            item.get("total_value") or 0
        ])
        for c_idx in range(1, len(headers_hsn) + 1):
            ws_hsn.cell(row=r_hsn, column=c_idx).border = border_thin
        r_hsn += 1

    # Auto-adjust column widths
    for sheet in [ws_b2b, ws_b2c, ws_hsn]:
        for col in sheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value or '')
                if len(val) > max_len:
                    max_len = len(val)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 14)

    wb.save(filepath)
    return filepath
