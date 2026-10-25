import sqlite3
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

# Adaptive DB path for local development and Vercel serverless runtime
IS_VERCEL = bool(os.environ.get("VERCEL"))
ORIGINAL_DB_PATH = Path(__file__).resolve().parent.parent / "gst_app.db"

if IS_VERCEL:
    DB_PATH = Path("/tmp/gst_app.db")
    # If /tmp/gst_app.db doesn't exist yet in the serverless container, copy from bundled db
    if not DB_PATH.exists() and ORIGINAL_DB_PATH.exists():
        try:
            shutil.copyfile(ORIGINAL_DB_PATH, DB_PATH)
        except Exception:
            pass
else:
    DB_PATH = ORIGINAL_DB_PATH

def hash_password(password: str) -> str:
    """Deterministic hash with salt for secure storage."""
    salt = "gst_secure_salt_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Clients Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        trade_name TEXT,
        gstin TEXT,
        state_code TEXT NOT NULL,
        state_name TEXT NOT NULL,
        address TEXT,
        city TEXT,
        pincode TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        bank_name TEXT,
        account_no TEXT,
        ifsc_code TEXT,
        branch TEXT,
        upi_id TEXT,
        invoice_prefix TEXT DEFAULT 'INV-',
        next_invoice_no INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Users Table (Admin & Client logins)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, -- Mobile or Email
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'client')),
        client_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
    );
    """)

    # 3. Parties Table (Debtors/Customers & Creditors/Suppliers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        party_type TEXT NOT NULL CHECK(party_type IN ('debtor', 'creditor', 'both')),
        name TEXT NOT NULL,
        trade_name TEXT,
        gstin TEXT,
        state_code TEXT,
        state_name TEXT,
        address TEXT,
        phone TEXT,
        email TEXT,
        opening_balance REAL DEFAULT 0.0,
        opening_balance_type TEXT DEFAULT 'Dr' CHECK(opening_balance_type IN ('Dr', 'Cr')),
        created_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
    );
    """)

    # 4. Invoices (Sales)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        invoice_number TEXT NOT NULL,
        invoice_date TEXT NOT NULL,
        party_id INTEGER NOT NULL,
        party_name TEXT NOT NULL,
        party_gstin TEXT,
        place_of_supply TEXT NOT NULL,
        is_interstate INTEGER DEFAULT 0,
        taxable_amount REAL DEFAULT 0.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_amount REAL DEFAULT 0.0,
        igst_amount REAL DEFAULT 0.0,
        total_tax REAL DEFAULT 0.0,
        round_off REAL DEFAULT 0.0,
        grand_total REAL DEFAULT 0.0,
        paid_amount REAL DEFAULT 0.0,
        status TEXT DEFAULT 'unpaid',
        notes TEXT,
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
        FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE RESTRICT
    );
    """)

    # 5. Invoice Items
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        item_description TEXT NOT NULL,
        hsn_sac TEXT,
        quantity REAL DEFAULT 1,
        unit TEXT DEFAULT 'PCS',
        unit_price REAL DEFAULT 0.0,
        discount_pct REAL DEFAULT 0.0,
        taxable_value REAL DEFAULT 0.0,
        gst_rate REAL DEFAULT 18.0,
        cgst_rate REAL DEFAULT 0.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_rate REAL DEFAULT 0.0,
        sgst_amount REAL DEFAULT 0.0,
        igst_rate REAL DEFAULT 0.0,
        igst_amount REAL DEFAULT 0.0,
        total_amount REAL DEFAULT 0.0,
        FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
    );
    """)

    # 6. Purchases
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        bill_number TEXT NOT NULL,
        bill_date TEXT NOT NULL,
        party_id INTEGER NOT NULL,
        party_name TEXT NOT NULL,
        party_gstin TEXT,
        is_interstate INTEGER DEFAULT 0,
        taxable_amount REAL DEFAULT 0.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_amount REAL DEFAULT 0.0,
        igst_amount REAL DEFAULT 0.0,
        total_tax REAL DEFAULT 0.0,
        round_off REAL DEFAULT 0.0,
        grand_total REAL DEFAULT 0.0,
        paid_amount REAL DEFAULT 0.0,
        itc_eligible INTEGER DEFAULT 1,
        notes TEXT,
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
        FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE RESTRICT
    );
    """)

    # 7. Purchase Items
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER NOT NULL,
        item_description TEXT NOT NULL,
        hsn_sac TEXT,
        quantity REAL DEFAULT 1,
        unit TEXT DEFAULT 'PCS',
        unit_price REAL DEFAULT 0.0,
        taxable_value REAL DEFAULT 0.0,
        gst_rate REAL DEFAULT 18.0,
        cgst_rate REAL DEFAULT 0.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_rate REAL DEFAULT 0.0,
        sgst_amount REAL DEFAULT 0.0,
        igst_rate REAL DEFAULT 0.0,
        igst_amount REAL DEFAULT 0.0,
        total_amount REAL DEFAULT 0.0,
        FOREIGN KEY (purchase_id) REFERENCES purchases (id) ON DELETE CASCADE
    );
    """)

    # 8. Payments (Received from Debtors & Paid to Creditors)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        payment_type TEXT NOT NULL CHECK(payment_type IN ('received', 'made')),
        payment_date TEXT NOT NULL,
        party_id INTEGER NOT NULL,
        party_name TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_mode TEXT NOT NULL,
        reference_no TEXT,
        invoice_id INTEGER,
        purchase_id INTEGER,
        remarks TEXT,
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
        FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE RESTRICT
    );
    """)

    # 9. Audit Logs (to track modifications by Admin / Client)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        user_id INTEGER,
        user_name TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER,
        details TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    conn.commit()

    # Seed Default Administrator
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, role, is_active, created_at)
            VALUES (?, ?, ?, 'admin', 1, ?)
        """, ('admin', hash_password('admin123'), 'Master Administrator', now))
        conn.commit()

    # Seed Sample Demo Client if none exists
    cursor.execute("SELECT COUNT(*) as cnt FROM clients")
    if cursor.fetchone()['cnt'] == 0:
        seed_sample_data(conn)

    conn.close()

def seed_sample_data(conn):
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    # Sample Client: Rajesh Sharma (Sharma Trading Co)
    cursor.execute("""
        INSERT INTO clients (
            business_name, trade_name, gstin, state_code, state_name,
            address, city, pincode, phone, email,
            bank_name, account_no, ifsc_code, branch, upi_id,
            invoice_prefix, next_invoice_no, created_at
        ) VALUES (
            'Sharma Trading Corporation', 'Sharma Enterprises', '27ABCDE1234F1Z5', '27', 'Maharashtra',
            'Plot No. 42, MIDC Industrial Area, Andheri East', 'Mumbai', '400093', '9876543210', 'client@sharma.in',
            'HDFC Bank', '50200012345678', 'HDFC0000240', 'Andheri East Branch', 'sharma@okhdfcbank',
            'STC/26-27/', 3, ?
        )
    """, (now,))
    client_id = cursor.lastrowid

    # Client Login user (Mobile: 9876543210, Password: client123)
    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role, client_id, is_active, created_at)
        VALUES (?, ?, ?, 'client', ?, 1, ?)
    """, ('9876543210', hash_password('client123'), 'Rajesh Sharma', client_id, now))

    # Sample Parties:
    # 1. Debtor (Customer): Apex Infotech Pvt Ltd (Interstate: Delhi 07)
    cursor.execute("""
        INSERT INTO parties (
            client_id, party_type, name, trade_name, gstin, state_code, state_name,
            address, phone, email, opening_balance, opening_balance_type, created_at
        ) VALUES (
            ?, 'debtor', 'Apex Infotech Pvt Ltd', 'Apex Tech', '07AAACA1234A1Z1', '07', 'Delhi',
            'Sector 62, Connaught Place', '9811122233', 'accounts@apextech.in', 5000.0, 'Dr', ?
        )
    """, (client_id, now))
    debtor1_id = cursor.lastrowid

    # 2. Debtor (Customer): Metro Retailers (Intrastate: Maharashtra 27)
    cursor.execute("""
        INSERT INTO parties (
            client_id, party_type, name, trade_name, gstin, state_code, state_name,
            address, phone, email, opening_balance, opening_balance_type, created_at
        ) VALUES (
            ?, 'debtor', 'Metro Retailers', 'Metro Mart', '27BBBCC2233D1Z8', '27', 'Maharashtra',
            'Shop 15, Link Road, Borivali West, Mumbai', '9822233344', 'contact@metromart.in', 0.0, 'Dr', ?
        )
    """, (client_id, now))
    debtor2_id = cursor.lastrowid

    # 3. Creditor (Supplier): Bharat Electronics Suppliers (Intrastate: Maharashtra 27)
    cursor.execute("""
        INSERT INTO parties (
            client_id, party_type, name, trade_name, gstin, state_code, state_name,
            address, phone, email, opening_balance, opening_balance_type, created_at
        ) VALUES (
            ?, 'creditor', 'Bharat Electronics Suppliers', 'Bharat Electronics', '27XYZAB9876Q1Z2', '27', 'Maharashtra',
            'Lamington Road, Grant Road, Mumbai', '9833344455', 'sales@bharatelec.com', 12000.0, 'Cr', ?
        )
    """, (client_id, now))
    creditor1_id = cursor.lastrowid

    # Sample Sale Invoice 1 (Inter-state to Delhi, IGST 18%)
    cursor.execute("""
        INSERT INTO invoices (
            client_id, invoice_number, invoice_date, party_id, party_name, party_gstin,
            place_of_supply, is_interstate, taxable_amount, cgst_amount, sgst_amount,
            igst_amount, total_tax, round_off, grand_total, paid_amount, status, notes,
            created_by_user_id, created_at, updated_at
        ) VALUES (
            ?, 'STC/26-27/001', ?, ?, 'Apex Infotech Pvt Ltd', '07AAACA1234A1Z1',
            '07 - Delhi', 1, 50000.00, 0.0, 0.0,
            9000.00, 9000.00, 0.00, 59000.00, 20000.00, 'partially_paid', 'Goods dispatched via DTDC Courier',
            1, ?, ?
        )
    """, (client_id, today, debtor1_id, now, now))
    inv1_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO invoice_items (
            invoice_id, item_description, hsn_sac, quantity, unit, unit_price,
            discount_pct, taxable_value, gst_rate, cgst_rate, cgst_amount,
            sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
        ) VALUES (
            ?, 'Industrial Network Routers Pro', '851762', 5, 'NOS', 10000.00,
            0.0, 50000.00, 18.0, 0.0, 0.0, 0.0, 0.0, 18.0, 9000.00, 59000.00
        )
    """, (inv1_id,))

    # Sample Sale Invoice 2 (Intra-state to Maharashtra, CGST 9% + SGST 9%)
    cursor.execute("""
        INSERT INTO invoices (
            client_id, invoice_number, invoice_date, party_id, party_name, party_gstin,
            place_of_supply, is_interstate, taxable_amount, cgst_amount, sgst_amount,
            igst_amount, total_tax, round_off, grand_total, paid_amount, status, notes,
            created_by_user_id, created_at, updated_at
        ) VALUES (
            ?, 'STC/26-27/002', ?, ?, 'Metro Retailers', '27BBBCC2233D1Z8',
            '27 - Maharashtra', 0, 25000.00, 2250.00, 2250.00,
            0.0, 4500.00, 0.00, 29500.00, 0.0, 'unpaid', 'Payment due in 15 days',
            1, ?, ?
        )
    """, (client_id, today, debtor2_id, now, now))
    inv2_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO invoice_items (
            invoice_id, item_description, hsn_sac, quantity, unit, unit_price,
            discount_pct, taxable_value, gst_rate, cgst_rate, cgst_amount,
            sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
        ) VALUES (
            ?, 'Thermal Receipt Printers', '844332', 5, 'PCS', 5000.00,
            0.0, 25000.00, 18.0, 9.0, 2250.00, 9.0, 2250.00, 0.0, 0.0, 29500.00
        )
    """, (inv2_id,))

    # Sample Purchase (From Bharat Electronics Suppliers, CGST 9% + SGST 9%)
    cursor.execute("""
        INSERT INTO purchases (
            client_id, bill_number, bill_date, party_id, party_name, party_gstin,
            is_interstate, taxable_amount, cgst_amount, sgst_amount, igst_amount,
            total_tax, round_off, grand_total, paid_amount, itc_eligible, notes,
            created_by_user_id, created_at, updated_at
        ) VALUES (
            ?, 'BES-2026-904', ?, ?, 'Bharat Electronics Suppliers', '27XYZAB9876Q1Z2',
            0, 30000.00, 2700.00, 2700.00, 0.0,
            5400.00, 0.00, 35400.00, 15000.00, 1, 'Inward stock received in good condition',
            1, ?, ?
        )
    """, (client_id, today, creditor1_id, now, now))
    purch1_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO purchase_items (
            purchase_id, item_description, hsn_sac, quantity, unit, unit_price,
            taxable_value, gst_rate, cgst_rate, cgst_amount,
            sgst_rate, sgst_amount, igst_rate, igst_amount, total_amount
        ) VALUES (
            ?, 'Electronic Components & Board Modules', '854231', 30, 'NOS', 1000.00,
            30000.00, 18.0, 9.0, 2700.00, 9.0, 2700.00, 0.0, 0.0, 35400.00
        )
    """, (purch1_id,))

    # Sample Payment Received (From Apex Infotech: Rs. 20,000)
    cursor.execute("""
        INSERT INTO payments (
            client_id, payment_type, payment_date, party_id, party_name,
            amount, payment_mode, reference_no, invoice_id, remarks,
            created_by_user_id, created_at, updated_at
        ) VALUES (
            ?, 'received', ?, ?, 'Apex Infotech Pvt Ltd',
            20000.00, 'Bank', 'HDFCN2612345678', ?, 'Part payment against STC/26-27/001',
            1, ?, ?
        )
    """, (client_id, today, debtor1_id, inv1_id, now, now))

    # Sample Payment Made (To Bharat Electronics: Rs. 15,000)
    cursor.execute("""
        INSERT INTO payments (
            client_id, payment_type, payment_date, party_id, party_name,
            amount, payment_mode, reference_no, purchase_id, remarks,
            created_by_user_id, created_at, updated_at
        ) VALUES (
            ?, 'made', ?, ?, 'Bharat Electronics Suppliers',
            15000.00, 'UPI', 'UPI/261025/998877', ?, 'Advance against bill BES-2026-904',
            1, ?, ?
        )
    """, (client_id, today, creditor1_id, purch1_id, now, now))

    conn.commit()
