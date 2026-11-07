"""
Configuração dinâmica - Hermes Job AI.
Lê chaves e modelos NO MOMENTO DO USO (não na importação), para que
alterações feitas pelo painel valham sem reiniciar o container.
Prioridade: data/runtime.env (volume persistente) > variáveis de ambiente.
"""

import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ENV = os.path.join(BASE_DIR, "data", "runtime.env")

DEFAULTS = {
    "GEMINI_MODEL_FAST": "gemini-3.5-flash-lite",
    "GEMINI_MODEL_SMART": "gemini-3.5-flash",
    "GEMINI_MODEL_FALLBACKS": "gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-flash-lite",
    "OLLAMA_HOST": "http://192.168.0.20:11434",
    "OLLAMA_MODEL": "qwen2.5:14b",
}


def _read_runtime() -> dict:
    values = {}
    if os.path.exists(RUNTIME_ENV):
        with open(RUNTIME_ENV, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
    return values


def get(name: str, default: Optional[str] = None) -> Optional[str]:
    runtime = _read_runtime()
    val = runtime.get(name) or os.getenv(name)
    if not val or val == "sua_chave_aqui":
        val = DEFAULTS.get(name, default) if name != "GEMINI_API_KEY" else None
    return val


def set_value(name: str, value: str) -> None:
    """Grava um valor em data/runtime.env (persistente entre reinícios)."""
    os.makedirs(os.path.dirname(RUNTIME_ENV), exist_ok=True)
    values = _read_runtime()
    values[name] = value
    with open(RUNTIME_ENV, "w", encoding="utf-8") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")
    try:
        os.chmod(RUNTIME_ENV, 0o600)
    except OSError:
        pass


def has_api_key() -> bool:
    return bool(get("GEMINI_API_KEY"))
