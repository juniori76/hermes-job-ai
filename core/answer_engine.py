"""
Motor de respostas - Hermes Job AI.
Decide o valor de cada campo do formulário a partir do perfil real do candidato.
- Campos simples/escolha: modelo rápido (GEMINI_MODEL_FAST)
- Perguntas abertas: modelo mais forte (GEMINI_MODEL_SMART), método STAR
Regra de ouro: nunca inventar experiência que não esteja no perfil.
"""

import os
import json
from typing import Any, Dict, List
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

FAST_MODEL = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash")
SMART_MODEL = os.getenv("GEMINI_MODEL_SMART", "gemini-2.5-pro")


def _client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY não configurada.")
    return genai.Client(api_key=key)


def _is_open_question(field: Dict[str, Any]) -> bool:
    return field.get("type") == "textarea" or (
        field.get("type") == "text" and len(field.get("label", "")) > 60
    )


def answer_fields(fields: List[Dict[str, Any]], profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recebe os campos extraídos da página e devolve {field_id: valor}.
    Retorna também a chave "_skip_job" (bool) se a vaga for incompatível.
    """
    client = _client()
    open_fields = [f for f in fields if _is_open_question(f)]
    simple_fields = [f for f in fields if f not in open_fields and f.get("type") != "file"]
    result: Dict[str, Any] = {}

    base_rules = (
        "Responda em primeira pessoa, no idioma da vaga. Use APENAS fatos presentes no perfil. "
        "Se não souber ou o perfil não cobrir, devolva null. Nunca invente experiências, "
        "certificações ou números."
    )

    if simple_fields:
        prompt = f"""{base_rules}
PERFIL: {json.dumps(profile, ensure_ascii=False)}
VAGA: {job.get('title')} - {job.get('company')} - {job.get('location')}
CAMPOS: {json.dumps(simple_fields, ensure_ascii=False)}
Para campos com 'options', devolva exatamente um dos textos de options.
Devolva JSON: {{"answers": {{"<id>": <valor|null>}}, "skip_job": <true se a vaga exige algo que o perfil recusa>}}"""
        resp = client.models.generate_content(
            model=FAST_MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        data = json.loads(resp.text)
        result.update(data.get("answers", {}))
        result["_skip_job"] = bool(data.get("skip_job", False))

    for f in open_fields:
        prompt = f"""{base_rules}
Responda de forma concisa (máx. 900 caracteres), usando estrutura STAR quando for pergunta
comportamental, e inclua naturalmente as palavras-chave da vaga que o candidato realmente domina.
PERFIL: {json.dumps(profile, ensure_ascii=False)}
VAGA: {job.get('title')} - {job.get('company')}
DESCRIÇÃO: {(job.get('description') or '')[:2500]}
PERGUNTA: {f.get('label')}
Devolva apenas o texto da resposta."""
        resp = client.models.generate_content(
            model=SMART_MODEL, contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )
        result[f["id"]] = resp.text.strip()

    return result
