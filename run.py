"""
Runner script for the GST Accounting & Tax Invoicing Web Application.
Usage: py run.py
"""
import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure current directory is on sys.path
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if curr_dir not in sys.path:
        sys.path.insert(0, curr_dir)

    print("=" * 60)
    print(" GST Accounting, Invoicing & Tax Compliance Web App ")
    print("=" * 60)
    print("Starting server at: http://127.0.0.1:8000")
    print("Accessible from mobile/devices on local network at your PC IP.")
    print("Default Admin Login:   Username: admin       Password: admin123")
    print("Default Client Login:  Username: 9876543210  Password: client123")
    print("=" * 60)

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
