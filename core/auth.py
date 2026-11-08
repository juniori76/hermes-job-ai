"""
Módulo de Autenticação e Segurança - Hermes Job AI.
Gerenciamento de credenciais com hash PBKDF2-HMAC-SHA256 e tokens de sessão persistentes.
"""

import os
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
AUTH_FILE = os.path.join(DATA_DIR, "auth_users.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

# Cache de sessões em memória
ACTIVE_SESSIONS: Dict[str, Dict] = {}


def _load_persisted_sessions():
    """Carrega sessões salvas em disco para a memória."""
    global ACTIVE_SESSIONS
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            now = datetime.now()
            valid_sessions = {}
            for token, sess in raw_data.items():
                try:
                    exp = datetime.fromisoformat(sess["expires"])
                    if exp > now:
                        valid_sessions[token] = {
                            "username": sess["username"],
                            "expires": exp
                        }
                except Exception:
                    pass
            ACTIVE_SESSIONS = valid_sessions
        except Exception as e:
            print(f"[Auth ⚠️] Erro ao carregar sessões de disco: {e}")


def _save_persisted_sessions():
    """Grava as sessões ativas em disco para sobreviver a reinicializações de contêiner."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        now = datetime.now()
        serializable = {}
        for token, sess in ACTIVE_SESSIONS.items():
            if sess["expires"] > now:
                serializable[token] = {
                    "username": sess["username"],
                    "expires": sess["expires"].isoformat()
                }
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao salvar sessões em disco: {e}")


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Gera o hash da senha usando salt de 32 bytes e PBKDF2."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${hashed}"


def verify_password(stored_hash: str, password_attempt: str) -> bool:
    """Verifica se a tentativa de senha confere com o hash armazenado."""
    try:
        salt, _ = stored_hash.split('$', 1)
        attempt_hash = hash_password(password_attempt, salt)
        return secrets.compare_digest(stored_hash, attempt_hash)
    except Exception:
        return False


def init_auth():
    """Garante a existência do arquivo de autenticação com o usuário padrão e carrega sessões."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(AUTH_FILE):
        default_user = {
            "eduardo": {
                "password_hash": hash_password("hermes2026"),
                "display_name": "Eduardo O. S. Junior",
                "created_at": datetime.now().isoformat()
            }
        }
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(default_user, f, indent=2)
    _load_persisted_sessions()


def authenticate_user(username: str, password_attempt: str) -> bool:
    """Valida se o usuário e senha são válidos."""
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        user_data = users.get(username.strip().lower())
        if not user_data:
            return False
        return verify_password(user_data["password_hash"], password_attempt)
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao verificar credenciais: {e}")
        return False


def create_session(username: str, days: int = 30) -> str:
    """Cria um token aleatório e persiste em disco por 30 dias."""
    init_auth()
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS[token] = {
        "username": username.strip().lower(),
        "expires": datetime.now() + timedelta(days=days)
    }
    _save_persisted_sessions()
    return token


def validate_session(token: Optional[str]) -> Optional[str]:
    """Retorna o nome do usuário se o token for válido e não expirado (lendo de memória ou disco)."""
    if not token:
        return None
        
    if not ACTIVE_SESSIONS:
        _load_persisted_sessions()

    if token not in ACTIVE_SESSIONS:
        # Tenta recarregar de disco uma vez caso tenha sido criado em outro processo
        _load_persisted_sessions()
        
    if token not in ACTIVE_SESSIONS:
        return None
        
    session = ACTIVE_SESSIONS[token]
    if datetime.now() > session["expires"]:
        del ACTIVE_SESSIONS[token]
        _save_persisted_sessions()
        return None
        
    return session["username"]


def revoke_session(token: Optional[str]):
    """Encerra a sessão do usuário (Logout)."""
    if token and token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
        _save_persisted_sessions()


def change_user_password(username: str, new_password: str) -> bool:
    """Atualiza a senha do usuário com novo hash seguro."""
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        u = username.strip().lower()
        if u not in users:
            return False
        users[u]["password_hash"] = hash_password(new_password)
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        return True
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao alterar senha: {e}")
        return False


def create_user(username: str, password: str, display_name: str = "") -> bool:
    """Cria um novo usuário e hash de senha no sistema."""
    init_auth()
    try:
        username = username.strip().lower()
        if not username or not password:
            return False
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        users[username] = {
            "password_hash": hash_password(password),
            "display_name": display_name or username.capitalize(),
            "created_at": datetime.now().isoformat()
        }
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        return True
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao criar usuário: {e}")
        return False


def list_users() -> Dict[str, Any]:
    """Retorna todos os usuários cadastrados."""
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        return {
            u: {
                "display_name": data.get("display_name", u.capitalize()),
                "created_at": data.get("created_at", "")
            }
            for u, data in users.items()
        }
    except Exception:
        return {}


def delete_user(username: str) -> bool:
    """Remove um usuário adicional do sistema."""
    if username.lower() == "eduardo":
        return False
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        if username in users:
            del users[username]
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)
            return True
        return False
    except Exception:
        return False
