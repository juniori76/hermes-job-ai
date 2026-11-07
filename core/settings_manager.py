"""
Gerenciador de Configurações do Hermes Job AI.
Lê e escreve data/settings.json para controlar o modo de operação e o Telegram.
"""

import json
import os
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")

DEFAULTS: Dict[str, Any] = {
    "operation_mode": "review",   # review | smart | auto
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_enabled": False,
    "auto_apply_daily_limit": 10,  # candidaturas automáticas por dia (modo auto)
    "smart_score_threshold": 80,   # score mínimo para alertar no Telegram (modo smart/auto)
    "auto_score_threshold": 85,    # score mínimo para candidatura automática (modo auto)
    "notify_on_new_hot_job": True, # alertar vagas com menos de 6h (modos smart/auto)
}


def load_settings() -> Dict[str, Any]:
    """Carrega as configurações do arquivo settings.json, preenchendo defaults."""
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Preenche qualquer chave nova que não existia no arquivo salvo
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        print(f"[Settings] Erro ao carregar settings.json: {e}")
        return dict(DEFAULTS)


def save_settings(settings: Dict[str, Any]) -> bool:
    """Persiste as configurações no arquivo settings.json."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Settings] Erro ao salvar settings.json: {e}")
        return False


def get_operation_mode() -> str:
    """Retorna o modo de operação atual: 'review', 'smart' ou 'auto'."""
    return load_settings().get("operation_mode", "review")


def set_operation_mode(mode: str) -> bool:
    """Altera o modo de operação. Valida que seja um dos três modos válidos."""
    if mode not in ("review", "smart", "auto"):
        raise ValueError(f"Modo inválido: {mode}. Use 'review', 'smart' ou 'auto'.")
    s = load_settings()
    s["operation_mode"] = mode
    return save_settings(s)


def update_telegram_config(token: str, chat_id: str) -> bool:
    """Atualiza as credenciais do Telegram e ativa as notificações."""
    s = load_settings()
    s["telegram_bot_token"] = token.strip()
    s["telegram_chat_id"] = chat_id.strip()
    s["telegram_enabled"] = bool(token.strip() and chat_id.strip())
    return save_settings(s)


def get_telegram_config() -> Dict[str, Any]:
    """Retorna apenas os campos relevantes ao Telegram."""
    s = load_settings()
    return {
        "enabled": s.get("telegram_enabled", False),
        "token": s.get("telegram_bot_token", ""),
        "chat_id": s.get("telegram_chat_id", ""),
    }
