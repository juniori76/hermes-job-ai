"""
Backend Web HTTP do Hermes Job AI.
Interface FastAPI leve para monitoramento e controle de candidaturas.
"""

import os
import shutil
import yaml
from typing import Optional
from fastapi import FastAPI, Request, BackgroundTasks, UploadFile, File, Form, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.database import (
    get_connection, init_db, record_application,
    get_user_applications, update_application_stage, delete_application
)
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
from core.profiles_manager import list_profiles, get_profile, save_profile, get_resume_path
from core.visual_copilot import answer_job_question
from core.resume_optimizer import optimize_resume_for_target
from core.ats_lab import analyze_standalone_resume
from core.cover_letter import generate_cover_letter
from core.backup_manager import create_backup, list_backups
from core.profiles_manager import save_resume_file
from core.telegram_multi_router import (
    start_telegram_listener, list_all_bindings, bind_user_telegram
)
from automation.apply_engine import apply_to_job
from automation.browser_session import check_auth_status, launch_assisted_login

app = FastAPI(title="Hermes Job AI Dashboard")

@app.on_event("startup")
async def startup_event():
    init_db()
    start_telegram_listener()

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
    """Página principal do Dashboard (Protegida por Login e Isolada por Perfil)."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    profile = get_profile(user)
    user_resume = get_resume_path(user)
    resume_exists = bool(user_resume and os.path.exists(user_resume))
    gemini_key_set = config.has_api_key()

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Métricas isoladas para o perfil do usuário logado
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE target_user = ?;", (user,))
        user_total_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE target_user = ? AND match_score >= 75;", (user,))
        user_high_match_jobs = cursor.fetchone()[0]

        # Métricas globais informativas do banco
        cursor.execute("SELECT COUNT(*) FROM jobs;")
        global_total_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE match_score >= 75;")
        global_high_match_jobs = cursor.fetchone()[0]
        
        user_apps = get_user_applications(user_id=user or "eduardo")

        # Top 150 melhores vagas ranqueadas priorizando o perfil atual (carregamento ultra-rápido)
        cursor.execute("""
            SELECT id, site, title, company, location, is_remote, job_url, 
                   match_score, match_reasons, keywords_found, status, date_posted, created_at, target_user,
                   salary_min, salary_max, description
            FROM jobs
            ORDER BY 
                CASE WHEN target_user = ? THEN 0 ELSE 1 END,
                CASE WHEN match_score IS NULL THEN 0 ELSE match_score END DESC,
                created_at DESC
            LIMIT 150;
        """, (user,))
        raw_jobs = [dict(row) for row in cursor.fetchall()]

        # Carrega os perfis em memória UMA ÚNICA VEZ
        from core.profiles_manager import list_profiles
        from core.telegram_multi_router import route_job_to_user
        from core.salary_oracle import estimate_job_salary
        from core.company_analyzer import get_company_health_insight
        cached_profiles = list_profiles()

        # Processa tags de antiguidade da vaga e inteligência de mercado
        jobs = []
        for j in raw_jobs:
            age = calculate_job_age_hours(j.get("date_posted") or j.get("created_at", ""))
            badge_text, badge_css, badge_icon = format_job_badge(age)
            j["age_hours"] = age
            j["badge_text"] = badge_text
            j["badge_css"] = badge_css
            j["badge_icon"] = badge_icon
            if not j.get("target_user"):
                j["target_user"] = route_job_to_user(j, cached_profiles)
            
            # Inteligência de Mercado: Salário Médio & Reputação da Empresa
            j["salary_insight"] = estimate_job_salary(j)
            j["company_insight"] = get_company_health_insight(j.get("company", ""), conn)
            # Remove texto bruto de descrição para enxugar o HTML e carregar instantaneamente
            j.pop("description", None)

            jobs.append(j)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "total_jobs": user_total_jobs,
            "high_match_jobs": user_high_match_jobs,
            "global_total_jobs": global_total_jobs,
            "user_total_jobs": user_total_jobs,
            "applied_jobs": len(user_apps),
            "jobs": jobs,
            "applications": user_apps,
            "applications_count": len(user_apps),
            "profile": profile,
            "resume_exists": resume_exists,
            "gemini_key_set": gemini_key_set,
            "current_user": user,
            "all_profiles": cached_profiles
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
async def upload_resume_settings(request: Request, file: UploadFile = File(...), username: Optional[str] = Form(None)):
    """Faz upload do curriculo em PDF pelo painel para o perfil do usuario indicado ou logado."""
    user = get_current_user(request) or "eduardo"
    target_user = (username or user).strip().lower()
    content = await file.read()
    save_resume_file(target_user, content)
    if target_user == "eduardo":
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "curriculo.pdf"), "wb") as buffer:
            buffer.write(content)
    try:
        sync_profile_from_resume_ai(target_user)
    except Exception as e:
        print(f"[Upload] Erro ao sincronizar perfil de {target_user}: {e}")
    return {"success": True, "filename": file.filename, "user": target_user}


@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks, request: Request = None, term: Optional[str] = None):
    """Dispara uma varredura de novas vagas em segundo plano (especifica para o usuario logado ou geral)."""
    user = get_current_user(request) if request else None
    if not term and request:
        try:
            body = await request.json()
            term = body.get("term")
        except Exception:
            pass
    if term and term.strip():
        background_tasks.add_task(scan_jobs, 15, [term.strip()])
        return {"message": f"Varredura iniciada para o termo '{term.strip()}'!"}
        
    if user:
        u_prof = get_profile(user)
        u_cargos = u_prof.get("preferencias_de_vaga", {}).get("cargos_alvo") or u_prof.get("cargos_alvo", [])
        if u_cargos:
            background_tasks.add_task(scan_jobs, 15, u_cargos)
            return {"message": f"Varredura iniciada para os cargos de @{user}: {', '.join(u_cargos[:3])}!"}

    background_tasks.add_task(scan_jobs)
    return {"message": "Varredura iniciada para todos os cargos configurados no radar!"}


@app.post("/api/resume/upload")
async def upload_resume(request: Request, file: UploadFile = File(...), username: Optional[str] = Form(None)):
    """Recebe upload de novo curriculo PDF para o perfil ativo e sincroniza com a IA."""
    user = get_current_user(request) or "eduardo"
    target_user = (username or user).strip().lower()
    
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Apenas arquivos PDF (.pdf) sao aceitos."}, status_code=400)
        
    content = await file.read()
    save_resume_file(target_user, content)
    if target_user == "eduardo":
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "curriculo.pdf"), "wb") as buffer:
            buffer.write(content)
        
    # Reanalisa com IA e sincroniza perfil do usuario
    analysis = analyze_resume_with_ai(target_user)
    sync = sync_profile_from_resume_ai(target_user)
    
    return {
        "success": True,
        "message": f"Curriculo de @{target_user} ('{file.filename}') recebido e analisado pela IA com sucesso!",
        "analysis": analysis,
        "sync": sync,
        "user": target_user
    }


@app.get("/api/resume/analysis")
async def get_resume_analysis(request: Request, username: Optional[str] = None):
    """Retorna o diagnostico de IA do curriculo do usuario logado."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    target_user = (username or user).strip().lower()
    analysis = analyze_resume_with_ai(target_user)
    return analysis


@app.post("/api/profile/sync")
async def trigger_profile_sync(request: Request):
    """Dispara a extracao profunda de dados do PDF para o perfil do usuario logado."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    try:
        body = await request.json()
        target_user = body.get("username", user).strip().lower()
    except Exception:
        target_user = user
    result = sync_profile_from_resume_ai(target_user)
    return result


@app.post("/api/settings/profile")
async def update_profile_settings(request: Request):
    """Salva todas as regras de modalidade, km, salário e cargos atualizadas pelo painel para o perfil logado."""
    user = get_current_user(request) or "eduardo"
    data = await request.json()
    current = get_profile(user)
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

    save_profile(user, current)
    if user == "eduardo":
        with open(os.path.join(CONFIG_DIR, "candidate_profile.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(current, f, allow_unicode=True)

    return {"success": True, "message": "Políticas de vaga, km e salários salvas com sucesso!"}


@app.post("/api/evaluate")
async def trigger_evaluation(background_tasks: BackgroundTasks):
    """Dispara a avaliação de compatibilidade ATS com Gemini Flash em segundo plano."""
    background_tasks.add_task(run_ats_evaluation_batch)
    return {"message": "Avaliação de ATS iniciada com Gemini Flash!"}


@app.post("/api/jobs/{job_id}/status")
async def update_status(job_id: str, request: Request):
    """Altera o status de uma vaga (ex: 'approved', 'rejected', 'applied')."""
    data = await request.json()
    new_status = data.get("status")
    current_u = get_current_user(request) or data.get("user_id") or "eduardo"
    
    if new_status == "applied":
        res = record_application(job_id=job_id, user_id=current_u, stage="em_processo")
        return {"success": True, "job_id": job_id, "new_status": "applied", "application": res}
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, job_id))
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



# =========================================================
# FASE 5 — Gestão & Histórico de Candidaturas (Funil)
# =========================================================

@app.get("/api/applications")
async def api_get_applications(request: Request, user_id: Optional[str] = None, stage: Optional[str] = None):
    """Retorna o histórico de candidaturas no pipeline com filtros."""
    current_u = get_current_user(request) or "eduardo"
    target_user = user_id if user_id else current_u
    apps = get_user_applications(user_id=target_user, stage=stage)
    return {"success": True, "applications": apps}


@app.post("/api/applications/{app_id}/stage")
async def api_update_app_stage(app_id: int, request: Request):
    """Atualiza o estágio da candidatura (ex: em_processo, entrevista, desclassificado, aprovado)."""
    data = await request.json()
    stage = data.get("stage", "em_processo")
    notes = data.get("notes")
    success = update_application_stage(app_id=app_id, stage=stage, notes=notes)
    return {"success": success, "app_id": app_id, "stage": stage}


@app.delete("/api/applications/{app_id}")
async def api_delete_application(app_id: int):
    """Remove uma candidatura do histórico."""
    success = delete_application(app_id)
    return {"success": success}


@app.get("/api/profiles")
async def api_list_profiles():
    """Lista todos os perfis cadastrados no sistema."""
    return {"profiles": list_profiles()}


@app.post("/api/copilot/answer")
async def api_copilot_answer(
    request: Request,
    username: str = Form("eduardo"),
    text_question: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Copiloto IA de Candidaturas: Analisa prints de tela (ou texto) de qualquer
    formulario de vaga e devolve a resposta definitiva pronta para copiar e colar.
    """
    image_bytes = None
    mime_type = "image/png"
    
    if file and file.filename:
        image_bytes = await file.read()
        mime_type = file.content_type or "image/png"
    
    # Suporte a envio direto via JSON com imagem em base64 (Ctrl+V no navegador)
    if not image_bytes and not text_question:
        try:
            body = await request.json()
            username = body.get("username", username)
            text_question = body.get("text_question")
            b64_img = body.get("image_base64")
            if b64_img:
                import base64
                if "," in b64_img:
                    header, b64_img = b64_img.split(",", 1)
                    if "jpeg" in header or "jpg" in header:
                        mime_type = "image/jpeg"
                image_bytes = base64.b64decode(b64_img)
        except Exception:
            pass

    res = answer_job_question(
        image_bytes=image_bytes,
        text_question=text_question,
        username=username,
        mime_type=mime_type
    )
    return res


# ==========================================
# ENDPOINTS ADMINISTRATIVOS (GESTAO DE PERFIS E LOGINS)
# ==========================================
from core.auth import create_user, delete_user, list_users
from core.profiles_manager import create_or_update_profile, save_resume_file, delete_profile


@app.get("/api/admin/profiles-full")
async def api_admin_profiles_full(request: Request):
    """Retorna a lista detalhada de perfis e seus dados completos para a area administrativa."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    
    profiles = list_profiles()
    full_data = []
    users_auth = list_users()
    
    for p in profiles:
        u_id = p["id"]
        cfg = get_profile(u_id)
        cand = cfg.get("candidato", {})
        prefs = cfg.get("preferencias_de_vaga", {})
        mods = prefs.get("modalidades", {})
        
        dist_km = 30
        if "hibrido" in mods:
            dist_km = mods["hibrido"].get("distancia_maxima_km", 30)
        elif "presencial" in mods:
            dist_km = mods["presencial"].get("distancia_maxima_km", 20)

        full_data.append({
            "id": u_id,
            "display_name": cand.get("nome_completo") or p["name"],
            "email": cand.get("email", ""),
            "telefone": cand.get("telefone", ""),
            "cidade": cand.get("cidade", "Diadema"),
            "estado": cand.get("estado", "SP"),
            "linkedin_url": cand.get("linkedin_url", ""),
            "cargos_alvo": prefs.get("cargos_alvo", []),
            "salario_min": prefs.get("salario_minimo_pretendido", 3000),
            "distancia_km": dist_km,
            "has_resume": p["has_resume"],
            "created_at": users_auth.get(u_id, {}).get("created_at", "")
        })
    return {"profiles": full_data}


@app.post("/api/admin/users/create")
async def api_admin_create_user(request: Request):
    """Cria um novo usuario de login e inicializa seu perfil no sistema."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    
    body = await request.json()
    username = body.get("username", "").strip().lower()
    password = body.get("password", "").strip()
    display_name = body.get("display_name", "").strip()
    cargos = body.get("cargos_alvo", [])
    if isinstance(cargos, str):
        cargos = [c.strip() for c in cargos.split(",") if c.strip()]
        
    if not username or not password:
        return JSONResponse({"error": "Usuario e senha sao obrigatorios."}, status_code=400)
        
    created = create_user(username, password, display_name=display_name)
    if not created:
        return JSONResponse({"error": "Usuario ja existe ou dados invalidos."}, status_code=400)
        
    create_or_update_profile(
        username=username,
        nome_completo=display_name or username.capitalize(),
        cargos_alvo=cargos or ["Assistente Administrativo", "Atendimento ao Cliente"]
    )
    return {"success": True, "message": f"Usuario '{username}' criado com sucesso!"}


@app.post("/api/admin/profiles/save")
async def api_admin_save_profile(request: Request):
    """Salva alteracoes cadastrais de qualquer perfil."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
        
    body = await request.json()
    username = body.get("username", "eduardo")
    nome = body.get("nome_completo", "")
    email = body.get("email", "")
    telefone = body.get("telefone", "")
    cidade = body.get("cidade", "Diadema")
    estado = body.get("estado", "SP")
    cargos = body.get("cargos_alvo", [])
    if isinstance(cargos, str):
        cargos = [c.strip() for c in cargos.split(",") if c.strip()]
    salario = body.get("salario_min", 3000)
    distancia = body.get("distancia_km", 30)
    linkedin = body.get("linkedin_url", "")
    
    create_or_update_profile(
        username=username,
        nome_completo=nome,
        email=email,
        telefone=telefone,
        cidade=cidade,
        estado=estado,
        cargos_alvo=cargos,
        salario_min=salario,
        distancia_km=int(distancia),
        linkedin_url=linkedin
    )
    return {"success": True, "message": "Perfil atualizado com sucesso!"}


@app.post("/api/admin/profiles/upload-resume")
async def api_admin_upload_resume(
    request: Request,
    username: str = Form("eduardo"),
    file: UploadFile = File(...)
):
    """Faz upload de curriculo PDF especifico para um perfil."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
        
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Apenas arquivos PDF sao permitidos."}, status_code=400)
        
    bytes_data = await file.read()
    save_resume_file(username, bytes_data)
    return {"success": True, "message": f"Curriculo de {username} atualizado com sucesso!"}


@app.post("/api/admin/users/delete")
async def api_admin_delete_user(request: Request):
    """Exclui um perfil e usuario adicional."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
        
    body = await request.json()
    username = body.get("username", "")
    if username.lower() == "eduardo":
        return JSONResponse({"error": "O perfil administrador principal nao pode ser excluido."}, status_code=400)
        
    delete_user(username)
    delete_profile(username)
    return {"success": True, "message": f"Perfil {username} excluido com sucesso."}


@app.post("/api/jobs/clean-rejected")
async def api_clean_rejected_jobs(request: Request):
    """Limpa do banco todas as vagas descartadas/rejeitadas pela IA e presenciais fora de SP."""
    if not get_current_user(request):
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE status in ('reject', 'rejected')")
        del1 = cursor.rowcount
        cursor.execute("""
            DELETE FROM jobs 
            WHERE status NOT IN ('applied', 'success') AND is_remote = 0 AND (
                location LIKE '% - PI%' OR location LIKE '%, PI%' OR location LIKE '%Teresina%' OR
                location LIKE '% - BA%' OR location LIKE '%, BA%' OR location LIKE '%Salvador%' OR
                location LIKE '% - CE%' OR location LIKE '%, CE%' OR location LIKE '%Fortaleza%' OR
                location LIKE '% - PE%' OR location LIKE '%, PE%' OR location LIKE '%Recife%' OR
                location LIKE '% - RJ%' OR location LIKE '%, RJ%' OR
                location LIKE '% - MG%' OR location LIKE '%, MG%' OR
                location LIKE '% - PR%' OR location LIKE '%, PR%' OR
                location LIKE '% - RS%' OR location LIKE '%, RS%' OR
                location LIKE '% - SC%' OR location LIKE '%, SC%' OR
                location LIKE '% - GO%' OR location LIKE '%, GO%' OR
                location LIKE '% - DF%' OR location LIKE '%, DF%' OR location LIKE '%Brasília%'
            )
        """)
        del2 = cursor.rowcount
        conn.commit()
    total_deleted = del1 + del2
    return {"success": True, "message": f"{total_deleted} vagas descartadas ou fora da região foram removidas com sucesso."}


@app.post("/api/resume/optimize")
async def api_optimize_resume(request: Request):
    """Otimiza o curriculo do membro contra cargo alvo ou vaga especifica para atingir 100% ATS.
    Pode usar o curriculo do perfil OU um arquivo avulso (PDF/DOCX/texto) sem alterar o perfil permanente."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Nao autorizado"}, status_code=401)
    
    content_type = request.headers.get("content-type", "")
    username = user
    target_role = None
    job_id = None
    custom_cv_text = None
    custom_job_desc = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        username = form.get("username", user) or user
        target_role = form.get("target_role")
        job_id = form.get("job_id")
        custom_cv_text = form.get("custom_cv_text")
        custom_job_desc = form.get("custom_job_desc")
        
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()
            if file_bytes:
                filename = getattr(uploaded_file, "filename", "").lower()
                extracted_text = ""
                if filename.endswith(".pdf") or file_bytes[:4] == b'%PDF':
                    try:
                        import pypdf, io
                        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                        extracted_text = "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
                    except Exception as e:
                        print(f"[Optimizer] Erro ao extrair PDF em memoria: {e}")
                elif filename.endswith(".docx"):
                    try:
                        import docx, io
                        doc = docx.Document(io.BytesIO(file_bytes))
                        extracted_text = "\n".join([p.text for p in doc.paragraphs if p.text]).strip()
                    except Exception as e:
                        print(f"[Optimizer] Erro ao extrair DOCX em memoria: {e}")
                else:
                    try:
                        extracted_text = file_bytes.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        pass
                if extracted_text:
                    custom_cv_text = extracted_text
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
            
        username = body.get("username", user) or user
        target_role = body.get("target_role")
        job_id = body.get("job_id")
        custom_cv_text = body.get("custom_cv_text")
        custom_job_desc = body.get("custom_job_desc")
        
    if job_id:
        job_id = str(job_id).strip() or None
            
    result = optimize_resume_for_target(
        username=username, 
        target_role=target_role, 
        job_id=job_id,
        custom_cv_text=custom_cv_text,
        custom_job_desc=custom_job_desc
    )
    return result


@app.get("/api/resume/download/{username}/{file_format}")
async def api_download_resume(username: str, file_format: str, request: Request):
    """Disponibiliza download direto do currículo otimizado em PDF ou DOCX."""
    if not get_current_user(request):
        return RedirectResponse(url="/login")
        
    file_format = file_format.lower().strip()
    if file_format not in ["pdf", "docx"]:
        return JSONResponse({"error": "Formato inválido. Use pdf ou docx."}, status_code=400)
        
    file_path = os.path.join(DATA_DIR, f"curriculo_{username}_otimizado.{file_format}")
    if not os.path.exists(file_path):
        return JSONResponse({"error": "Currículo otimizado ainda não gerado. Clique em 'Gerar Currículo 100% ATS' primeiro."}, status_code=404)
        
    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    
    filename = f"Curriculo_{username.capitalize()}_Otimizado_ATS.{file_format}"
    return FileResponse(
        path=file_path,
        media_type=media_types[file_format],
        filename=filename
    )



@app.get("/api/telegram/bindings")
async def api_get_telegram_bindings(request: Request):
    """Retorna o status de vinculação do Telegram de cada perfil da casa."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    bindings = list_all_bindings()
    profiles = list_profiles()
    result = []
    for p in profiles:
        u_id = p["id"]
        result.append({
            "username": u_id,
            "display_name": p.get("display_name", u_id.capitalize()),
            "chat_id": bindings.get(u_id),
            "is_linked": bool(bindings.get(u_id))
        })
    return {"bindings": result}


@app.post("/api/telegram/bind")
async def api_bind_telegram(request: Request):
    """Permite vincular manualmente o Chat ID de um membro pelo painel Web."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    body = await request.json()
    username = body.get("username", "").strip().lower()
    chat_id = body.get("chat_id", "").strip()
    if not username or not chat_id:
        return JSONResponse({"error": "Usuário e Chat ID são obrigatórios."}, status_code=400)
    success = bind_user_telegram(chat_id, username)
    if success:
        return {"success": True, "message": f"Telegram de @{username} vinculado com sucesso!"}
    return JSONResponse({"error": "Usuário não encontrado."}, status_code=400)


# ==========================================
# GERAÇÃO DE CARTA DE APRESENTAÇÃO (PITCH RH)
# ==========================================
@app.post("/api/jobs/cover-letter")
async def api_generate_cover_letter(request: Request):
    """Gera uma carta de apresentação sob medida para uma vaga e perfil de candidato."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    
    try:
        body = await request.json()
    except Exception:
        body = {}

    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        return JSONResponse({"error": "ID da vaga é obrigatório."}, status_code=400)
        
    target_user = body.get("user_id") or user
    if target_user == "all" or not target_user:
        target_user = user
    tone = body.get("tone") or "persuasivo"

    result = generate_cover_letter(job_id=job_id, username=target_user, tone=tone)
    if result.get("success"):
        return result
    return JSONResponse(result, status_code=400)


# ==========================================
# WIZARD DE ONBOARDING GUIADO (NOVO MEMBRO)
# ==========================================
@app.post("/api/onboarding/wizard")
async def api_onboarding_wizard(
    background_tasks: BackgroundTasks,
    request: Request,
    target_roles: str = Form(...),
    city: str = Form("Diadema"),
    state: str = Form("SP"),
    max_km_presential: int = Form(18),
    max_km_hybrid: int = Form(30),
    min_salary: float = Form(2500.0),
    resume_file: Optional[UploadFile] = File(None)
):
    """Configura o perfil do usuário em 1 passo guiado (cargos, localização, currículo e primeira varredura)."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)

    # 1. Atualiza preferências no profile.json
    prof = get_profile(user)
    roles_list = [r.strip() for r in target_roles.replace(";", ",").split(",") if r.strip()]
    if not roles_list:
        roles_list = [target_roles.strip()]

    prof["cargos_alvo"] = roles_list
    if "preferencias_de_vaga" not in prof:
        prof["preferencias_de_vaga"] = {}
    prof["preferencias_de_vaga"]["cargos_alvo"] = roles_list

    if "candidato" not in prof:
        prof["candidato"] = {}
    prof["candidato"]["cidade"] = city.strip()
    prof["candidato"]["estado"] = state.strip().upper()

    if "modalidades" not in prof["preferencias_de_vaga"]:
        prof["preferencias_de_vaga"]["modalidades"] = {}
    prof["preferencias_de_vaga"]["modalidades"]["presencial"] = {"distancia_maxima_km": max_km_presential}
    prof["preferencias_de_vaga"]["modalidades"]["hibrido"] = {"distancia_maxima_km": max_km_hybrid}

    if "financeiro" not in prof["preferencias_de_vaga"]:
        prof["preferencias_de_vaga"]["financeiro"] = {}
    prof["preferencias_de_vaga"]["financeiro"]["salario_minimo_clt"] = min_salary

    save_profile(user, prof)

    # 2. Se enviou currículo PDF, salva e analisa
    if resume_file and resume_file.filename:
        if resume_file.filename.lower().endswith(".pdf"):
            content = await resume_file.read()
            save_resume_file(user, content)
            try:
                sync_profile_from_resume_ai(user)
            except Exception as e:
                print(f"[Onboarding] Erro ao sincronizar com IA: {e}")

    # 3. Dispara a primeira varredura focada no perfil do usuário
    background_tasks.add_task(scan_jobs, 15, roles_list)

    return {
        "success": True, 
        "message": f"Perfil de @{user} configurado com sucesso! Primeira varredura iniciada para {len(roles_list)} cargos."
    }


# ==========================================
# BACKUP AUTOMÁTICO E INTEGRIDADE DO SISTEMA
# ==========================================
@app.post("/api/system/backup")
async def api_trigger_backup(request: Request):
    """Cria um snapshot compactado ZIP do banco de dados e perfis."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    res = create_backup()
    if res.get("success"):
        return res
    return JSONResponse(res, status_code=500)


@app.get("/api/system/backups")
async def api_list_backups(request: Request):
    """Lista histórico de backups salvos."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    return {"backups": list_backups()}


# ==========================================
# LABORATÓRIO ATS AVULSO (SANDBOX INDEPENDENTE)
# ==========================================
@app.post("/api/ats-lab/analyze")
async def api_ats_lab_analyze(
    request: Request,
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    target_role: Optional[str] = Form(None)
):
    """Analisa um currículo avulso em sandbox (PDF ou texto) sem alterar o perfil permanente do robô."""
    if not get_current_user(request):
        return JSONResponse({"error": "Não autorizado"}, status_code=401)
    
    pdf_bytes = None
    filename = None
    if file and file.filename:
        pdf_bytes = await file.read()
        filename = file.filename

    res = analyze_standalone_resume(
        pdf_bytes=pdf_bytes,
        raw_text=raw_text,
        target_role=target_role,
        filename=filename
    )
    if res.get("success"):
        return res
    return JSONResponse(res, status_code=400)
