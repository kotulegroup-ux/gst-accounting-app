# GST Accounting, Invoicing & Compliance Portal

A full-featured multi-tenant accounting and tax compliance application designed for an **Administrator (Accountant / CA / Tax Practitioner)** and their **Business Clients**.

---

## 🌟 Key Features

### 1. Multi-Tenant Architecture & Roles
* **Administrator (Master CA / Accountant):**
  * View all registered client businesses.
  * Switch into any client's books with one click.
  * Modify, correct, or delete any sale invoice, purchase bill, or payment entry.
  * Register new clients and set their user ID (Mobile number/Email) and password.
  * Complete audit trail log of all changes.
  * Generate GSTR-1 (Table 4 B2B, Table 7 B2C, Table 12 HSN) & GSTR-3B monthly computation across any client with Excel (.xlsx) export.
* **Client (Business Owner):**
  * Secure sign-in using their registered Mobile Number or Email + Password.
  * Records daily sales invoices, purchase bills, debtor receipts, and creditor payments.
  * Isolated data access: clients only see their own business data.

### 2. GST-Compliant Tax Invoicing (Rule 46 CGST Rules)
* Auto-computes **Intra-State (CGST + SGST)** vs **Inter-State (IGST)** based on Client State vs Buyer Place of Supply (POS).
* Item-wise HSN/SAC code, quantity, unit (PCS, NOS, KG, MTR, etc.), rate, discount %, and GST rates (0%, 5%, 12%, 18%, 28%).
* Professional **A4 Print Layout** (`window.print()`):
  * Supplier & Buyer GSTIN, State code, and Address.
  * Tax breakdown table (Taxable, CGST, SGST, IGST).
  * Total amount converted to **Indian Rupees in Words**.
  * Bank remittance details (Account No, IFSC, Branch, UPI).
  * Authorized Signatory declaration.

### 3. Purchases & Input Tax Credit (ITC)
* Record supplier bills with vendor GSTIN and bill number.
* Track eligible vs ineligible ITC (Section 17(5)).
* Automatic calculation of ITC available for GSTR-3B.

### 4. Payments In & Out
* **Payment Received (from Debtors):** Bank Transfer, UPI, Cash, Cheque.
* **Payment Made (to Creditors):** Bank, UPI, Cash, Cheque.
* Automatically credits or debits the respective party ledger.

### 5. Party Ledgers & Running Balance Statements
* Full statement of account for any customer or supplier.
* Chronological listing: Date, Voucher Type, Voucher No, Narration, Debit, Credit, Running Balance (Dr/Cr).
* Print-ready ledger statement to send directly to parties for reconciliation.

### 6. GST Returns Preparation Center
* **GSTR-1:**
  * Table 4: B2B Invoices (Registered buyers with 15-digit GSTIN).
  * Table 7: B2C Invoices (Unregistered consumers).
  * Table 12: HSN Summary (HSN, UQC, Total Quantity, Taxable, Tax).
  * **Export to Multi-sheet Excel (.xlsx)** for filing on the GST portal.
* **GSTR-3B Computation:**
  * Outward taxable supply tax liability.
  * Inward supply Input Tax Credit (ITC).
  * Net Cash GST Tax Payable (Liability minus ITC) and excess ITC carry forward.

---

## 🚀 Quick Start Guide

### Step 1: Open PowerShell or Terminal
Navigate to the application folder:
```powershell
cd C:\Users\ICAI-PC\.gemini\antigravity\scratch\gst-accounting-app
```

### Step 2: Run the App
Launch the server using Python:
```powershell
py run.py
```

### Step 3: Open in Browser
Open your browser and visit:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔑 Default Login Credentials

| Role | User ID (Username) | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | CA / Accountant with master access to all clients |
| **Demo Client** | `9876543210` | `client123` | Sample business: Sharma Trading Corporation |

---

## 📱 Mobile & Office Network Access
Because the server listens on `0.0.0.0:8000`, any smartphone, tablet, or PC connected to your office Wi-Fi can access the app!
Simply find your PC's local IP address (run `ipconfig` in cmd):
Example: `http://192.168.1.15:8000`
Your clients can open that link in their mobile browser to enter invoices and check ledgers on the go.
