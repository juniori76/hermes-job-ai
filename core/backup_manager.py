"""
Gerenciador de Backup Automático e Integridade - Hermes Job AI 2.0.
Cria snapshots compactados do banco SQLite (hermes.db), configurações e perfis.
Mantém rotação das últimas 10 versões para economia de disco.
"""

import os
import zipfile
import datetime
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")


def create_backup() -> Dict[str, Any]:
    """Cria um snapshot compactado ZIP do banco de dados e perfis."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"hermes_backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUPS_DIR, backup_filename)

    files_to_backup = [
        os.path.join(DATA_DIR, "hermes.db"),
        os.path.join(CONFIG_DIR, "settings.json"),
        os.path.join(DATA_DIR, "telegram_bindings.json"),
        os.path.join(DATA_DIR, "auth_users.json"),
    ]

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # 1. Arquivos centrais
            for file_path in files_to_backup:
                if os.path.exists(file_path):
                    arcname = os.path.relpath(file_path, BASE_DIR)
                    zipf.write(file_path, arcname=arcname)

            # 2. Pasta inteira de perfis config/profiles/
            profiles_dir = os.path.join(CONFIG_DIR, "profiles")
            if os.path.exists(profiles_dir):
                for root, _, files in os.walk(profiles_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        arcname = os.path.relpath(p, BASE_DIR)
                        zipf.write(p, arcname=arcname)

            # 3. Currículos em data/profiles/
            cv_profiles_dir = os.path.join(DATA_DIR, "profiles")
            if os.path.exists(cv_profiles_dir):
                for root, _, files in os.walk(cv_profiles_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        arcname = os.path.relpath(p, BASE_DIR)
                        zipf.write(p, arcname=arcname)

        size_kb = round(os.path.getsize(backup_path) / 1024, 1)

        # Rotação: manter apenas os 10 backups mais recentes
        _rotate_backups(keep=10)

        return {
            "success": True,
            "filename": backup_filename,
            "size_kb": size_kb,
            "path": backup_path,
            "timestamp": timestamp
        }
    except Exception as e:
        return {"success": False, "error": f"Erro ao gerar backup: {e}"}


def list_backups() -> List[Dict[str, Any]]:
    """Lista todos os backups salvos em data/backups/."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    backups = []
    for f in os.listdir(BACKUPS_DIR):
        if f.startswith("hermes_backup_") and f.endswith(".zip"):
            p = os.path.join(BACKUPS_DIR, f)
            size_kb = round(os.path.getsize(p) / 1024, 1)
            mtime = os.path.getmtime(p)
            dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M:%S")
            backups.append({
                "filename": f,
                "size_kb": size_kb,
                "created_at": dt_str,
                "mtime": mtime
            })
    backups.sort(key=lambda x: x["mtime"], reverse=True)
    return backups


def _rotate_backups(keep: int = 10):
    """Apaga os backups mais antigos excedentes."""
    backups = list_backups()
    if len(backups) > keep:
        for b in backups[keep:]:
            try:
                os.remove(os.path.join(BACKUPS_DIR, b["filename"]))
            except Exception:
                pass
