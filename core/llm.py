"""
Cliente Híbrido: Suporta MÚLTIPLAS CHAVES GEMINI + OLLAMA LOCAL (RTX 3090).
Alterna automaticamente entre a Chave 1 (Eduardo), Chave 2 (Soffia) e Ollama local.
Se um provedor falhar ou esgotar cota (429), tenta o próximo sem parar o robô.
"""

import json
import time
import requests
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

from core import config


def get_gemini_keys() -> List[str]:
    """Retorna lista de chaves Gemini cadastradas (primária + backups)."""
    keys = []
    k1 = config.get("GEMINI_API_KEY")
    k2 = config.get("GEMINI_API_KEY_BACKUP")
    k3 = config.get("GEMINI_API_KEY_BACKUP2")
    for k in (k1, k2, k3):
        if k and k.strip() and k.strip() not in keys:
            keys.append(k.strip())
    return keys


def query_ollama(prompt: str, model: str = "qwen2.5:14b", json_mode: bool = False, timeout: int = 40) -> Optional[str]:
    """Tenta consultar o Ollama local (RTX 3090) se estiver acessível."""
    host = config.get("OLLAMA_HOST", "http://192.168.0.20:11434")
    url = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json" if json_mode else ""
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception:
        pass
    return None


def generate(prompt: str, smart: bool = False, json_mode: bool = False, temperature: float = 0.2) -> str:
    """Gera texto usando a cadeia de resiliência: Chaves Gemini -> Ollama RTX 3090."""
    gemini_keys = get_gemini_keys()
    models = [config.get("GEMINI_MODEL_FAST", "gemini-3.5-flash-lite")] + [
        m.strip() for m in config.get("GEMINI_MODEL_FALLBACKS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-flash-lite").split(",") if m.strip()
    ]

    # 1. Tenta nas chaves do Gemini
    for key_idx, key in enumerate(gemini_keys):
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=35_000))
        for model in models:
            try:
                cfg = types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json" if json_mode else None
                )
                resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    print(f"[LLM] Cota esgotada na Chave {key_idx+1} para {model}. Alternando...")
                    break # Pula para a próxima chave
                time.sleep(1)

    # 2. Se as APIs do Gemini falharem, usa a RTX 3090 local (Ollama)
    ollama_model = config.get("OLLAMA_MODEL", "qwen2.5:14b")
    print(f"[LLM 🔄] Alternando para motor local RTX 3090 (Ollama: {ollama_model})...")
    ollama_resp = query_ollama(prompt, model=ollama_model, json_mode=json_mode)
    if ollama_resp:
        return ollama_resp

    raise RuntimeError("Todos os provedores falharam (Chaves Gemini 1 e 2 esgotadas e Ollama indisponível).")


def generate_json(prompt: str, smart: bool = False, temperature: float = 0.2) -> Dict[str, Any]:
    raw = generate(prompt, smart=smart, json_mode=True, temperature=temperature)
    # Garante parsing de JSON limpo mesmo se a LLM mandar marcação markdown
    clean = raw.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return json.loads(clean.strip())
