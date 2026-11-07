"""
Driver Especializado para Gupy - Hermes Job AI.
Navega pelo portal de vagas da Gupy, inicia o processo de candidatura,
preenche dados do candidato e submete etapas conforme perfil.
"""

import os
import time
from typing import Dict, Any
from playwright.sync_api import Page

from automation.browser_session import open_session, human_pause, human_type, BASE_DIR
from automation.form_filler import extract_fields, _fill
from core.answer_engine import answer_fields
from core.radar import load_profile

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")


def apply_gupy_job(page: Page, job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Fluxo de candidatura para páginas de vagas na Gupy.
    """
    job_id = job.get("id", "gupy_job")
    profile = load_profile()
    report = {"status": "failed", "job_id": job_id}

    # 1. Localiza botão Candidatar-se na Gupy
    apply_selectors = [
        "button[data-testid='apply-button']",
        "a[data-testid='apply-button']",
        "button:has-text('Candidatar-se para a vaga')",
        "button:has-text('Candidatar-se')",
        "a:has-text('Candidatar-se')",
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

    # 2. Se exigir login, verifica se a tela de login apareceu
    if "login" in page.url.lower():
        report["status"] = "requires_login"
        report["error"] = "Sessão da Gupy não autenticada. Acesse o noVNC (porta 6080) para logar."
        return report

    # 3. Detecta campos do formulário/etapas da Gupy
    fields = extract_fields(page)
    if fields:
        answers = answer_fields(fields, profile, job)
        for f in fields:
            if f["type"] == "file" and os.path.exists(RESUME_PATH):
                try:
                    page.set_input_files(f"[data-hermes-id='{f['id']}']", RESUME_PATH)
                except Exception:
                    pass
                continue
            ans = answers.get(f["id"])
            if ans is not None:
                _fill(page, f, ans)

    # 4. Tira screenshot de auditoria
    shot_path = os.path.join(SHOT_DIR, f"{job_id}_gupy.png")
    page.screenshot(path=shot_path, full_page=True)
    report["screenshot"] = shot_path

    if dry_run:
        report["status"] = "dry_run"
        print("[Gupy Apply ✅] Simulação concluída na Gupy sem submissão.")
        return report

    # Botão de finalizar se não for dry_run
    submit_btn = page.locator("button:has-text('Enviar candidatura'), button:has-text('Concluir')").first
    if submit_btn.is_visible(timeout=2000):
        submit_btn.click()
        human_pause(3.0, 5.0)
        report["status"] = "success"
        print("[Gupy Apply 🎉] Candidatura enviada na Gupy com sucesso!")
    else:
        report["status"] = "requires_human"

    return report
