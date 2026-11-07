"""
Motor de Candidatura Automática Real - Hermes Job AI (Fase 5).
Executa candidaturas completas via Playwright no Chromium,
preenchendo formulários, anexando data/curriculo.pdf, gerando auditoria com prints,
respeitando o limite diário e integrando aos modos Avaliação/Inteligente/Automático.
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
from automation.browser_session import open_session, human_pause, human_type, BASE_DIR
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
        
        # Se for sucesso, marca job como applied
        if status == "success":
            cursor.execute("UPDATE jobs SET status = 'applied', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        elif status == "failed":
            cursor.execute("UPDATE jobs SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        elif status == "dry_run":
            cursor.execute("UPDATE jobs SET status = 'dry_run', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
            
        conn.commit()


def detect_platform(url: str) -> str:
    """Identifica a plataforma da vaga pela URL."""
    u = url.lower()
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


def apply_to_job(job: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    Executa o fluxo completo de candidatura com Playwright.
    dry_run=True apenas simula, tira screenshot e não envia.
    """
    job_id = job.get("id")
    url = job.get("job_url")
    title = job.get("title", "Vaga")
    company = job.get("company", "Empresa")
    platform = detect_platform(url)
    
    settings = load_settings()
    daily_limit = settings.get("auto_apply_daily_limit", 10)
    
    # 1. Verifica limite diário (se não for dry-run)
    if not dry_run:
        today_total = count_applications_today()
        if today_total >= daily_limit:
            msg = f"Limite diário de candidaturas atingido ({today_total}/{daily_limit})."
            print(f"[Apply Engine ⚠️] {msg}")
            log_application(job_id, platform, "failed", {}, error=msg)
            return {"status": "limit_reached", "error": msg}

    os.makedirs(SHOT_DIR, exist_ok=True)
    profile = load_profile()
    report: Dict[str, Any] = {
        "job_id": job_id,
        "platform": platform,
        "status": "failed",
        "dry_run": dry_run,
        "answers": {}
    }

    print(f"\n[Apply Engine] 🚀 Iniciando candidatura: {title} @ {company} ({platform})")
    print(f"  URL: {url}")
    print(f"  Modo: {'DRY-RUN (Simulação)' if dry_run else 'REAL'}")

    try:
        with open_session(headless=True) as ctx:
            page = ctx.new_page()
            
            # Carrega a página da vaga
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"[Apply Engine] Timeout ao abrir página: {e}")
                page.goto(url, timeout=30000)
                
            human_pause(2.5, 4.5)

            # Verifica se há botão inicial de 'Candidatar-se' para abrir formulário
            apply_triggers = [
                "button:has-text('Candidatar')",
                "button:has-text('Candidatar-se')",
                "a:has-text('Candidatar-se')",
                "a:has-text('Apply')",
                "button:has-text('Apply')",
                "[data-testid='apply-button']",
                ".job-apply-button",
                "button:has-text('Quero me candidatar')",
            ]
            for selector in apply_triggers:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1500):
                        print(f"[Apply Engine] Clicando no gatilho de candidatura: {selector}")
                        btn.click()
                        human_pause(2.0, 3.5)
                        break
                except Exception:
                    pass

            # Detecta campos do formulário
            fields = extract_fields(page)
            if not fields:
                # Pode estar pedindo login ou tela externa
                shot = os.path.join(SHOT_DIR, f"{job_id}_no_fields.png")
                page.screenshot(path=shot, full_page=True)
                err = "Nenhum campo de formulário detectado na página (pode exigir login manual prévio)."
                print(f"[Apply Engine ⚠️] {err}")
                log_application(job_id, platform, "requires_human", {}, shot_path=shot, error=err)
                return {"status": "requires_human", "error": err, "screenshot": shot}

            print(f"[Apply Engine] {len(fields)} campos detectados no formulário.")

            # Gera respostas com LLM baseando-se estritamente no perfil
            answers = answer_fields(fields, profile, job)
            if answers.pop("_skip_job", False):
                err = "Vaga rejeitada pelo motor de respostas (exige requisito incompatível)."
                print(f"[Apply Engine] {err}")
                log_application(job_id, platform, "skipped", {}, error=err)
                return {"status": "skipped", "error": err}

            # Preenche cada campo
            for f in fields:
                if f["type"] == "file":
                    if os.path.exists(RESUME_PATH):
                        try:
                            print(f"[Apply Engine] Anexando currículo em: {f.get('label')}")
                            page.set_input_files(f"[data-hermes-id='{f['id']}']", RESUME_PATH)
                            human_pause(1.0, 2.0)
                        except Exception as up_err:
                            print(f"[Apply Engine] Aviso ao anexar arquivo: {up_err}")
                    continue
                
                ans_val = answers.get(f["id"])
                if ans_val is not None:
                    _fill(page, f, ans_val)

            # Tira print do formulário preenchido (Auditoria)
            shot_file = f"{job_id}_{'dry' if dry_run else 'final'}.png"
            shot_path = os.path.join(SHOT_DIR, shot_file)
            page.screenshot(path=shot_path, full_page=True)
            report["screenshot"] = shot_path
            report["answers"] = {f.get("label", f["id"]): answers.get(f["id"]) for f in fields if f["id"] in answers}

            # Submissão
            if dry_run:
                report["status"] = "dry_run"
                log_application(job_id, platform, "dry_run", report["answers"], shot_path=shot_path)
                print(f"[Apply Engine ✅] Simulação concluída com sucesso! Screenshot salvo.")
            else:
                # Clica no botão final de envio
                submit_selectors = [
                    "button[type='submit']",
                    "button:has-text('Enviar Candidatura')",
                    "button:has-text('Enviar')",
                    "button:has-text('Finalizar')",
                    "button:has-text('Concluir')",
                    "button:has-text('Submit')",
                ]
                submitted = False
                for s in submit_selectors:
                    try:
                        btn = page.locator(s).first
                        if btn.is_visible(timeout=1500):
                            btn.click()
                            submitted = True
                            print(f"[Apply Engine] Clicou para enviar: {s}")
                            human_pause(3.0, 5.0)
                            break
                    except Exception:
                        pass

                if submitted:
                    report["status"] = "success"
                    log_application(job_id, platform, "success", report["answers"], shot_path=shot_path)
                    print(f"[Apply Engine 🎉] Candidatura enviada com sucesso!")
                    # Notifica no Telegram
                    try:
                        notify_application_sent(title, company, job_url=url, status="sent")
                    except Exception as tg_e:
                        print(f"[Apply Engine] Telegram aviso: {tg_e}")
                else:
                    err = "Formulário preenchido, mas botão final de envio não foi localizado com segurança."
                    report["status"] = "requires_human"
                    report["error"] = err
                    log_application(job_id, platform, "requires_human", report["answers"], shot_path=shot_path, error=err)
                    print(f"[Apply Engine ⚠️] {err}")

    except Exception as e:
        err = f"Falha durante a automação: {str(e)}"
        print(f"[Apply Engine ❌] {err}")
        log_application(job_id, platform, "failed", {}, error=err)
        return {"status": "failed", "error": err}

    return report


def get_approved_unapplied_jobs(limit: int = 5):
    """Busca vagas que foram aprovadas e ainda não foram aplicadas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE status = 'approved' 
            ORDER BY match_score DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
