"""
Main FastAPI Application Entrypoint.
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from app.config import SECRET_KEY, APP_TITLE
from app.database import init_db
from app.routers import (
    auth_router,
    client_router,
    sales_router,
    purchase_router,
    payment_router,
    party_router,
    report_router,
    admin_router
)

app = FastAPI(title=APP_TITLE, version="1.0.0")

# Session Middleware for cookie sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=86400 * 30, # 30 days session
    same_site="lax"
)

# Static Files Mount
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers
app.include_router(auth_router.router)
app.include_router(client_router.router)
app.include_router(sales_router.router)
app.include_router(purchase_router.router)
app.include_router(payment_router.router)
app.include_router(party_router.router)
app.include_router(report_router.router)
app.include_router(admin_router.router)

@app.on_event("startup")
def on_startup():
    init_db()

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return RedirectResponse("/", status_code=302)
