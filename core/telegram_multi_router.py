"""
Roteador Multi-Perfil do Telegram - Hermes Job AI.
Gerencia a vinculação de múltiplos usuários/candidatos cadastrados
a seus respectivos Telegram Chat IDs, roteia vagas com base nos cargos pretendidos
de cada um e processa comandos interativos via Long-Polling (/start, /vincular, /vagas, /status).
"""

import os
import json
import time
import threading
import requests
import sqlite3
from typing import Dict, Any, Optional, List

from core.settings_manager import load_settings
from core.profiles_manager import list_profiles, get_profile
from core.auth import list_users

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BINDINGS_FILE = os.path.join(DATA_DIR, "telegram_bindings.json")
DB_PATH = os.path.join(DATA_DIR, "hermes.db")

_polling_thread_started = False


def _get_bindings_data() -> Dict[str, Any]:
    """Lê os vínculos salvos no arquivo JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(BINDINGS_FILE):
        default_data = {
            "chat_to_user": {},
            "user_to_chat": {}
        }
        with open(BINDINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)
        return default_data

    try:
        with open(BINDINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"chat_to_user": {}, "user_to_chat": {}}


def _save_bindings_data(data: Dict[str, Any]):
    """Salva os vínculos no arquivo JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BINDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def bind_user_telegram(chat_id: str, username: str) -> bool:
    """Vincula um Telegram Chat ID a um nome de usuário do Hermes."""
    username = username.strip().lower()
    chat_id = str(chat_id).strip()
    
    users = list_users()
    if username not in users:
        return False
        
    data = _get_bindings_data()
    data["chat_to_user"][chat_id] = username
    data["user_to_chat"][username] = chat_id
    _save_bindings_data(data)
    print(f"[TelegramRouter ✅] Chat ID {chat_id} vinculado ao perfil @{username}")
    return True


def get_user_by_chat_id(chat_id: str) -> Optional[str]:
    """Retorna o nome do usuário associado a este Chat ID."""
    data = _get_bindings_data()
    return data.get("chat_to_user", {}).get(str(chat_id))


def get_chat_id_by_user(username: str) -> Optional[str]:
    """Retorna o Chat ID associado a um nome de usuário."""
    data = _get_bindings_data()
    return data.get("user_to_chat", {}).get(str(username).lower())


def list_all_bindings() -> Dict[str, str]:
    """Retorna dicionário {username: chat_id} de todos os membros vinculados."""
    data = _get_bindings_data()
    return data.get("user_to_chat", {})


def route_job_to_user(job: Dict[str, Any], profiles: Optional[List[Dict]] = None) -> str:
    """
    Analisa o título e a descrição da vaga e determina qual usuário/candidato
    tem o perfil com maior afinidade para esta oportunidade.
    """
    if profiles is None:
        profiles = list_profiles()
    if not profiles:
        return "eduardo"

    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    keywords = (job.get("keywords_found") or "").lower()
    full_text = f"{title} {keywords} {desc}"

    best_user = "eduardo"
    best_score = 0

    for p in profiles:
        u_id = p["id"]
        cargos = p.get("cargos_alvo") or p.get("target_roles") or []
        score = 0
        for cargo in cargos:
            cargo_lower = cargo.lower().strip()
            if not cargo_lower:
                continue
            # Match exato no título
            if cargo_lower in title:
                score += 30
            # Palavras individuais SIGNIFICATIVAS do cargo no título (ignora prefixos genéricos como 'analista', 'assistente')
            from core.relevance_filter import GENERIC_TITLE_PREFIXES
            for part in cargo_lower.split():
                if len(part) > 3 and part not in GENERIC_TITLE_PREFIXES:
                    if part in title:
                        score += 10
                    elif part in full_text:
                        score += 2

        if score > best_score:
            best_score = score
            best_user = u_id

    # Se não pontuou com nenhum cargo específico, verifica termos-chave do tipo de função
    if best_score == 0:
        admin_keywords = ["administrativo", "administrativa", "atendimento", "recepcionista", "auxiliar de escritório", "secretaria", "financeiro", "contas a pagar"]
        if any(ak in title for ak in admin_keywords):
            for p in profiles:
                if p["id"] in ["rute", "vine"]:
                    return p["id"]
        ti_keywords = ["suporte", "redes", "infraestrutura", "windows server", "linux", "analista de ti", "helpdesk", "field service", "mikrotik", "cisco"]
        if any(tk in title for tk in ti_keywords):
            return "eduardo"
        return "eduardo"

    return best_user


def send_message_to_chat(token: str, chat_id: str, message: str, reply_markup: dict = None) -> bool:
    """Envia mensagem para um Chat ID específico no Telegram."""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[TelegramRouter ⚠️] Erro ao enviar mensagem para {chat_id}: {e}")
        return False


def notify_segmented_job(job: Dict[str, Any]) -> bool:
    """
    Envia a vaga especificamente para o Telegram do membro da casa cujo perfil combina com a vaga.
    Se o membro ainda não vinculou seu Telegram, envia para o chat_id mestre com indicação.
    """
    settings = load_settings()
    if not settings.get("telegram_enabled", False):
        return False
    token = settings.get("telegram_bot_token", "")
    if not token:
        return False

    target_user = route_job_to_user(job)
    profile = get_profile(target_user)
    display_name = profile.get("candidato", {}).get("nome_completo") or target_user.capitalize()

    target_chat_id = get_chat_id_by_user(target_user)
    is_fallback = False
    if not target_chat_id:
        # Fallback para o chat principal configurado
        target_chat_id = settings.get("telegram_chat_id", "")
        is_fallback = True

    if not target_chat_id:
        return False

    score = job.get("match_score", 0)
    title = job.get("title", "Vaga")
    company = job.get("company", "Empresa")
    location = job.get("location", "Local não informado")
    job_url = job.get("job_url", "")
    job_id = job.get("id", "")
    reasons = job.get("match_reasons", "Compatibilidade com perfil profissional.")
    
    header_line = f"🎯 *OPORTUNIDADE PARA VOCÊ, {display_name.upper()}!*"
    if is_fallback:
        header_line = f"🎯 *OPORTUNIDADE PARA @{target_user} ({display_name})*"

    msg = (
        f"{header_line}\n\n"
        f"💼 *Cargo:* {title}\n"
        f"🏢 *Empresa:* {company}\n"
        f"📍 *Local:* {location}\n"
        f"⭐ *Score ATS:* `{score}%`\n\n"
        f"🧠 *Diagnóstico da IA:*\n_{reasons}_\n\n"
        f"🔗 [Abrir Vaga no Navegador]({job_url})\n"
        f"📱 [Acessar Hermes no Celular](http://192.168.0.123:8090)"
    )

    reply_markup = None
    if job_id:
        panel_base = "http://192.168.0.123:8090"
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "↗️ Abrir Vaga", "url": job_url},
                    {"text": "✅ Já Me Candidatei", "url": f"{panel_base}/api/jobs/{job_id}/approve_redirect"}
                ],
                [
                    {"text": "❌ Descartar Vaga", "url": f"{panel_base}/api/jobs/{job_id}/reject_redirect"}
                ]
            ]
        }

    return send_message_to_chat(token, target_chat_id, msg, reply_markup=reply_markup)


def get_top_jobs_for_user(username: str, limit: int = 4) -> List[Dict[str, Any]]:
    """Busca as melhores vagas no banco SQLite mais aderentes ao perfil deste usuário."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        profile = get_profile(username)
        cargos = profile.get("cargos_alvo", [])
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Busca vagas aprovadas ou com score >= 75
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE status IN ('discovered', 'reviewed', 'approve', 'approved')
              AND match_score IS NOT NULL
            ORDER BY match_score DESC, created_at DESC 
            LIMIT 30;
        """)
        all_jobs = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Filtra ou pontua as vagas para este usuário
        matched = []
        for j in all_jobs:
            if route_job_to_user(j) == username or not cargos:
                matched.append(j)
            if len(matched) >= limit:
                break

        return matched if matched else all_jobs[:limit]
    except Exception as e:
        print(f"[TelegramRouter ⚠️] Erro ao buscar vagas para {username}: {e}")
        return []


def handle_telegram_command(token: str, chat_id: str, text: str, user_name: str = ""):
    """Processa mensagens recebidas pelo bot via Telegram."""
    text = text.strip()
    cmd = text.split()[0].lower() if text else ""
    args = text.split()[1:] if len(text.split()) > 1 else []

    linked_user = get_user_by_chat_id(chat_id)

    # 1. COMANDO /START OU /AJUDA
    if cmd in ["/start", "/ajuda", "/help"]:
        users_list = list(list_users().keys())
        users_str = ", ".join([f"`{u}`" for u in users_list])

        if linked_user:
            profile = get_profile(linked_user)
            name = profile.get("candidato", {}).get("nome_completo") or linked_user.capitalize()
            reply = (
                f"👋 *Olá, {name}!*\n\n"
                f"Seu Telegram já está conectado ao perfil *@ {linked_user}* no Hermes Job AI.\n\n"
                f"📌 *Comandos disponíveis:*\n"
                f"• `/vagas` — Ver as melhores vagas abertas para você hoje\n"
                f"• `/status` — Status do radar e do seu perfil\n"
                f"• `/desvincular` — Desconectar este Telegram da sua conta\n\n"
                f"Sempre que surgir uma vaga excelente com score alto, eu te aviso aqui na hora! 🚀"
            )
        else:
            reply = (
                f"🤖 *Olá! Eu sou o Hermes Job AI!*\n\n"
                f"Para receber as vagas certas para a sua área no seu celular, vincule seu login:\n\n"
                f"👉 Digite: `/vincular seu_usuario`\n"
                f"Exemplo: `/vincular eduardo` ou `/vincular gabriel`\n\n"
                f"👥 *Perfis cadastrados:* {users_str}\n\n"
                f"Depois de vincular, você receberá apenas as vagas que interessam para você!"
            )
        send_message_to_chat(token, chat_id, reply)

    # 2. COMANDO /VINCULAR <USUARIO>
    elif cmd == "/vincular":
        if not args:
            send_message_to_chat(
                token, chat_id,
                "⚠️ *Por favor, informe seu usuário de login.*\nExemplo: `/vincular eduardo` ou `/vincular seu_usuario`"
            )
            return

        target_u = args[0].strip().lower()
        success = bind_user_telegram(chat_id, target_u)
        if success:
            profile = get_profile(target_u)
            name = profile.get("candidato", {}).get("nome_completo") or target_u.capitalize()
            cargos_str = ", ".join(profile.get("cargos_alvo", ["Área Geral"]))
            reply = (
                f"✅ *CONEXÃO REALIZADA COM SUCESSO!*\n\n"
                f"👤 *Perfil:* {name} (`@{target_u}`)\n"
                f"🎯 *Cargos de Interesse:* {cargos_str}\n\n"
                f"A partir de agora, quando surgirem vagas novas para a sua carreira, "
                f"eu vou apitar diretamente aqui no seu celular!\n\n"
                f"👉 Digite `/vagas` para ver as oportunidades atuais."
            )
        else:
            send_message_to_chat(
                token, chat_id,
                f"❌ *Usuário '{target_u}' não encontrado.*\n"
                f"Verifique se o login foi criado no painel Web em 'Gestão de Usuários & Perfis'."
            )
            return
        send_message_to_chat(token, chat_id, reply)

    # 3. COMANDO /DESVINCULAR
    elif cmd == "/desvincular":
        data = _get_bindings_data()
        if str(chat_id) in data.get("chat_to_user", {}):
            u = data["chat_to_user"][str(chat_id)]
            del data["chat_to_user"][str(chat_id)]
            if u in data.get("user_to_chat", {}):
                del data["user_to_chat"][u]
            _save_bindings_data(data)
            send_message_to_chat(token, chat_id, "🔌 *Telegram desvinculado com sucesso.*")
        else:
            send_message_to_chat(token, chat_id, "ℹ️ Este Telegram não estava vinculado a nenhum perfil.")

    # 4. COMANDO /VAGAS
    elif cmd == "/vagas":
        if not linked_user:
            send_message_to_chat(
                token, chat_id,
                "⚠️ *Você ainda não vinculou seu perfil.*\nDigite `/vincular seu_usuario` primeiro!"
            )
            return

        profile = get_profile(linked_user)
        name = profile.get("candidato", {}).get("nome_completo") or linked_user.capitalize()
        jobs = get_top_jobs_for_user(linked_user, limit=3)

        if not jobs:
            send_message_to_chat(
                token, chat_id,
                f"📡 *Nenhuma vaga pendente no radar para você no momento, {name}.*\n"
                f"O robô 24/7 está varrendo o LinkedIn, Gupy e Indeed e avisará assim que encontrar novas!"
            )
            return

        send_message_to_chat(
            token, chat_id,
            f"💼 *TOP OPORTUNIDADES PARA {name.upper()}:*"
        )

        panel_base = "http://192.168.0.123:8090"
        for j in jobs:
            j_id = j.get("id")
            j_url = j.get("job_url", "")
            title = j.get("title")
            company = j.get("company")
            score = j.get("match_score", 0)
            loc = j.get("location")
            reasons = j.get("match_reasons") or "Alta aderência aos seus requisitos."

            msg = (
                f"⭐ *Score ATS: {score}%* | `{j.get('site', 'Vaga').upper()}`\n"
                f"💼 *{title}*\n"
                f"🏢 {company} • 📍 {loc}\n"
                f"💡 _{reasons}_\n"
            )
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "↗️ Abrir Vaga", "url": j_url},
                        {"text": "✅ Já Candidatei", "url": f"{panel_base}/api/jobs/{j_id}/approve_redirect"}
                    ]
                ]
            }
            send_message_to_chat(token, chat_id, msg, reply_markup=markup)
            time.sleep(0.3)

    # 5. COMANDO /STATUS
    elif cmd == "/status":
        settings = load_settings()
        mode_label = {"review": "🔵 Avaliação", "smart": "🟣 Inteligente", "auto": "🟢 Automático"}.get(
            settings.get("operation_mode"), "🔵 Avaliação"
        )
        bindings = list_all_bindings()
        bindings_str = "\n".join([f"• `@{u}`: Chat ID {cid}" for u, cid in bindings.items()]) or "Nenhum vinculado."

        reply = (
            f"🤖 *STATUS DO HERMES JOB AI*\n\n"
            f"⚙️ *Modo de Operação:* {mode_label}\n"
            f"🌐 *Servidor:* Linux `192.168.0.123:8090`\n"
            f"👤 *Seu Usuário:* `@{linked_user or 'Não vinculado'}`\n\n"
            f"👥 *Membros Conectados no Telegram:*\n{bindings_str}\n\n"
            f"📱 [Abrir Painel no Celular](http://192.168.0.123:8090)"
        )
        send_message_to_chat(token, chat_id, reply)

    # RESPOSTA PADRÃO PARA TEXTO LIVRE
    else:
        send_message_to_chat(
            token, chat_id,
            "🤖 *Comando não reconhecido.*\nDigite `/vagas` para ver suas oportunidades ou `/ajuda` para ver os comandos."
        )


def _telegram_polling_worker():
    """Worker de segundo plano que escuta mensagens do Telegram usando Long-Polling nativo."""
    last_update_id = 0
    print("[TelegramRouter] 📡 Listener de mensagens do Telegram iniciado.")
    
    while True:
        try:
            settings = load_settings()
            if not settings.get("telegram_enabled", False):
                time.sleep(15)
                continue
                
            token = settings.get("telegram_bot_token", "").strip()
            if not token:
                time.sleep(15)
                continue

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {
                "offset": last_update_id + 1,
                "timeout": 20
            }
            
            resp = requests.get(url, params=params, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    msg = update.get("message")
                    if not msg:
                        continue
                    chat_id = str(msg.get("chat", {}).get("id"))
                    text = msg.get("text", "")
                    from_user = msg.get("from", {}).get("first_name", "")
                    
                    if text:
                        handle_telegram_command(token, chat_id, text, user_name=from_user)
            elif resp.status_code == 401 or resp.status_code == 404:
                # Token inválido ou não configurado
                time.sleep(30)
            else:
                time.sleep(5)
                
        except Exception as e:
            time.sleep(10)


def start_telegram_listener():
    """Inicia a thread de escuta do Telegram se ainda não estiver ativa."""
    global _polling_thread_started
    if not _polling_thread_started:
        _polling_thread_started = True
        t = threading.Thread(target=_telegram_polling_worker, daemon=True, name="TelegramListenerThread")
        t.start()
        print("[TelegramRouter ✅] Thread de Long-Polling do Telegram ativada com sucesso.")
