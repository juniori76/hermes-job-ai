"""
Driver Especializado para LinkedIn Easy Apply (Candidatura Simplificada) - Hermes Job AI.
Navega passo a passo pelo modal, preenche perguntas com IA (respeitando o perfil real),
anexa o currículo PDF se solicitado, tira screenshots de auditoria por etapa
e detecta checkpoints/captchas para pausa com alerta no Telegram e noVNC.
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


def detect_security_checkpoint(page: Page) -> bool:
    """Verifica se o LinkedIn apresentou um captcha ou desafio de segurança."""
    url = page.url.lower()
    if "checkpoint" in url or "challenge" in url or "security" in url:
        return True

    captcha_selectors = [
        "iframe[src*='captcha']",
        "iframe[src*='recaptcha']",
        "iframe[src*='arkoselabs']",
        "div[class*='captcha']",
        "#captcha-internal",
        "button:has-text('Verificar')",
        "button:has-text('Verify')"
    ]
    for sel in captcha_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=400):
                return True
        except Exception:
            pass
    return False


def _find_and_click_next(page: Page) -> bool:
    """Tenta localizar e clicar no botão de avançar para a próxima etapa."""
    next_selectors = [
        "button[aria-label*='Avançar']",
        "button[aria-label*='Next']",
        "button:has-text('Avançar')",
        "button:has-text('Próximo')",
        "button:has-text('Next')",
        "button.artdeco-button--primary:has-text('Continuar')",
    ]
    for sel in next_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click()
                human_pause(1.5, 2.5)
                return True
        except Exception:
            pass
    return False


def _dismiss_modal(page: Page):
    """Fecha e descarta o modal com segurança para modo dry-run."""
    dismiss_selectors = [
        "button[aria-label='Fechar']",
        "button[aria-label='Dismiss']",
        "button[data-test-modal-close-btn]",
        "button.artdeco-modal__dismiss"
    ]
    for sel in dismiss_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click()
                human_pause(0.8, 1.5)
                # Confirma descarte
                discard_btn = page.locator("button:has-text('Descartar'), button:has-text('Discard')").first
                if discard_btn.is_visible(timeout=1500):
                    discard_btn.click()
                    human_pause(1.0, 1.5)
                break
        except Exception:
            pass


def apply_linkedin_easy(page: Page, job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Controla o fluxo do modal 'Candidatura Simplificada' do LinkedIn.
    Avança pelas etapas até a revisão ou submissão final.
    """
    os.makedirs(SHOT_DIR, exist_ok=True)
    profile = load_profile()
    job_id = job.get("id", "linkedin_job")
    report: Dict[str, Any] = {
        "status": "failed",
        "job_id": job_id,
        "platform": "linkedin",
        "steps_completed": 0,
        "answers": {},
        "dry_run": dry_run
    }

    # 1. Verifica checkpoint inicial
    if detect_security_checkpoint(page):
        msg = ("⚠️ *ATENÇÃO: LinkedIn solicitou verificação de segurança!*\n"
               "Abra o noVNC em http://192.168.0.123:6080 para resolver manualmente.")
        send_telegram_alert(msg)
        report["status"] = "security_checkpoint"
        report["error"] = "Security checkpoint detectado no LinkedIn."
        return report

    # 2. Verifica se já se candidatou anteriormente
    already_applied_selectors = [
        "span:has-text('Candidatou-se há')",
        "span:has-text('Applied')",
        ".jobs-s-apply__application-link"
    ]
    for sel in already_applied_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                print(f"[LinkedIn Apply] Vaga já foi aplicada anteriormente.")
                report["status"] = "already_applied"
                report["error"] = "Candidatura já realizada previamente."
                return report
        except Exception:
            pass

    # 3. Localiza botão Candidatura Simplificada
    easy_apply_selectors = [
        "button.jobs-apply-button",
        "button:has-text('Candidatura simplificada')",
        "button:has-text('Easy Apply')",
        "[data-control-name='jobdetails_topcard_inapply']",
        "button[aria-label*='Candidatura simplificada']",
        "button[aria-label*='Easy Apply']"
    ]
    
    clicked = False
    for sel in easy_apply_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                clicked = True
                print(f"[LinkedIn Apply] Clicou no botão Candidatura Simplificada ({sel})")
                human_pause(2.5, 4.0)
                break
        except Exception:
            pass

    if not clicked:
        report["error"] = "Botão de Candidatura Simplificada não encontrado ou vaga exige site externo."
        report["status"] = "requires_human"
        shot_path = os.path.join(SHOT_DIR, f"{job_id}_no_easy_apply.png")
        page.screenshot(path=shot_path, full_page=True)
        report["screenshot"] = shot_path
        return report

    modal_container = ".jobs-easy-apply-modal, [role='dialog']"

    # 4. Loop de navegação pelo modal de múltiplos passos
    max_steps = 10
    for step in range(1, max_steps + 1):
        human_pause(1.5, 2.5)

        # Checa se caiu em checkpoint durante os passos
        if detect_security_checkpoint(page):
            msg = (f"⚠️ *ATENÇÃO: LinkedIn solicitou verificação no passo {step}!*\n"
                   f"Resolva no noVNC: http://192.168.0.123:6080")
            send_telegram_alert(msg)
            report["status"] = "security_checkpoint"
            return report

        # Anexa currículo PDF se houver input de upload no modal
        file_inputs = page.locator(f"{modal_container} input[type='file']")
        if file_inputs.count() > 0:
            if os.path.exists(RESUME_PATH):
                try:
                    file_inputs.first.set_input_files(RESUME_PATH)
                    print(f"[LinkedIn Apply] Currículo PDF anexado no passo {step}.")
                    human_pause(1.5, 2.5)
                except Exception as up_e:
                    print(f"[LinkedIn Apply] Aviso upload: {up_e}")

        # Extrai e responde campos do passo atual
        fields = extract_fields(page, container_selector=modal_container)
        unfilled = [f for f in fields if not f.get("current_value") and f.get("type") != "file"]
        if unfilled:
            answers = answer_fields(unfilled, profile, job)
            for f in unfilled:
                ans = answers.get(f["id"])
                if ans is not None:
                    _fill(page, f, ans)
                    report["answers"][f.get("label", f["id"])] = ans
            human_pause(1.0, 2.0)

        # Registra screenshot da etapa
        step_shot = os.path.join(SHOT_DIR, f"{job_id}_step_{step}.png")
        try:
            page.screenshot(path=step_shot)
        except Exception:
            pass

        # Verifica se estamos na tela de Revisão ("Revisar" / "Review")
        review_btn = page.locator("button:has-text('Revisar'), button:has-text('Review'), button[aria-label*='Revisar']").first
        if review_btn.is_visible(timeout=1000):
            print(f"[LinkedIn Apply] Encontrou botão 'Revisar' no passo {step}. Avançando...")
            review_btn.click()
            human_pause(2.5, 3.5)

        # Verifica se chegamos na tela final de envio ("Enviar candidatura" / "Submit application")
        submit_btn = page.locator("button:has-text('Enviar candidatura'), button:has-text('Submit application'), button[aria-label*='Enviar candidatura']").first
        if submit_btn.is_visible(timeout=1500):
            print("[LinkedIn Apply] Chegou na tela final de submissão!")
            final_shot = os.path.join(SHOT_DIR, f"{job_id}_linkedin_review.png")
            page.screenshot(path=final_shot)
            report["screenshot"] = final_shot
            report["steps_completed"] = step

            if dry_run:
                print("[LinkedIn Apply 🛡️ DRY-RUN] Simulação finalizada com sucesso. Descartando modal sem envio real.")
                _dismiss_modal(page)
                report["status"] = "dry_run"
                return report
            else:
                print("[LinkedIn Apply 🚀 REAL] Submetendo candidatura de verdade...")
                submit_btn.click()
                human_pause(3.5, 6.0)

                # Verifica tela de confirmação de envio
                confirm_shot = os.path.join(SHOT_DIR, f"{job_id}_linkedin_submitted.png")
                page.screenshot(path=confirm_shot)
                report["screenshot"] = confirm_shot
                report["status"] = "success"

                # Fecha modal de agradecimento
                _dismiss_modal(page)
                return report

        # Se não é a tela final, clica em "Avançar" / "Próximo"
        if _find_and_click_next(page):
            print(f"[LinkedIn Apply] Passo {step} concluído com sucesso.")
            report["steps_completed"] = step
            continue
        else:
            # Não achou botão para avançar nem submeter
            print(f"[LinkedIn Apply] Nenhum botão de avanço encontrado no passo {step}.")
            break

    # Se saiu do loop sem concluir
    final_shot = os.path.join(SHOT_DIR, f"{job_id}_linkedin_final.png")
    page.screenshot(path=final_shot)
    report["screenshot"] = final_shot
    return report
