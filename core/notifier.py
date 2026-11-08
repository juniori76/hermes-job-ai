"""
Módulo de Notificações via Telegram - Hermes Job AI.
Envia alertas no seu celular quando uma vaga excelente (Score >= 80%)
for encontrada ou quando uma candidatura for realizada.
Suporta botões inline para aprovar/rejeitar diretamente pelo chat.
"""

import requests
from typing import Dict, Any

from core.settings_manager import load_settings


def _get_config() -> Dict[str, Any]:
    """Lê configuração do Telegram do settings.json (atualizado em tempo real)."""
    s = load_settings()
    return {
        "enabled": s.get("telegram_enabled", False),
        "token": s.get("telegram_bot_token", ""),
        "chat_id": s.get("telegram_chat_id", ""),
    }


def send_telegram_message(message: str, reply_markup: dict = None) -> bool:
    """Envia uma mensagem de texto formatada (Markdown) para o seu Telegram."""
    cfg = _get_config()
    if not cfg["enabled"] or not cfg["token"] or not cfg["chat_id"]:
        print("[Telegram] Notificações não configuradas — pulando.")
        return False

    url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
    payload = {
        "chat_id": cfg["chat_id"],
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        print(f"[Telegram ⚠️] Erro HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[Telegram ⚠️] Exceção ao enviar: {e}")
        return False


# Alias de compatibilidade
send_telegram_alert = send_telegram_message



def notify_high_score_job(job: Dict[str, Any]) -> bool:
    """
    Roteia e notifica a vaga de alto score especificamente para o Telegram
    do membro da família correspondente aos cargos pretendidos.
    """
    try:
        from core.telegram_multi_router import notify_segmented_job
        return notify_segmented_job(job)
    except Exception as e:
        print(f"[Notifier ⚠️] Erro no roteador multi-perfil: {e}")
        return False

def notify_application_sent(job_title: str, company: str, job_url: str = "", status: str = "sent") -> bool:
    """Alerta de candidatura realizada (modo auto)."""
    if status == "dry_run":
        icon = "🧪 *[SIMULAÇÃO DRY-RUN]*"
        verb = "simulada"
    else:
        icon = "✅ *CANDIDATURA ENVIADA COM SUCESSO!*"
        verb = "realizada"

    msg = (
        f"{icon}\n\n"
        f"💼 *Vaga:* {job_title}\n"
        f"🏢 *Empresa:* {company}\n"
        f"📋 Candidatura {verb} e registrada no banco de dados."
    )
    if job_url:
        msg += f"\n🔗 [Ver vaga]({job_url})"

    return send_telegram_message(msg)


def notify_scan_summary(total_new: int, high_score_count: int, mode: str) -> bool:
    """Resumo do ciclo de varredura (enviado apenas se houver vagas relevantes)."""
    if total_new == 0:
        return False

    mode_labels = {"review": "🔵 Avaliação", "smart": "🟣 Inteligente", "auto": "🟢 Automático"}
    mode_label = mode_labels.get(mode, mode)

    msg = (
        f"📡 *HERMES — VARREDURA CONCLUÍDA*\n\n"
        f"🔍 Modo atual: {mode_label}\n"
        f"📥 Novas vagas encontradas: `{total_new}`\n"
        f"🎯 Com score alto (≥80%): `{high_score_count}`\n\n"
        f"📱 [Ver no Painel](http://192.168.0.123:8090)"
    )
    return send_telegram_message(msg)


def test_telegram_connection(token: str, chat_id: str) -> Dict[str, Any]:
    """
    Testa as credenciais do Telegram enviando uma mensagem de teste.
    Não usa settings.json — usa os parâmetros diretos para o teste.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": (
            "🤖 *Hermes Job AI — Conexão Testada!*\n\n"
            "✅ Telegram configurado com sucesso.\n"
            "Você receberá alertas de vagas com alto score aqui."
        ),
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return {"success": True, "message": "Mensagem de teste enviada com sucesso!"}
        err = resp.json().get("description", resp.text[:200])
        return {"success": False, "message": f"Erro Telegram: {err}"}
    except Exception as e:
        return {"success": False, "message": f"Falha de conexão: {e}"}
