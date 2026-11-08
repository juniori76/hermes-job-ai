"""
Motor de respostas inteligente - Hermes Job AI.
- Campos simples/escolha: LLM rápido com perfil e preferências
- Perguntas abertas/comportamentais: LLM estruturado com método STAR
Regra de ouro: nunca inventar experiência ou dados que não estejam no perfil real.
"""

import json
from typing import Any, Dict, List

from core import llm


def _is_open_question(field: Dict[str, Any]) -> bool:
    return field.get("type") == "textarea" or (
        field.get("type") == "text" and len(field.get("label", "")) > 60
    )


def answer_fields(fields: List[Dict[str, Any]], profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """Devolve {field_id: valor} e a chave "_skip_job" se a vaga for incompatível."""
    open_fields = [f for f in fields if _is_open_question(f)]
    simple_fields = [f for f in fields if f not in open_fields and f.get("type") != "file"]
    result: Dict[str, Any] = {}

    rules = (
        "Você é o assistente pessoal de candidatura do candidato. "
        "Responda estritamente em primeira pessoa, em português do Brasil (ou no idioma da vaga). "
        "Use APENAS fatos presentes no PERFIL. "
        "Para pretensão salarial, use a pretensão CLT ou PJ indicada no perfil (ex: 4500 ou 7000). "
        "Para disponibilidade, use 'Imediata' ou 'A combinar'. "
        "Para PCD (Pessoa com Deficiência), responda 'Não' salvo especificado no perfil. "
        "Se uma pergunta de múltipla escolha/select tiver opções, sua resposta DEVE ser EXATAMENTE uma das opções fornecidas. "
        "Nunca invente experiências, empresas ou certificações que não constem no perfil."
    )

    if simple_fields:
        prompt = f"""{rules}
PERFIL DO CANDIDATO:
{json.dumps(profile, ensure_ascii=False, indent=2)}

DADOS DA VAGA:
Cargo: {job.get('title')}
Empresa: {job.get('company')}
Local: {job.get('location')}

CAMPOS DO FORMULÁRIO A PREENCHER:
{json.dumps(simple_fields, ensure_ascii=False, indent=2)}

Devolva EXCLUSIVAMENTE um objeto JSON no formato:
{{
  "answers": {{
    "<field_id>": <valor|null>
  }},
  "skip_job": <true se o formulário exigir algo inaceitável para o candidato, caso contrário false>
}}"""
        try:
            data = llm.generate_json(prompt, temperature=0.1)
            result.update(data.get("answers", {}))
            result["_skip_job"] = bool(data.get("skip_job", False))
        except Exception as e:
            print(f"[Answer Engine] Erro ao responder campos simples: {e}")

    for f in open_fields:
        prompt = f"""{rules}
Responda de forma concisa, profissional e direta (máximo 800 caracteres).
Se for uma pergunta comportamental (ex: 'conte uma situação onde...'), use a estrutura STAR (Situação, Tarefa, Ação, Resultado) baseando-se no histórico real e competências do perfil do candidato.

PERFIL DO CANDIDATO:
{json.dumps(profile, ensure_ascii=False)}

VAGA: {job.get('title')} na {job.get('company')}
DESCRIÇÃO: {(job.get('description') or '')[:2500]}
PERGUNTA DO RECRUTADOR: {f.get('label')}

Devolva APENAS o texto puro da resposta, sem aspas adicionais nem introduções."""
        try:
            ans_text = llm.generate(prompt, smart=True, temperature=0.3)
            result[f["id"]] = (ans_text or "").strip()
        except Exception as e:
            print(f"[Answer Engine] Erro ao responder pergunta aberta: {e}")

    return result
