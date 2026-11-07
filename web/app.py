"""
Backend Web HTTP do Hermes Job AI.
Interface FastAPI leve para monitoramento e controle de candidaturas.
"""

import os
import shutil
import yaml
from typing import Optional
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File, Form, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.database import get_connection
from core import config
from core.radar import scan_jobs, load_profile, CONFIG_PATH
from core.ats_brain import run_ats_evaluation_batch
from core.resume_analyzer import analyze_resume_with_ai
from core.profile_sync import sync_profile_from_resume_ai
from core.recency_engine import calculate_job_age_hours, format_job_badge
from core.auth import (
    authenticate_user, create_session, validate_session,
    revoke_session, change_user_password, init_auth
)
from core.settings_manager import (
    load_settings, save_settings, set_operation_mode, update_telegram_config
)
from core.notifier import test_telegram_connection
from automation.apply_engine import apply_to_job
from automation.browser_session import check_auth_status, launch_assisted_login

app = FastAPI(title="Hermes Job AI Dashboard")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))

# Inicializa credenciais
init_auth()


def get_current_user(request: Request) -> Optional[str]:
    """Extrai e valida o token de sessão do cookie."""
    token = request.cookies.get("hermes_session")
    return validate_session(token)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Exibe a tela de login."""
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    """Processa a tentativa de login."""
    if authenticate_user(username, password):
        token = create_session(username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="hermes_session",
            value=token,
            httponly=True,
            max_age=14 * 86400, # 14 dias de validade
            samesite="lax"
        )
        return response
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Usuário ou senha incorretos."}
    )


@app.get("/logout")
async def logout(request: Request):
    """Encerra a sessão do usuário."""
    token = request.cookies.get("hermes_session")
    revoke_session(token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("hermes_session")
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Página principal do Dashboard (Protegida por Login)."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    profile = load_profile()
    resume_exists = os.path.exists(os.path.join(DATA_DIR, "curriculo.pdf"))
    gemini_key_set = config.has_api_key()

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
                   match_score, match_reasons, keywords_found, status, date_posted, created_at
            FROM jobs
            ORDER BY 
                CASE WHEN match_score IS NULL THEN 0 ELSE match_score END DESC,
                created_at DESC
            LIMIT 500;
        """)
        raw_jobs = [dict(row) for row in cursor.fetchall()]

        # Processa tags de antiguidade da vaga
        jobs = []
        for j in raw_jobs:
            age = calculate_job_age_hours(j.get("date_posted") or j.get("created_at", ""))
            badge_text, badge_css, badge_icon = format_job_badge(age)
            j["age_hours"] = age
            j["badge_text"] = badge_text
            j["badge_css"] = badge_css
            j["badge_icon"] = badge_icon
            jobs.append(j)

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


@app.post("/api/auth/change-password")
async def api_change_password(request: Request):
    """Altera a senha do usuário logado."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    new_pass = data.get("new_password", "").strip()
    if len(new_pass) < 6:
        return JSONResponse({"error": "Senha muito curta"}, status_code=400)
    
    if change_user_password(user, new_pass):
        return {"success": True, "message": "Senha alterada!"}
    return JSONResponse({"error": "Erro ao atualizar"}, status_code=500)


@app.post("/api/settings/api-key")
async def save_api_key(request: Request):
    """Salva a chave do Gemini em data/runtime.env (volume persistente)."""
    data = await request.json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return JSONResponse({"error": "Chave vazia"}, status_code=400)

    config.set_value("GEMINI_API_KEY", api_key)
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
async def trigger_scan(background_tasks: BackgroundTasks, request: Request = None):
    """Dispara uma varredura de novas vagas em segundo plano."""
    background_tasks.add_task(scan_jobs)
    return {"message": "Varredura iniciada em segundo plano no LinkedIn, Gupy, Indeed e Glassdoor!"}


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...), request: Request = None):
    """Recebe upload de novo curriculo.pdf, salva em data/curriculo.pdf e sincroniza perfil e analise ATS."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Apenas arquivos PDF (.pdf) são aceitos."}, status_code=400)
        
    resume_path = os.path.join(BASE_DIR, "data", "curriculo.pdf")
    os.makedirs(os.path.dirname(resume_path), exist_ok=True)
    
    content = await file.read()
    with open(resume_path, "wb") as f:
        f.write(content)
        
    # Reanalisa com IA e sincroniza perfil
    analysis = analyze_resume_with_ai()
    sync = sync_profile_from_resume_ai()
    
    return {
        "success": True,
        "message": f"Currículo '{file.filename}' recebido e analisado pela IA com sucesso!",
        "analysis": analysis,
        "sync": sync
    }


@app.get("/api/resume/analysis")
async def get_resume_analysis(request: Request):
    """Retorna o diagnóstico de IA do currículo atual."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    analysis = analyze_resume_with_ai()
    return analysis


@app.post("/api/profile/sync")
async def trigger_profile_sync(request: Request):
    """Dispara a extração profunda de dados do PDF para o candidate_profile.yaml."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    result = sync_profile_from_resume_ai()
    return result


@app.post("/api/settings/profile")
async def update_profile_settings(request: Request):
    """Salva todas as regras de modalidade, km, salário e cargos atualizadas pelo painel."""
    data = await request.json()
    profile_path = os.path.join(CONFIG_PATH, "candidate_profile.yaml")
    
    current = load_profile()
    candidato = current.setdefault("candidato", {})
    prefs = current.setdefault("preferencias_de_vaga", {})
    modalidades = prefs.setdefault("modalidades", {})
    financeiro = prefs.setdefault("financeiro", {})

    # Atualiza dados pessoais e residência
    if "cidade" in data: candidato["cidade"] = data["cidade"].strip()
    if "estado" in data: candidato["estado"] = data["estado"].strip()
    if "bairro" in data: candidato["bairro"] = data["bairro"].strip()
    if "endereco_residencia" in data: candidato["endereco_residencia"] = data["endereco_residencia"].strip()

    # Atualiza cargos alvo
    if "cargos" in data:
        cargos = [c.strip() for c in data["cargos"].split(",") if c.strip()]
        prefs["cargos_alvo"] = cargos

    # Atualiza regras de Km e Modalidades
    if "remoto_aceitar" in data:
        modalidades.setdefault("remoto", {})["aceitar"] = bool(data["remoto_aceitar"])
    if "hibrido_aceitar" in data:
        modalidades.setdefault("hibrido", {})["aceitar"] = bool(data["hibrido_aceitar"])
    if "hibrido_km" in data:
        modalidades.setdefault("hibrido", {})["distancia_maxima_km"] = float(data["hibrido_km"])
    if "hibrido_dias" in data:
        modalidades.setdefault("hibrido", {})["dias_presenciais_maximo"] = int(data["hibrido_dias"])
    if "presencial_aceitar" in data:
        modalidades.setdefault("presencial", {})["aceitar"] = bool(data["presencial_aceitar"])
    if "presencial_km" in data:
        modalidades.setdefault("presencial", {})["distancia_maxima_km"] = float(data["presencial_km"])

    # Atualiza regras financeiras
    if "salario_min_clt" in data:
        financeiro["salario_minimo_clt"] = float(data["salario_min_clt"])
    if "pretensao_clt" in data:
        financeiro["pretensao_clt"] = float(data["pretensao_clt"])
    if "salario_min_pj" in data:
        financeiro["salario_minimo_pj"] = float(data["salario_min_pj"])
    if "pretensao_pj" in data:
        financeiro["pretensao_pj"] = float(data["pretensao_pj"])

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(current, f, allow_unicode=True)

    return {"success": True, "message": "Políticas de vaga, km e salários salvas com sucesso!"}


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


# =========================================================
# FASE 4 — Modos de Operação, Telegram, Aprovação Rápida
# =========================================================

@app.get("/api/settings")
async def get_settings(request: Request):
    """Retorna as configurações atuais (modo de operação, Telegram)."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    s = load_settings()
    # Mascara o token do bot para segurança — retorna só se está configurado
    return {
        "operation_mode": s.get("operation_mode", "review"),
        "telegram_enabled": s.get("telegram_enabled", False),
        "telegram_chat_id": s.get("telegram_chat_id", ""),
        "telegram_token_set": bool(s.get("telegram_bot_token")),
        "smart_score_threshold": s.get("smart_score_threshold", 80),
        "auto_score_threshold": s.get("auto_score_threshold", 85),
        "auto_apply_daily_limit": s.get("auto_apply_daily_limit", 10),
    }


@app.post("/api/settings/mode")
async def set_mode(request: Request):
    """Altera o modo de operação: review | smart | auto."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    mode = data.get("mode", "review")
    try:
        set_operation_mode(mode)
        return {"success": True, "operation_mode": mode}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/settings/telegram")
async def save_telegram(request: Request):
    """Salva ou atualiza as credenciais do Telegram."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    token = data.get("token", "").strip()
    chat_id = data.get("chat_id", "").strip()
    update_telegram_config(token, chat_id)
    return {"success": True, "telegram_enabled": bool(token and chat_id)}


@app.post("/api/settings/telegram/test")
async def test_telegram(request: Request):
    """Envia uma mensagem de teste para verificar as credenciais do Telegram."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    token = data.get("token", "").strip()
    chat_id = data.get("chat_id", "").strip()
    if not token or not chat_id:
        return JSONResponse({"error": "Token e Chat ID são obrigatórios para o teste."}, status_code=400)
    result = test_telegram_connection(token, chat_id)
    return result


@app.post("/api/settings/thresholds")
async def save_thresholds(request: Request):
    """Salva os thresholds de score para alertas e candidatura automática."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    s = load_settings()
    if "smart_score_threshold" in data:
        s["smart_score_threshold"] = int(data["smart_score_threshold"])
    if "auto_score_threshold" in data:
        s["auto_score_threshold"] = int(data["auto_score_threshold"])
    if "auto_apply_daily_limit" in data:
        s["auto_apply_daily_limit"] = int(data["auto_apply_daily_limit"])
    save_settings(s)
    return {"success": True}


@app.get("/api/jobs/{job_id}/approve_redirect")
async def approve_redirect(job_id: str):
    """Aprovação rápida via link do Telegram — redireciona para o painel após aprovar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job_id,))
        conn.commit()
    # Redireciona para o painel principal
    return RedirectResponse(url="/?tab=vagas&highlight=" + job_id, status_code=302)


@app.get("/api/jobs/{job_id}/reject_redirect")
async def reject_redirect(job_id: str):
    """Rejeição rápida via link do Telegram — redireciona para o painel após rejeitar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = 'rejected' WHERE id = ?", (job_id,))
        conn.commit()
    return RedirectResponse(url="/?tab=vagas", status_code=302)

# =========================================================
# FASE 5 — Candidatura Automática Real com Playwright
# =========================================================

def _run_apply_task(job_id: str, dry_run: bool = False):
    """Executa a candidatura em background para não travar a requisição HTTP."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if row:
            apply_to_job(dict(row), dry_run=dry_run)


@app.post("/api/jobs/{job_id}/apply")
async def trigger_apply(job_id: str, background_tasks: BackgroundTasks, request: Request):
    """Dispara a candidatura real com Playwright em segundo plano."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    background_tasks.add_task(_run_apply_task, job_id, dry_run=False)
    return {"success": True, "message": "Candidatura iniciada via Playwright em segundo plano! Acompanhe pelos logs ou Telegram."}


@app.post("/api/jobs/{job_id}/dry-run")
async def trigger_dry_run(job_id: str, background_tasks: BackgroundTasks, request: Request):
    """Simula o preenchimento completo do formulário com print sem enviar."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    background_tasks.add_task(_run_apply_task, job_id, dry_run=True)
    return {"success": True, "message": "Simulação (Dry-Run) iniciada! O formulário será preenchido e um print será gerado sem enviar."}


@app.get("/api/applications/history")
async def get_applications_history(request: Request):
    """Retorna o histórico de auditoria de candidaturas enviadas."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, j.title, j.company, j.job_url 
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
            ORDER BY a.applied_at DESC
            LIMIT 50
        """)
        history = [dict(row) for row in cursor.fetchall()]
    return history


@app.get("/api/auth/browser-status")
def get_browser_auth_status(request: Request):
    """Verifica se há sessão autenticada do LinkedIn e Gupy no perfil persistente."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    status = check_auth_status()
    return status


@app.post("/api/auth/assisted-login")
async def trigger_assisted_login(background_tasks: BackgroundTasks, request: Request, platform: str = "linkedin"):
    """Dispara a abertura do navegador no display virtual para login assistido via noVNC."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    background_tasks.add_task(launch_assisted_login, platform)
    return {"success": True, "message": f"Navegador aberto para {platform}. Acesse o noVNC para efetuar o login."}



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
                   match_score, match_reasons, keywords_found, status, date_posted, created_at
            FROM jobs
            ORDER BY 
                CASE WHEN match_score IS NULL THEN 0 ELSE match_score END DESC,
                created_at DESC
            LIMIT 500;
        """)
        raw_jobs = [dict(row) for row in cursor.fetchall()]

        # Processa tags de antiguidade da vaga
        jobs = []
        for j in raw_jobs:
            age = calculate_job_age_hours(j.get("date_posted") or j.get("created_at", ""))
            badge_text, badge_css, badge_icon = format_job_badge(age)
            j["age_hours"] = age
            j["badge_text"] = badge_text
            j["badge_css"] = badge_css
            j["badge_icon"] = badge_icon
            jobs.append(j)

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
async def trigger_scan(background_tasks: BackgroundTasks, request: Request = None):
    """Dispara uma varredura de novas vagas em segundo plano."""
    background_tasks.add_task(scan_jobs)
    return {"message": "Varredura iniciada em segundo plano no LinkedIn, Gupy, Indeed e Glassdoor!"}


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...), request: Request = None):
    """Recebe upload de novo curriculo.pdf, salva em data/curriculo.pdf e sincroniza perfil e analise ATS."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Apenas arquivos PDF (.pdf) são aceitos."}, status_code=400)
        
    resume_path = os.path.join(BASE_DIR, "data", "curriculo.pdf")
    os.makedirs(os.path.dirname(resume_path), exist_ok=True)
    
    content = await file.read()
    with open(resume_path, "wb") as f:
        f.write(content)
        
    # Reanalisa com IA e sincroniza perfil
    analysis = analyze_resume_with_ai()
    sync = sync_profile_from_resume_ai()
    
    return {
        "success": True,
        "message": f"Currículo '{file.filename}' recebido e analisado pela IA com sucesso!",
        "analysis": analysis,
        "sync": sync
    }


@app.get("/api/resume/analysis")
async def get_resume_analysis(request: Request):
    """Retorna o diagnóstico de IA do currículo atual."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    analysis = analyze_resume_with_ai()
    return analysis


@app.post("/api/profile/sync")
async def trigger_profile_sync(request: Request):
    """Dispara a extração profunda de dados do PDF para o candidate_profile.yaml."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    result = sync_profile_from_resume_ai()
    return result


@app.post("/api/settings/profile")
async def update_profile_settings(request: Request):
    """Salva todas as regras de modalidade, km, salário e cargos atualizadas pelo painel."""
    data = await request.json()
    profile_path = os.path.join(CONFIG_PATH, "candidate_profile.yaml")
    
    current = load_profile()
    candidato = current.setdefault("candidato", {})
    prefs = current.setdefault("preferencias_de_vaga", {})
    modalidades = prefs.setdefault("modalidades", {})
    financeiro = prefs.setdefault("financeiro", {})

    # Atualiza dados pessoais e residência
    if "cidade" in data: candidato["cidade"] = data["cidade"].strip()
    if "estado" in data: candidato["estado"] = data["estado"].strip()
    if "bairro" in data: candidato["bairro"] = data["bairro"].strip()
    if "endereco_residencia" in data: candidato["endereco_residencia"] = data["endereco_residencia"].strip()

    # Atualiza cargos alvo
    if "cargos" in data:
        cargos = [c.strip() for c in data["cargos"].split(",") if c.strip()]
        prefs["cargos_alvo"] = cargos

    # Atualiza regras de Km e Modalidades
    if "remoto_aceitar" in data:
        modalidades.setdefault("remoto", {})["aceitar"] = bool(data["remoto_aceitar"])
    if "hibrido_aceitar" in data:
        modalidades.setdefault("hibrido", {})["aceitar"] = bool(data["hibrido_aceitar"])
    if "hibrido_km" in data:
        modalidades.setdefault("hibrido", {})["distancia_maxima_km"] = float(data["hibrido_km"])
    if "hibrido_dias" in data:
        modalidades.setdefault("hibrido", {})["dias_presenciais_maximo"] = int(data["hibrido_dias"])
    if "presencial_aceitar" in data:
        modalidades.setdefault("presencial", {})["aceitar"] = bool(data["presencial_aceitar"])
    if "presencial_km" in data:
        modalidades.setdefault("presencial", {})["distancia_maxima_km"] = float(data["presencial_km"])

    # Atualiza regras financeiras
    if "salario_min_clt" in data:
        financeiro["salario_minimo_clt"] = float(data["salario_min_clt"])
    if "pretensao_clt" in data:
        financeiro["pretensao_clt"] = float(data["pretensao_clt"])
    if "salario_min_pj" in data:
        financeiro["salario_minimo_pj"] = float(data["salario_min_pj"])
    if "pretensao_pj" in data:
        financeiro["pretensao_pj"] = float(data["pretensao_pj"])

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(current, f, allow_unicode=True)

    return {"success": True, "message": "Políticas de vaga, km e salários salvas com sucesso!"}


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


# =========================================================
# FASE 4 — Modos de Operação, Telegram, Aprovação Rápida
# =========================================================

@app.get("/api/settings")
async def get_settings(request: Request):
    """Retorna as configurações atuais (modo de operação, Telegram)."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    s = load_settings()
    # Mascara o token do bot para segurança — retorna só se está configurado
    return {
        "operation_mode": s.get("operation_mode", "review"),
        "telegram_enabled": s.get("telegram_enabled", False),
        "telegram_chat_id": s.get("telegram_chat_id", ""),
        "telegram_token_set": bool(s.get("telegram_bot_token")),
        "smart_score_threshold": s.get("smart_score_threshold", 80),
        "auto_score_threshold": s.get("auto_score_threshold", 85),
        "auto_apply_daily_limit": s.get("auto_apply_daily_limit", 10),
    }


@app.post("/api/settings/mode")
async def set_mode(request: Request):
    """Altera o modo de operação: review | smart | auto."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    mode = data.get("mode", "review")
    try:
        set_operation_mode(mode)
        return {"success": True, "operation_mode": mode}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/settings/telegram")
async def save_telegram(request: Request):
    """Salva ou atualiza as credenciais do Telegram."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    token = data.get("token", "").strip()
    chat_id = data.get("chat_id", "").strip()
    update_telegram_config(token, chat_id)
    return {"success": True, "telegram_enabled": bool(token and chat_id)}


@app.post("/api/settings/telegram/test")
async def test_telegram(request: Request):
    """Envia uma mensagem de teste para verificar as credenciais do Telegram."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    token = data.get("token", "").strip()
    chat_id = data.get("chat_id", "").strip()
    if not token or not chat_id:
        return JSONResponse({"error": "Token e Chat ID são obrigatórios para o teste."}, status_code=400)
    result = test_telegram_connection(token, chat_id)
    return result


@app.post("/api/settings/thresholds")
async def save_thresholds(request: Request):
    """Salva os thresholds de score para alertas e candidatura automática."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    data = await request.json()
    s = load_settings()
    if "smart_score_threshold" in data:
        s["smart_score_threshold"] = int(data["smart_score_threshold"])
    if "auto_score_threshold" in data:
        s["auto_score_threshold"] = int(data["auto_score_threshold"])
    if "auto_apply_daily_limit" in data:
        s["auto_apply_daily_limit"] = int(data["auto_apply_daily_limit"])
    save_settings(s)
    return {"success": True}


@app.get("/api/jobs/{job_id}/approve_redirect")
async def approve_redirect(job_id: str):
    """Aprovação rápida via link do Telegram — redireciona para o painel após aprovar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job_id,))
        conn.commit()
    # Redireciona para o painel principal
    return RedirectResponse(url="/?tab=vagas&highlight=" + job_id, status_code=302)


@app.get("/api/jobs/{job_id}/reject_redirect")
async def reject_redirect(job_id: str):
    """Rejeição rápida via link do Telegram — redireciona para o painel após rejeitar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = 'rejected' WHERE id = ?", (job_id,))
        conn.commit()
    return RedirectResponse(url="/?tab=vagas", status_code=302)
