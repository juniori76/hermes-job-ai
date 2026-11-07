"""
Backend Web HTTP do Hermes Job AI.
Interface FastAPI leve para monitoramento e controle de candidaturas.
"""

import os
import shutil
import yaml
from typing import Optional
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.database import get_connection
from core.radar import scan_jobs, load_profile, CONFIG_PATH
from core.ats_brain import run_ats_evaluation_batch

app = FastAPI(title="Hermes Job AI Dashboard")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Página principal do Dashboard exibindo métricas e vagas ranqueadas."""
    profile = load_profile()
    resume_exists = os.path.exists(os.path.join(DATA_DIR, "curriculo.pdf"))
    gemini_key_set = bool(os.getenv("GEMINI_API_KEY"))

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Métricas gerais
        cursor.execute("SELECT COUNT(*) FROM jobs;")
        total_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE match_score >= 75;")
        high_match_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'success';")
        applied_jobs = cursor.fetchone()[0]
        
        # Top 50 melhores vagas ranqueadas
        cursor.execute("""
            SELECT id, site, title, company, location, is_remote, job_url, 
                   match_score, match_reasons, keywords_found, status, created_at
            FROM jobs
            ORDER BY 
                CASE WHEN match_score IS NULL THEN 0 ELSE match_score END DESC,
                created_at DESC
            LIMIT 50;
        """)
        jobs = [dict(row) for row in cursor.fetchall()]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "total_jobs": total_jobs,
            "high_match_jobs": high_match_jobs,
            "applied_jobs": applied_jobs,
            "jobs": jobs,
            "profile": profile,
            "resume_exists": resume_exists,
            "gemini_key_set": gemini_key_set
        }
    )


@app.post("/api/settings/api-key")
async def save_api_key(request: Request):
    """Salva a chave do Gemini no arquivo .env e na memória."""
    data = await request.json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "Chave vazia"}, status_code=400)

    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    lines.append(f"GEMINI_API_KEY={api_key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"GEMINI_API_KEY={api_key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    os.environ["GEMINI_API_KEY"] = api_key
    return {"success": True, "message": "Chave Gemini salva com sucesso!"}


@app.post("/api/settings/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Faz upload do currículo em PDF pelo painel."""
    os.makedirs(DATA_DIR, exist_ok=True)
    target_path = os.path.join(DATA_DIR, "curriculo.pdf")
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"success": True, "filename": file.filename}


@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Dispara uma varredura de novas vagas em segundo plano."""
    background_tasks.add_task(scan_jobs)
    return {"message": "Varredura iniciada em segundo plano!"}


@app.post("/api/evaluate")
async def trigger_evaluation(background_tasks: BackgroundTasks):
    """Dispara a avaliação de compatibilidade ATS com Gemini Flash em segundo plano."""
    background_tasks.add_task(run_ats_evaluation_batch)
    return {"message": "Avaliação de ATS iniciada com Gemini Flash!"}


@app.post("/api/jobs/{job_id}/status")
async def update_status(job_id: str, request: Request):
    """Altera o status de uma vaga (ex: 'approved', 'rejected')."""
    data = await request.json()
    new_status = data.get("status")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
        conn.commit()
        
    return {"success": True, "job_id": job_id, "new_status": new_status}


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Página principal do Dashboard exibindo métricas e vagas ranqueadas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Métricas gerais
        cursor.execute("SELECT COUNT(*) FROM jobs;")
        total_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE match_score >= 75;")
        high_match_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'success';")
        applied_jobs = cursor.fetchone()[0]
        
        # Top 50 melhores vagas ranqueadas
        cursor.execute("""
            SELECT id, site, title, company, location, is_remote, job_url, 
                   match_score, match_reasons, keywords_found, status, created_at
            FROM jobs
            ORDER BY 
                CASE WHEN match_score IS NULL THEN 0 ELSE match_score END DESC,
                created_at DESC
            LIMIT 50;
        """)
        jobs = [dict(row) for row in cursor.fetchall()]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total_jobs": total_jobs,
            "high_match_jobs": high_match_jobs,
            "applied_jobs": applied_jobs,
            "jobs": jobs
        }
    )


@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Dispara uma varredura de novas vagas em segundo plano."""
    background_tasks.add_task(scan_jobs)
    return {"message": "Varredura iniciada em segundo plano!"}


@app.post("/api/evaluate")
async def trigger_evaluation(background_tasks: BackgroundTasks):
    """Dispara a avaliação de compatibilidade ATS com Gemini Flash em segundo plano."""
    background_tasks.add_task(run_ats_evaluation_batch)
    return {"message": "Avaliação de ATS iniciada com Gemini Flash!"}


@app.post("/api/jobs/{job_id}/status")
async def update_status(job_id: str, request: Request):
    """Altera o status de uma vaga (ex: 'approved', 'rejected')."""
    data = await request.json()
    new_status = data.get("status")
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
        conn.commit()
        
    return {"success": True, "job_id": job_id, "new_status": new_status}
