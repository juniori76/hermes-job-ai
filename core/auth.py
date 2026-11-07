"""
Módulo de Autenticação e Segurança - Hermes Job AI.
Gerenciamento de credenciais com hash PBKDF2-HMAC-SHA256 e tokens de sessão.
"""

import os
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
AUTH_FILE = os.path.join(DATA_DIR, "auth_users.json")

# Sessões ativas em memória: {token: {"username": str, "expires": datetime}}
ACTIVE_SESSIONS: Dict[str, Dict] = {}


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
    """Garante a existência do arquivo de autenticação com o usuário padrão."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(AUTH_FILE):
        # Usuário inicial padrão: eduardo / senha inicial: hermes2026
        default_user = {
            "eduardo": {
                "password_hash": hash_password("hermes2026"),
                "created_at": datetime.now().isoformat()
            }
        }
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(default_user, f, indent=2)


def authenticate_user(username: str, password_attempt: str) -> bool:
    """Valida se o usuário e senha são válidos."""
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        user_data = users.get(username.strip())
        if not user_data:
            return False
        return verify_password(user_data["password_hash"], password_attempt)
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao verificar credenciais: {e}")
        return False


def create_session(username: str, days: int = 14) -> str:
    """Cria um token aleatório criptograficamente seguro com validade."""
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS[token] = {
        "username": username,
        "expires": datetime.now() + timedelta(days=days)
    }
    return token


def validate_session(token: Optional[str]) -> Optional[str]:
    """Retorna o nome do usuário se o token for válido e não expirado."""
    if not token or token not in ACTIVE_SESSIONS:
        return None
    session = ACTIVE_SESSIONS[token]
    if datetime.now() > session["expires"]:
        del ACTIVE_SESSIONS[token]
        return None
    return session["username"]


def revoke_session(token: Optional[str]):
    """Encerra a sessão do usuário (Logout)."""
    if token and token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]


def change_user_password(username: str, new_password: str) -> bool:
    """Atualiza a senha do usuário com novo hash seguro."""
    init_auth()
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        if username not in users:
            return False
        users[username]["password_hash"] = hash_password(new_password)
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        return True
    except Exception as e:
        print(f"[Auth ⚠️] Erro ao alterar senha: {e}")
        return False
