"""
Motor de Candidatura Automática Real - Hermes Job AI.
Orquestra os drivers especializados (LinkedIn Easy Apply, Gupy Driver e Form Filler Genérico).
Opera com DISPLAY virtual :99 para permitir acompanhamento ao vivo via noVNC (porta 6080).
Aplica limites diários, pausas humanas, retentativas e auditoria com prints.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

from core.database import get_connection
from core.radar import load_profile
from core.settings_manager import load_settings
from core.notifier import notify_application_sent
from automation.browser_session import open_session, human_pause, BASE_DIR
from automation.linkedin_driver import apply_linkedin_easy
from automation.gupy_driver import apply_gupy_job
from automation.form_filler import extract_fields, _fill
from core.answer_engine import answer_fields

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")


def count_applications_today() -> int:
    """Retorna o número de candidaturas reais enviadas com sucesso no dia de hoje."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total FROM applications 
            WHERE status = 'success' 
              AND applied_at >= ?
        """, (f"{today} 00:00:00",))
        row = cursor.fetchone()
        return row["total"] if row else 0


def log_application(job_id: str, platform: str, status: str, answers: Dict[str, Any], shot_path: str = None, error: str = None):
    """Grava o registro de auditoria na tabela applications e atualiza status da vaga."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO applications (job_id, platform, status, answers_json, screenshot_path, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            platform,
            status,
            json.dumps(answers, ensure_ascii=False),
            shot_path,
            error
        ))
        
        if status == "success":
            cursor.execute("UPDATE jobs SET status = 'applied', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        elif status == "failed":
            cursor.execute("UPDATE jobs SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        elif status == "dry_run":
            cursor.execute("UPDATE jobs SET status = 'dry_run', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        elif status == "already_applied":
            cursor.execute("UPDATE jobs SET status = 'applied', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
            
        conn.commit()


def detect_platform(url: str) -> str:
    """Identifica a plataforma da vaga pela URL."""
    u = (url or "").lower()
    if "gupy.io" in u:
        return "gupy"
    elif "linkedin.com" in u:
        return "linkedin"
    elif "indeed.com" in u:
        return "indeed"
    elif "glassdoor" in u:
        return "glassdoor"
    elif "inhire.app" in u:
        return "inhire"
    elif "lever.co" in u:
        return "lever"
    elif "greenhouse.io" in u:
        return "greenhouse"
    return "generic"


def _apply_generic(page, job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """Driver genérico para páginas de vagas externas com formulário."""
    job_id = job.get("id", "generic_job")
    report: Dict[str, Any] = {"status": "failed", "job_id": job_id, "platform": "generic", "answers": {}}
    profile = load_profile()

    fields = extract_fields(page)
    if not fields:
        shot = os.path.join(SHOT_DIR, f"{job_id}_no_fields.png")
        page.screenshot(path=shot, full_page=True)
        report["status"] = "requires_human"
        report["error"] = "Campos não detectados ou formulário exige autenticação externa."
        report["screenshot"] = shot
        return report

    answers = answer_fields(fields, profile, job)
    if answers.pop("_skip_job", False):
        report["status"] = "skipped"
        report["error"] = "Vaga incompatível com as preferências do perfil."
        return report

    for f in fields:
        if f.get("type") == "file" and os.path.exists(RESUME_PATH):
            try:
                page.set_input_files(f"[data-hermes-id='{f['id']}']", RESUME_PATH)
            except Exception:
                pass
            continue
        ans = answers.get(f["id"])
        if ans is not None:
            _fill(page, f, ans)
            report["answers"][f.get("label", f["id"])] = ans

    shot = os.path.join(SHOT_DIR, f"{job_id}_{'dry' if dry_run else 'final'}.png")
    page.screenshot(path=shot, full_page=True)
    report["screenshot"] = shot

    if dry_run:
        report["status"] = "dry_run"
        return report

    # Submissão no modo real
    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Enviar')",
        "button:has-text('Candidatar')",
        "button:has-text('Submit')",
        "input[type='submit']"
    ]
    for sel in submit_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                loc.click()
                human_pause(3.0, 5.0)
                report["status"] = "success"
                return report
        except Exception:
            pass

    report["status"] = "requires_human"
    return report


def apply_to_job(job: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    Executa o fluxo de candidatura com Playwright delegando para o driver correto.
    Suporta retentativas e visualização ao vivo via noVNC (DISPLAY=:99).
    """
    job_id = job.get("id")
    url = job.get("job_url")
    title = job.get("title", "Vaga")
    company = job.get("company", "Empresa")
    platform = detect_platform(url)
    
    settings = load_settings()
    daily_limit = settings.get("auto_apply_daily_limit", 10)
    
    # 1. Checa limite diário de candidaturas
    if not dry_run:
        today_total = count_applications_today()
        if today_total >= daily_limit:
            msg = f"Limite diário de candidaturas atingido ({today_total}/{daily_limit})."
            print(f"[Apply Engine ⚠️] {msg}")
            log_application(job_id, platform, "failed", {}, error=msg)
            return {"status": "limit_reached", "error": msg}

    os.makedirs(SHOT_DIR, exist_ok=True)
    report: Dict[str, Any] = {
        "job_id": job_id,
        "platform": platform,
        "status": "failed",
        "dry_run": dry_run,
        "answers": {}
    }

    print(f"\n[Apply Engine] 🚀 Iniciando candidatura: {title} @ {company} ({platform})")
    print(f"  URL: {url} | Modo: {'DRY-RUN' if dry_run else 'REAL'}")

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            # headless=False para permitir que a janela seja renderizada no X11/noVNC
            with open_session(headless=False) as ctx:
                page = ctx.new_page()
                page.set_default_timeout(35000)
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40000)
                except Exception:
                    page.goto(url, timeout=30000)
                human_pause(2.0, 3.5)

                # Roteia para o driver da plataforma
                if platform == "linkedin":
                    report = apply_linkedin_easy(page, job, dry_run=dry_run)
                elif platform == "gupy":
                    report = apply_gupy_job(page, job, dry_run=dry_run)
                else:
                    report = _apply_generic(page, job, dry_run=dry_run)

                # Se obteve um resultado definitivo, sai do loop de tentativas
                if report.get("status") in ("success", "dry_run", "already_applied", "requires_login", "security_checkpoint"):
                    break

        except Exception as e:
            err = f"Tentativa {attempt}/{max_retries} falhou: {str(e)}"
            print(f"[Apply Engine ⚠️] {err}")
            if attempt == max_retries:
                report["status"] = "failed"
                report["error"] = err

    # Registra no banco de dados para auditoria
    log_application(
        job_id,
        platform,
        report.get("status", "failed"),
        report.get("answers", {}),
        shot_path=report.get("screenshot"),
        error=report.get("error")
    )

    # Notifica via Telegram
    if report.get("status") == "success" and not dry_run:
        try:
            notify_application_sent(title, company, job_url=url, status="sent")
        except Exception as te:
            print(f"[Apply Engine] Aviso Telegram: {te}")
    elif report.get("status") == "dry_run":
        try:
            notify_application_sent(title, company, job_url=url, status="dry_run")
        except Exception:
            pass

    return report


def get_approved_unapplied_jobs(limit: int = 5):
    """Busca vagas aprovadas que ainda não foram aplicadas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE status = 'approved' 
            ORDER BY match_score DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
