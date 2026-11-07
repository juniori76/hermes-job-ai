"""
Módulo de Notificações via Telegram - Hermes Job AI.
Envia alertas no seu celular quando uma vaga excelente (Score >= 80%)
for encontrada ou quando uma candidatura for realizada.
"""

import os
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_alert(message: str) -> bool:
    """Envia uma mensagem de texto formatada para o seu Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        # Se não estiver configurado no .env, apenas pula silenciosamente
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram ⚠️] Erro ao enviar notificação: {e}")
        return False


def notify_high_score_job(job: Dict[str, Any]):
    """Alerta específico para vaga com alta afinidade."""
    score = job.get("match_score", 0)
    title = job.get("title", "Vaga")
    company = job.get("company", "Empresa")
    location = job.get("location", "Local não informado")
    url = job.get("job_url", "")
    reasons = job.get("match_reasons", "Sem detalhes adicionais")

    msg = (
        f"🎯 *NOVA OPORTUNIDADE DE OURO ENCONTRADA!*\n\n"
        f"💼 *Cargo:* {title}\n"
        f"🏢 *Empresa:* {company}\n"
        f"📍 *Local:* {location}\n"
        f"⭐ *Score ATS:* {score}%\n\n"
        f"🧠 *Por que combina com você:*\n_{reasons}_\n\n"
        f"🔗 [Acessar Vaga no Site]({url})\n"
        f"📱 [Abrir Painel Hermes](http://192.168.0.123:8088)"
    )
    send_telegram_alert(msg)


def notify_application_sent(job_title: str, company: str, status: str = "dry_run"):
    """Alerta de status de candidatura."""
    icon = "🧪 [SIMULAÇÃO DRY-RUN]" if status == "dry_run" else "✅ [ENVIADA COM SUCESSO]"
    msg = (
        f"{icon}\n\n"
        f"💼 *Vaga:* {job_title}\n"
        f"🏢 *Empresa:* {company}\n"
        f"Formulário preenchido e registrado no banco de dados."
    )
    send_telegram_alert(msg)
