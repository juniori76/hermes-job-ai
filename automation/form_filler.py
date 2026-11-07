"""
Preenchedor genérico de formulários (ex.: InHire, Gupy, sites externos).
Fluxo: extrair campos -> LLM decide respostas -> preencher -> (opcional) enviar.
Por padrão roda em dry_run: preenche, tira print e NÃO clica em enviar.
"""

import os
import json
from typing import Any, Dict, List
from playwright.sync_api import Page

from automation.browser_session import open_session, human_pause, BASE_DIR
from core.answer_engine import answer_fields
from core.radar import load_profile

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")

EXTRACT_JS = """
() => {
  const out = [];
  const els = document.querySelectorAll('input, textarea, select');
  els.forEach((el, i) => {
    if (el.type === 'hidden' || el.type === 'submit' || el.disabled) return;
    if (!el.offsetParent && el.type !== 'file') return;
    if (!el.dataset.hermesId) el.dataset.hermesId = 'h' + i;
    let label = '';
    if (el.id) { const l = document.querySelector(`label[for="${el.id}"]`); if (l) label = l.innerText; }
    if (!label) { const p = el.closest('label, div'); if (p) label = p.innerText.split('\\n')[0]; }
    label = (label || el.placeholder || el.name || '').trim();
    const type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : el.type;
    const f = { id: el.dataset.hermesId, type, label, name: el.name || '' };
    if (type === 'select') f.options = [...el.options].map(o => o.text.trim()).filter(Boolean);
    if (type === 'radio' || type === 'checkbox') f.value = el.value;
    out.push(f);
  });
  return out;
}
"""


def extract_fields(page: Page) -> List[Dict[str, Any]]:
    fields = page.evaluate(EXTRACT_JS)
    # Agrupa radios com o mesmo name em um único campo com opções
    grouped: Dict[str, Dict[str, Any]] = {}
    final: List[Dict[str, Any]] = []
    for f in fields:
        if f["type"] == "radio" and f["name"]:
            g = grouped.setdefault(f["name"], {**f, "options": [], "ids": {}})
            lbl = page.evaluate(
                "(id) => { const e=document.querySelector(`[data-hermes-id='${id}']`);"
                " return (e.parentElement.innerText||e.value||'').trim(); }", f["id"])
            g["options"].append(lbl)
            g["ids"][lbl] = f["id"]
        else:
            final.append(f)
    final.extend(grouped.values())
    return final


def _fill(page: Page, field: Dict[str, Any], value: Any):
    if value is None:
        return
    sel = f"[data-hermes-id='{field['id']}']"
    t = field["type"]
    if t == "select":
        page.select_option(sel, label=str(value))
    elif t == "radio":
        rid = field.get("ids", {}).get(str(value))
        if rid:
            page.check(f"[data-hermes-id='{rid}']")
    elif t == "checkbox":
        if str(value).lower() in ("true", "sim", "yes"):
            page.check(sel)
    else:
        page.fill(sel, str(value))
    human_pause(0.4, 1.2)


def fill_application(job: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """Abre a vaga, preenche o formulário e retorna o relatório da execução."""
    profile = load_profile()
    report: Dict[str, Any] = {"job_id": job["id"], "status": "failed", "answers": {}}
    os.makedirs(SHOT_DIR, exist_ok=True)

    with open_session(headless=True) as ctx:
        page = ctx.new_page()
        page.goto(job["job_url"], wait_until="domcontentloaded")
        human_pause(2, 4)

        fields = extract_fields(page)
        if not fields:
            report["error"] = "Nenhum campo de formulário detectado (pode exigir clique em 'Candidatar-se')."
            report["status"] = "requires_human"
            return report

        answers = answer_fields(fields, profile, job)
        if answers.pop("_skip_job", False):
            report["status"] = "skipped"
            report["error"] = "Vaga incompatível com as preferências do perfil."
            return report

        for f in fields:
            if f["type"] == "file":
                if os.path.exists(RESUME_PATH):
                    page.set_input_files(f"[data-hermes-id='{f['id']}']", RESUME_PATH)
                continue
            _fill(page, f, answers.get(f["id"]))

        report["answers"] = {f["label"]: answers.get(f["id"]) for f in fields if f["id"] in answers}
        shot = os.path.join(SHOT_DIR, f"{job['id']}.png")
        page.screenshot(path=shot, full_page=True)
        report["screenshot"] = shot

        if dry_run:
            report["status"] = "dry_run"
        else:
            page.get_by_role("button", name="Enviar").or_(page.get_by_role("button", name="Candidatar")).first.click()
            human_pause(2, 4)
            report["status"] = "success"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report
