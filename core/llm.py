"""
Cliente Gemini compartilhado: timeout curto, retry e CADEIA DE FALLBACK de modelos.
Se um modelo estiver sobrecarregado (503/504), sem cota (429) ou indisponível (404),
passa automaticamente para o próximo da cadeia.
"""

import json
import time
from typing import Any, Dict, List

from google import genai
from google.genai import types

from core import config


class GeminiAuthError(Exception):
    """Chave inválida/ausente: não adianta tentar outros modelos."""


class GeminiUnavailable(Exception):
    """Nenhum modelo da cadeia respondeu."""


def get_client() -> genai.Client:
    key = config.get("GEMINI_API_KEY")
    if not key:
        raise GeminiAuthError("GEMINI_API_KEY não configurada.")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=45_000))


def model_chain(smart: bool = False) -> List[str]:
    primary = config.get("GEMINI_MODEL_SMART" if smart else "GEMINI_MODEL_FAST")
    chain = [primary] + [m.strip() for m in config.get("GEMINI_MODEL_FALLBACKS", "").split(",") if m.strip()]
    seen, out = set(), []
    for m in chain:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def generate(prompt: str, smart: bool = False, json_mode: bool = False,
             temperature: float = 0.2) -> str:
    client = get_client()
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    )
    errors = []
    for model in model_chain(smart):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
            if resp.text:
                return resp.text.strip()
            errors.append(f"{model}: resposta vazia")
        except Exception as e:
            msg = str(e)
            if "API_KEY_INVALID" in msg or "API key not valid" in msg:
                raise GeminiAuthError(f"Chave rejeitada pelo Gemini: {msg[:120]}")
            errors.append(f"{model}: {msg[:70]}")
            time.sleep(1)
    raise GeminiUnavailable("Nenhum modelo respondeu -> " + " | ".join(errors))


def generate_json(prompt: str, smart: bool = False, temperature: float = 0.2) -> Dict[str, Any]:
    return json.loads(generate(prompt, smart=smart, json_mode=True, temperature=temperature))
