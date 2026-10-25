import tempfile
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.reports import get_gstr1_report, get_gstr3b_report, export_gstr1_excel
from app.routers.client_router import get_context

router = APIRouter(prefix="/reports")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/gst", response_class=HTMLResponse)
async def gst_reports_page(request: Request, start_date: str = None, end_date: str = None):
    user, active_client, all_clients = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]

    today = datetime.now()
    if not start_date:
        start_date = today.strftime("%Y-%m-01")
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")

    gstr1 = get_gstr1_report(client_id, start_date, end_date)
    gstr3b = get_gstr3b_report(client_id, start_date, end_date)

    return templates.TemplateResponse(request=request, name="admin/gst_reports.html", context={
        "user": user,
        "active_client": active_client,
        "all_clients": all_clients,
        "start_date": start_date,
        "end_date": end_date,
        "gstr1": gstr1,
        "gstr3b": gstr3b
    })

@router.get("/gst/export-excel")
async def export_gstr1_excel_endpoint(request: Request, start_date: str = None, end_date: str = None):
    user, active_client, _ = get_context(request)
    if not user or not active_client:
        return RedirectResponse("/login", status_code=302)

    client_id = active_client["id"]
    gstr1 = get_gstr1_report(client_id, start_date, end_date)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    export_gstr1_excel(active_client, gstr1, tmp.name)

    safe_name = active_client.get("business_name", "Client").replace(" ", "_")
    filename = f"GSTR1_{safe_name}_{start_date}_to_{end_date}.xlsx"

    return FileResponse(
        tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )
