from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.database import get_db, hash_password
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    pwd_hash = hash_password(password)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, full_name, role, client_id, is_active 
        FROM users 
        WHERE (username = ? OR username = (SELECT phone FROM clients WHERE phone = ?))
          AND password_hash = ?
    """, (username, username, pwd_hash))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return templates.TemplateResponse(request=request, name="login.html", context={
            "error": "Invalid User ID or Password. Please check and try again."
        })

    user_dict = dict(user)
    if not user_dict.get("is_active"):
        conn.close()
        return templates.TemplateResponse(request=request, name="login.html", context={
            "error": "This account is inactive. Please contact the administrator."
        })

    # Set session data
    request.session["user_id"] = user_dict["id"]
    request.session["username"] = user_dict["username"]
    request.session["role"] = user_dict["role"]
    request.session["client_id"] = user_dict["client_id"]

    if user_dict["role"] == "admin":
        cursor.execute("SELECT id FROM clients ORDER BY id ASC LIMIT 1")
        first_client = cursor.fetchone()
        if first_client:
            request.session["admin_active_client_id"] = first_client["id"]

    conn.close()
    return RedirectResponse("/", status_code=302)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
