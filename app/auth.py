"""
Authentication, Session Management, and Authorization Helpers.
"""
from datetime import datetime
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from app.database import get_db, hash_password

def get_current_user(request: Request):
    """Retrieve logged-in user details from session."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, client_id, is_active FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not user["is_active"]:
        return None
    
    return dict(user)

def get_active_client_id(request: Request, current_user: dict):
    """
    Returns the active client_id for the current session.
    If the user is a client, returns user['client_id'].
    If the user is admin, returns the client_id selected in admin_active_client_id, or None if in admin global view.
    """
    if not current_user:
        return None
    if current_user["role"] == "client":
        return current_user["client_id"]
    if current_user["role"] == "admin":
        return request.session.get("admin_active_client_id")
    return None

def log_audit(client_id, user_id, user_name, action, entity_type, entity_id, details):
    """Record administrative or user action for auditing."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO audit_logs (client_id, user_id, user_name, action, entity_type, entity_id, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, user_id, user_name, action, entity_type, entity_id, details, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging audit: {e}")
