"""
Driver Especializado para Gupy - Hermes Job AI.
Navega pelo portal de vagas da Gupy, inicia o processo de candidatura,
preenche dados do candidato, responde perguntas customizadas respeitando o perfil real,
anexa currículo e navega pelos passos até a revisão ou submissão.
"""

import os
import time
from typing import Dict, Any, List
from playwright.sync_api import Page

from automation.browser_session import human_pause, human_type, BASE_DIR
from automation.form_filler import extract_fields, _fill
from core.answer_engine import answer_fields
from core.radar import load_profile
from core.notifier import send_telegram_alert

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")


def _is_gupy_login_required(page: Page) -> bool:
    """Detecta se a Gupy solicitou autenticação do candidato."""
    url = page.url.lower()
    if "login" in url or "signin" in url:
        return True
    
    login_indicators = [
        "input[type='password']",
        "button:has-text('Entrar com')",
        "h1:has-text('Identifique-se')",
        "h2:has-text('Identifique-se')",
        "a[href*='login']"
    ]
    for sel in login_indicators:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                return True
        except Exception:
            pass
    return False


def apply_gupy_job(page: Page, job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Fluxo de candidatura completo para páginas de vagas na Gupy.
    Acompanha os passos do wizard da Gupy respeitando o modo dry-run.
    """
    os.makedirs(SHOT_DIR, exist_ok=True)
    job_id = job.get("id", "gupy_job")
    profile = load_profile()
    report: Dict[str, Any] = {
        "status": "failed",
        "job_id": job_id,
        "platform": "gupy",
        "steps_completed": 0,
        "answers": {},
        "dry_run": dry_run
    }

    # 1. Verifica se já está na tela de login antes de qualquer clique
    if _is_gupy_login_required(page):
        msg = ("⚠️ *ATENÇÃO: Gupy exige login!*\n"
               "Abra o noVNC em http://192.168.0.123:6080 para fazer login na Gupy uma única vez.")
        send_telegram_alert(msg)
        report["status"] = "requires_login"
        report["error"] = "Sessão da Gupy não autenticada."
        return report

    # 2. Localiza botão Candidatar-se na Gupy
    apply_selectors = [
        "button[data-testid='apply-button']",
        "a[data-testid='apply-button']",
        "button:has-text('Candidatar-se para a vaga')",
        "button:has-text('Candidatar-se')",
        "a:has-text('Candidatar-se')",
        "button:has-text('Apply for job')"
    ]

    clicked = False
    for sel in apply_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                clicked = True
                print(f"[Gupy Apply] Clicou no botão de candidatura: {sel}")
                human_pause(2.5, 4.0)
                break
        except Exception:
            pass

    # 3. Re-verifica login pós clique
    if _is_gupy_login_required(page):
        msg = ("⚠️ *ATENÇÃO: Gupy solicitou login ao clicar em candidatar!*\n"
               "Abra o noVNC em http://192.168.0.123:6080 para autenticar sua conta.")
        send_telegram_alert(msg)
        report["status"] = "requires_login"
        report["error"] = "Sessão da Gupy exige login manual."
        return report

    # 4. Loop de etapas do formulário da Gupy
    max_steps = 6
    for step in range(1, max_steps + 1):
        human_pause(2.0, 3.5)

        # Upload de currículo se solicitado na etapa
        file_inputs = page.locator("input[type='file']")
        if file_inputs.count() > 0 and os.path.exists(RESUME_PATH):
            try:
                file_inputs.first.set_input_files(RESUME_PATH)
                print(f"[Gupy Apply] Currículo PDF anexado na etapa {step}.")
                human_pause(1.5, 2.5)
            except Exception as e:
                print(f"[Gupy Apply] Aviso upload: {e}")

        # Extração e preenchimento de campos da etapa
        fields = extract_fields(page)
        unfilled = [f for f in fields if not f.get("current_value") and f.get("type") != "file"]
        if unfilled:
            answers = answer_fields(unfilled, profile, job)
            for f in unfilled:
                ans = answers.get(f["id"])
                if ans is not None:
                    _fill(page, f, ans)
                    report["answers"][f.get("label", f["id"])] = ans
            human_pause(1.0, 2.0)

        # Screenshot da etapa atual
        step_shot = os.path.join(SHOT_DIR, f"{job_id}_gupy_step_{step}.png")
        try:
            page.screenshot(path=step_shot)
        except Exception:
            pass

        # Verifica se chegamos na tela final de confirmação / envio
        submit_selectors = [
            "button:has-text('Concluir candidatura')",
            "button:has-text('Finalizar candidatura')",
            "button:has-text('Enviar candidatura')",
            "button:has-text('Confirmar candidatura')",
            "button[data-testid='submit-application-button']"
        ]
        submit_btn = None
        for sel in submit_selectors:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    submit_btn = loc
                    break
            except Exception:
                pass

        if submit_btn:
            print(f"[Gupy Apply] Encontrou botão final de submissão na etapa {step}!")
            shot_path = os.path.join(SHOT_DIR, f"{job_id}_gupy_review.png")
            page.screenshot(path=shot_path, full_page=True)
            report["screenshot"] = shot_path
            report["steps_completed"] = step

            if dry_run:
                print("[Gupy Apply 🛡️ DRY-RUN] Simulação concluída com sucesso na Gupy sem submissão.")
                report["status"] = "dry_run"
                return report
            else:
                print("[Gupy Apply 🚀 REAL] Enviando candidatura definitiva na Gupy...")
                submit_btn.click()
                human_pause(4.0, 6.0)
                confirm_shot = os.path.join(SHOT_DIR, f"{job_id}_gupy_submitted.png")
                page.screenshot(path=confirm_shot, full_page=True)
                report["screenshot"] = confirm_shot
                report["status"] = "success"
                return report

        # Botão Avançar / Próximo na Gupy
        next_selectors = [
            "button:has-text('Próximo')",
            "button:has-text('Avançar')",
            "button:has-text('Continuar')",
            "button:has-text('Salvar e continuar')",
            "button[data-testid='next-step-button']"
        ]
        advanced = False
        for sel in next_selectors:
            try:
                nxt = page.locator(sel).first
                if nxt.is_visible(timeout=800):
                    nxt.click()
                    advanced = True
                    print(f"[Gupy Apply] Avançando para próximo passo da Gupy ({sel})...")
                    human_pause(2.0, 3.5)
                    report["steps_completed"] = step
                    break
            except Exception:
                pass

        if not advanced:
            # Não há próximo passo nem botão final detectado
            print(f"[Gupy Apply] Nenhum botão de avanço encontrado no passo {step}.")
            break

    # Screenshot de conclusão
    shot_path = os.path.join(SHOT_DIR, f"{job_id}_gupy_final.png")
    page.screenshot(path=shot_path, full_page=True)
    report["screenshot"] = shot_path
    if report["steps_completed"] > 0:
        report["status"] = "dry_run" if dry_run else "requires_human"
    return report
