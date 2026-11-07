"""
Driver Especializado para LinkedIn Easy Apply (Candidatura Simplificada) - Hermes Job AI.
Navega passo a passo pelo modal, preenche campos usando a IA (respeitando o perfil),
anexa o currículo PDF se solicitado e detecta checkpoints/captchas para pausa e alerta no Telegram.
"""

import os
import time
from typing import Dict, Any, List
from playwright.sync_api import Page

from automation.browser_session import open_session, human_pause, human_type, BASE_DIR
from core.answer_engine import answer_fields
from core.radar import load_profile
from core.notifier import send_telegram_alert

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")


def detect_security_checkpoint(page: Page) -> bool:
    """Verifica se o LinkedIn apresentou um captcha ou desafio de segurança."""
    url = page.url.lower()
    if "checkpoint" in url or "challenge" in url:
        return True
    
    # Procura elementos típicos de captcha
    captcha_selectors = [
        "iframe[src*='captcha']",
        "iframe[src*='recaptcha']",
        "div[class*='captcha']",
        "#captcha-internal",
        "button:has-text('Verificar')"
    ]
    for sel in captcha_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                return True
        except Exception:
            pass
    return False


def apply_linkedin_easy(page: Page, job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Controla o fluxo do modal 'Candidatura Simplificada' do LinkedIn.
    Avança pelas etapas até a revisão final.
    """
    profile = load_profile()
    job_id = job.get("id", "linkedin_job")
    report = {"status": "failed", "job_id": job_id, "steps_completed": 0}

    # 1. Verifica checkpoint inicial
    if detect_security_checkpoint(page):
        msg = f"⚠️ *ATENÇÃO:* LinkedIn solicitou verificação de segurança/captcha!\nAbra o noVNC em http://192.168.0.123:6080 para resolver manualmente."
        send_telegram_alert(msg)
        report["status"] = "security_checkpoint"
        report["error"] = "Security checkpoint detectado."
        return report

    # 2. Localiza botão Candidatura Simplificada
    easy_apply_selectors = [
        "button.jobs-apply-button",
        "button:has-text('Candidatura simplificada')",
        "button:has-text('Easy Apply')",
        "[data-control-name='jobdetails_topcard_inapply']",
    ]
    
    clicked = False
    for sel in easy_apply_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                clicked = True
                print(f"[LinkedIn Apply] Clicou no botão Candidatura Simplificada ({sel})")
                human_pause(2.0, 3.5)
                break
        except Exception:
            pass

    if not clicked:
        report["error"] = "Botão de Candidatura Simplificada não encontrado ou vaga exige site externo."
        report["status"] = "requires_human"
        return report

    # 3. Loop de navegação pelo modal de múltiplos passos
    max_steps = 8
    for step in range(1, max_steps + 1):
        human_pause(1.5, 2.5)

        # Checa se caiu em checkpoint durante os passos
        if detect_security_checkpoint(page):
            msg = f"⚠️ *ATENÇÃO:* Verificação de segurança no LinkedIn durante o passo {step}!\nResolva no noVNC: http://192.168.0.123:6080"
            send_telegram_alert(msg)
            report["status"] = "security_checkpoint"
            return report

        # Se houver upload de currículo neste passo
        file_inputs = page.locator("input[type='file']")
        if file_inputs.count() > 0:
            if os.path.exists(RESUME_PATH):
                try:
                    file_inputs.first.set_input_files(RESUME_PATH)
                    print(f"[LinkedIn Apply] Currículo PDF anexado com sucesso.")
                    human_pause(1.5, 2.5)
                except Exception as up_e:
                    print(f"[LinkedIn Apply] Aviso upload: {up_e}")

        # Tenta avançar para o próximo passo
        # Verifica se chegamos na tela de "Revisar"
        review_btn = page.locator("button:has-text('Revisar'), button:has-text('Review')").first
        if review_btn.is_visible(timeout=800):
            print("[LinkedIn Apply] Chegou na etapa final de Revisão!")
            review_btn.click()
            human_pause(2.0, 3.0)

            # Tira print da tela de revisão
            shot_path = os.path.join(SHOT_DIR, f"{job_id}_linkedin_review.png")
            page.screenshot(path=shot_path, full_page=True)
            report["screenshot"] = shot_path

            if dry_run:
                report["status"] = "dry_run"
                print("[LinkedIn Apply ✅] Simulação concluída na tela de revisão sem submissão.")
                # Fecha o modal sem enviar
                try:
                    page.locator("button[aria-label='Fechar'], button[aria-label='Dismiss']").first.click()
                    human_pause(0.5, 1.0)
                    page.locator("button:has-text('Descartar'), button:has-text('Discard')").first.click()
                except Exception:
                    pass
                return report
            else:
                # Envio definitivo
                submit_btn = page.locator("button:has-text('Enviar candidatura'), button:has-text('Submit application')").first
                if submit_btn.is_visible(timeout=1500):
                    submit_btn.click()
                    human_pause(3.0, 5.0)
                    report["status"] = "success"
                    print("[LinkedIn Apply 🎉] Candidatura Simplificada enviada com sucesso!")
                    return report

        # Botão Avançar / Próximo
        next_btn = page.locator("button:has-text('Avançar'), button:has-text('Próximo'), button:has-text('Next')").first
        if next_btn.is_visible(timeout=1000):
            print(f"[LinkedIn Apply] Avançando passo {step}...")
            next_btn.click()
            report["steps_completed"] = step
            continue

        # Se não achou 'Avançar' nem 'Revisar', pode ter chegado ao fim ou travado
        break

    shot_path = os.path.join(SHOT_DIR, f"{job_id}_linkedin_final.png")
    page.screenshot(path=shot_path, full_page=True)
    report["screenshot"] = shot_path
    return report
