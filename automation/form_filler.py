"""
Preenchedor genérico e especializado de formulários - Hermes Job AI.
Fluxo: extrair campos estruturados -> LLM decide respostas -> preencher -> validar -> submeter.
Suporta formulários nativos, modais dinâmicos (LinkedIn, Gupy, InHire, Lever, Greenhouse).
"""

import os
import json
import time
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

from automation.browser_session import human_pause, human_type, BASE_DIR
from core.answer_engine import answer_fields
from core.radar import load_profile

RESUME_PATH = os.path.join(BASE_DIR, "data", "curriculo.pdf")
SHOT_DIR = os.path.join(BASE_DIR, "data", "screenshots")

EXTRACT_JS = """
(containerSelector) => {
  const root = containerSelector ? (document.querySelector(containerSelector) || document) : document;
  const out = [];
  const els = root.querySelectorAll('input, textarea, select, [role="combobox"]');
  
  els.forEach((el, i) => {
    if (el.type === 'hidden' || el.type === 'submit' || el.disabled) return;
    if (!el.offsetParent && el.type !== 'file' && el.getAttribute('role') !== 'combobox') return;
    
    if (!el.dataset.hermesId) {
      el.dataset.hermesId = 'h_' + i + '_' + Math.random().toString(36).substr(2, 5);
    }
    
    let label = '';
    // 1. aria-label ou aria-labelledby
    if (el.getAttribute('aria-label')) {
      label = el.getAttribute('aria-label');
    } else if (el.getAttribute('aria-labelledby')) {
      const lblEl = document.getElementById(el.getAttribute('aria-labelledby'));
      if (lblEl) label = lblEl.innerText;
    }
    
    // 2. label[for="id"]
    if (!label && el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) label = l.innerText;
    }
    
    // 3. Closest label ou fieldset legend ou container do LinkedIn / Gupy
    if (!label) {
      const fieldset = el.closest('fieldset');
      if (fieldset) {
        const legend = fieldset.querySelector('legend');
        if (legend) label = legend.innerText;
      }
    }
    if (!label) {
      const group = el.closest('.jobs-easy-apply-form-section__grouping, .fb-dash-form-element, .form-group, .form-item, label');
      if (group) {
        const titleEl = group.querySelector('label, h3, h4, span.t-14, .artdeco-text-input--label');
        if (titleEl) label = titleEl.innerText;
        else label = group.innerText.split('\\n')[0];
      }
    }
    
    // 4. Fallbacks (placeholder, name)
    if (!label) {
      label = el.placeholder || el.name || el.id || '';
    }
    
    // Limpeza de asteriscos e tags de 'obrigatório'
    label = label.replace(/[\\*\\n\\r]/g, ' ').replace(/\\s+/g, ' ').replace(/(obrigat[oó]ri[ao]|required)/gi, '').trim();
    
    const tagName = el.tagName.toUpperCase();
    let type = 'text';
    if (tagName === 'SELECT') {
      type = 'select';
    } else if (tagName === 'TEXTAREA') {
      type = 'textarea';
    } else if (el.getAttribute('role') === 'combobox') {
      type = 'select';
    } else {
      type = el.type || 'text';
    }
    
    const currentValue = el.value || el.innerText || '';
    const f = {
      id: el.dataset.hermesId,
      type: type,
      label: label,
      name: el.name || '',
      current_value: currentValue.trim(),
      required: el.required || el.getAttribute('aria-required') === 'true'
    };
    
    if (type === 'select' && tagName === 'SELECT') {
      f.options = Array.from(el.options).map(o => (o.text || o.value || '').trim()).filter(Boolean);
    } else if (type === 'radio' || type === 'checkbox') {
      f.value = el.value || '';
      // Tenta achar o texto ao lado do radio/checkbox
      let optionText = '';
      const parentLabel = el.closest('label');
      if (parentLabel) {
        optionText = parentLabel.innerText.trim();
      } else if (el.nextElementSibling) {
        optionText = el.nextElementSibling.innerText.trim();
      }
      f.option_text = optionText || el.value;
      f.checked = el.checked;
    }
    
    out.push(f);
  });
  
  return out;
}
"""


def extract_fields(page: Page, container_selector: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extrai campos visíveis de um formulário ou modal, agrupando botões de rádio."""
    try:
        raw_fields = page.evaluate(EXTRACT_JS, container_selector)
    except Exception as e:
        print(f"[Form Extractor] Erro ao avaliar script: {e}")
        return []

    grouped_radios: Dict[str, Dict[str, Any]] = {}
    final_fields: List[Dict[str, Any]] = []

    for f in raw_fields:
        if f["type"] == "radio":
            group_key = f.get("name") or f.get("label") or "radio_group"
            if group_key not in grouped_radios:
                grouped_radios[group_key] = {
                    "id": f["id"],
                    "type": "radio",
                    "label": f.get("label") or group_key,
                    "name": f.get("name", ""),
                    "options": [],
                    "option_ids": {},
                    "required": f.get("required", False)
                }
            opt_label = f.get("option_text") or f.get("value") or f"Opção {len(grouped_radios[group_key]['options'])+1}"
            grouped_radios[group_key]["options"].append(opt_label)
            grouped_radios[group_key]["option_ids"][opt_label] = f["id"]
        else:
            final_fields.append(f)

    final_fields.extend(grouped_radios.values())
    return final_fields


def _fill(page: Page, field: Dict[str, Any], value: Any):
    """Preenche um campo específico com respeito a delays humanos e tipos de elemento."""
    if value is None:
        return
    
    sel = f"[data-hermes-id='{field['id']}']"
    t = field.get("type", "text")
    val_str = str(value).strip()

    try:
        loc = page.locator(sel).first
        if not loc.is_visible(timeout=1000):
            return

        if t == "select":
            # Tenta selecionar por label ou valor
            try:
                loc.select_option(label=val_str)
            except Exception:
                try:
                    loc.select_option(value=val_str)
                except Exception:
                    # Se for combobox ou custom select
                    loc.click()
                    human_pause(0.3, 0.6)
                    opt_loc = page.locator(f"option:has-text('{val_str}'), [role='option']:has-text('{val_str}')").first
                    if opt_loc.is_visible(timeout=1000):
                        opt_loc.click()

        elif t == "radio":
            option_ids = field.get("option_ids", {})
            # Procura a chave mais próxima
            target_id = None
            for opt_key, fid in option_ids.items():
                if val_str.lower() in opt_key.lower() or opt_key.lower() in val_str.lower():
                    target_id = fid
                    break
            
            if target_id:
                page.locator(f"[data-hermes-id='{target_id}']").first.check(force=True)
            elif option_ids:
                # Se não achou exato, pega a primeira opção compatível
                first_id = list(option_ids.values())[0]
                page.locator(f"[data-hermes-id='{first_id}']").first.check(force=True)

        elif t == "checkbox":
            if val_str.lower() in ("true", "sim", "yes", "1", "concordo", "aceito"):
                if not loc.is_checked():
                    loc.check(force=True)
            elif val_str.lower() in ("false", "não", "nao", "no", "0"):
                if loc.is_checked():
                    loc.uncheck(force=True)

        elif t in ("text", "textarea", "email", "tel", "number", "date"):
            # Se já tem valor e é o mesmo, não precisa reescrever
            curr = field.get("current_value", "")
            if curr and curr == val_str:
                return
            loc.click()
            loc.fill("")
            human_type(loc, val_str)

    except Exception as e:
        print(f"[Form Filler] Aviso ao preencher {field.get('label')}: {e}")

    human_pause(0.3, 0.8)
