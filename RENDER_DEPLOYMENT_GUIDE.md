# Deploy GST Accounting App to Render (2-Minute Guide)

Render is the easiest, most reliable cloud platform to host this application. It runs Python natively, supports your SQLite database with zero code changes, and provides a free, live HTTPS domain (`https://your-app.onrender.com`).

---

## 🚀 3 Quick Steps to Deploy

### Step 1: Push Code to GitHub
1. Create a repository on [GitHub](https://github.com/new) (e.g. `gst-accounting-app`).
2. Upload the files from:
   `C:\Users\ICAI-PC\.gemini\antigravity\scratch\gst-accounting-app`
   *(or upload the pre-packaged zip: `gst-accounting-app-vercel.zip`)*.

---

### Step 2: Create Web Service on Render
1. Go to **[https://dashboard.render.com](https://dashboard.render.com)** and sign in (Free).
2. Click the blue **"New +"** button at the top right and select **"Web Service"**.
3. Choose **"Build and deploy from a Git repository"** and select your `gst-accounting-app` repo.

---

### Step 3: Configure & Launch
Render will auto-detect your project settings:
* **Name:** `gst-accounting-app` (or any name you prefer)
* **Region:** Singapore / Frankfurt / Oregon (select closest to you)
* **Runtime:** `Python 3`
* **Build Command:** `pip install -r requirements.txt`
* **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
* **Instance Type:** `Free`

Click **"Create Web Service"**.

---

## 🎉 Done!
Within 90 seconds, Render will build your application and display your live URL:
👉 **`https://gst-accounting-app.onrender.com`**

You and your clients can now log in from any phone or computer worldwide with:
* **Admin Login:** `admin` / `admin123`
* **Client Login:** `9876543210` / `client123`
