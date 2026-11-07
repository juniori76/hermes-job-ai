"""
Motor de respostas - Hermes Job AI.
- Campos simples/escolha: modelo rápido
- Perguntas abertas: modelo forte (método STAR)
Regra de ouro: nunca inventar experiência que não esteja no perfil.
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
        "Responda em primeira pessoa, no idioma da vaga. Use APENAS fatos presentes no perfil. "
        "Se não souber ou o perfil não cobrir, devolva null. Nunca invente experiências, "
        "certificações ou números."
    )

    if simple_fields:
        prompt = f"""{rules}
PERFIL: {json.dumps(profile, ensure_ascii=False)}
VAGA: {job.get('title')} - {job.get('company')} - {job.get('location')}
CAMPOS: {json.dumps(simple_fields, ensure_ascii=False)}
Para campos com 'options', devolva exatamente um dos textos de options.
Devolva JSON: {{"answers": {{"<id>": <valor|null>}}, "skip_job": <true se a vaga exige algo que o perfil recusa>}}"""
        data = llm.generate_json(prompt, temperature=0.1)
        result.update(data.get("answers", {}))
        result["_skip_job"] = bool(data.get("skip_job", False))

    for f in open_fields:
        prompt = f"""{rules}
Responda de forma concisa (máx. 900 caracteres), com estrutura STAR se for pergunta comportamental,
incluindo naturalmente as palavras-chave da vaga que o candidato realmente domina.
PERFIL: {json.dumps(profile, ensure_ascii=False)}
VAGA: {job.get('title')} - {job.get('company')}
DESCRIÇÃO: {(job.get('description') or '')[:2500]}
PERGUNTA: {f.get('label')}
Devolva apenas o texto da resposta."""
        result[f["id"]] = llm.generate(prompt, smart=True, temperature=0.5)

    return result
