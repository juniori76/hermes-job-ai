"""
Cliente Gemini compartilhado: timeout, retry e classificação de erros.
"""

import json
import time
from typing import Any, Dict, Optional
from google import genai
from google.genai import types

from core import config


class GeminiAuthError(Exception):
    """Chave inválida ou modelo indisponível: não adianta tentar de novo."""


def get_client() -> genai.Client:
    key = config.get("GEMINI_API_KEY")
    if not key:
        raise GeminiAuthError("GEMINI_API_KEY não configurada.")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=90_000))


def generate(prompt: str, smart: bool = False, json_mode: bool = False,
             temperature: float = 0.2, retries: int = 3) -> str:
    model = config.get("GEMINI_MODEL_SMART" if smart else "GEMINI_MODEL_FAST")
    client = get_client()
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    )
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
            return resp.text.strip()
        except Exception as e:
            msg = str(e)
            if any(t in msg for t in ("API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED", "401", "403")):
                raise GeminiAuthError(f"Chave rejeitada pelo Gemini: {msg[:120]}")
            if "404" in msg or "NOT_FOUND" in msg:
                raise GeminiAuthError(f"Modelo '{model}' indisponível: {msg[:120]}")
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Falha após {retries} tentativas: {str(last)[:150]}")


def generate_json(prompt: str, smart: bool = False, temperature: float = 0.2) -> Dict[str, Any]:
    return json.loads(generate(prompt, smart=smart, json_mode=True, temperature=temperature))
