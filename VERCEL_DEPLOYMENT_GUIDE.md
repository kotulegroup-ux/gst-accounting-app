# Deploying GST Accounting App to Vercel

This repository is fully configured for deployment on **Vercel** with:
* `vercel.json` – Configured with `@vercel/python` builder and routing.
* `api/index.py` – Serverless ASGI entrypoint for FastAPI.
* `requirements.txt` – Automated dependency installation.
* `app/database.py` – Adapted for Vercel's serverless environment (handles `/tmp` storage and auto-seeds initial data).

---

## 🚀 Step-by-Step Deployment (via GitHub & Vercel Dashboard)

The standard and most reliable method to deploy on Vercel is connecting your GitHub repository:

### Step 1: Push Code to GitHub
1. Create a new repository on [GitHub](https://github.com/new) (e.g., `gst-accounting-app`).
2. In your terminal or GitHub Desktop, publish the project files from:
   `C:\Users\ICAI-PC\.gemini\antigravity\scratch\gst-accounting-app`
3. Push to your GitHub repository.

### Step 2: Import Project in Vercel
1. Log in to [Vercel](https://vercel.com) (sign up with GitHub).
2. Click **"Add New..."** &rarr; **"Project"**.
3. Under **Import Git Repository**, select your `gst-accounting-app` repository and click **Import**.
4. In the configuration screen:
   * **Framework Preset:** Leave as *Other*.
   * **Root Directory:** Leave as `./`.
   * **Environment Variables:**
     * `SECRET_KEY`: Set any secure random string (e.g., `gst_prod_secret_key_2026_xyz`).
5. Click **Deploy**.

Vercel will build the project and assign a live production URL:
👉 `https://your-app-name.vercel.app`

---

## ⚠️ Important Production Database Note for Accounting Apps

* **Serverless Nature of Vercel:** Vercel functions are stateless. With the current configuration, SQLite runs inside `/tmp/gst_app.db` with sample data.
* **For Permanent Data Storage:**
  Because accounting data (sales invoices, debtor receipts, tax filings) must never be lost:
  1. **Option A (Turso / LibSQL):** Turso is a free cloud SQLite database designed for serverless platforms like Vercel.
  2. **Option B (Persistent Containers):** Platforms like **Render.com** or **Railway.app** provide persistent disk volumes, allowing your SQLite database file to persist forever with zero code changes.
