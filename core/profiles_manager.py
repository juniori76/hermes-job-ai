"""
Gerenciador Multi-Perfil do Hermes Job AI.
Permite alternar entre diferentes perfis de candidatos,
cada um com suas preferências de busca, cargos-alvo, regras e currículo em PDF.
"""

import os
import shutil
import yaml
from typing import Dict, Any, List, Optional
import pypdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
PROFILES_CONFIG_DIR = os.path.join(CONFIG_DIR, "profiles")
DATA_DIR = os.path.join(BASE_DIR, "data")
PROFILES_DATA_DIR = os.path.join(DATA_DIR, "profiles")


def init_profiles():
    """Garante que a estrutura multi-perfil exista, migrando o perfil inicial padrão se necessário."""
    os.makedirs(PROFILES_CONFIG_DIR, exist_ok=True)
    os.makedirs(PROFILES_DATA_DIR, exist_ok=True)
    
    # Perfil padrão Eduardo
    eduardo_cfg = os.path.join(PROFILES_CONFIG_DIR, "eduardo")
    os.makedirs(eduardo_cfg, exist_ok=True)
    eduardo_yaml = os.path.join(eduardo_cfg, "candidate_profile.yaml")
    
    root_yaml = os.path.join(CONFIG_DIR, "candidate_profile.yaml")
    if not os.path.exists(eduardo_yaml) and os.path.exists(root_yaml):
        shutil.copy2(root_yaml, eduardo_yaml)
        
    eduardo_data = os.path.join(PROFILES_DATA_DIR, "eduardo")
    os.makedirs(eduardo_data, exist_ok=True)
    eduardo_pdf = os.path.join(eduardo_data, "curriculo.pdf")
    root_pdf = os.path.join(DATA_DIR, "curriculo.pdf")
    if not os.path.exists(eduardo_pdf) and os.path.exists(root_pdf):
        shutil.copy2(root_pdf, eduardo_pdf)


def list_profiles() -> List[Dict[str, Any]]:
    """Lista todos os perfis cadastrados no sistema."""
    init_profiles()
    profiles = []
    
    for name in sorted(os.listdir(PROFILES_CONFIG_DIR)):
        p_dir = os.path.join(PROFILES_CONFIG_DIR, name)
        cfg_file = os.path.join(p_dir, "candidate_profile.yaml")
        if os.path.isdir(p_dir) and os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                cand = data.get("candidato", {})
                display_name = cand.get("nome_completo") or name.capitalize()
                cargos = data.get("preferencias_de_vaga", {}).get("cargos_alvo", [])
                
                resume_exists = os.path.exists(os.path.join(PROFILES_DATA_DIR, name, "curriculo.pdf"))
                
                profiles.append({
                    "id": name,
                    "name": display_name,
                    "display_name": display_name,
                    "cargos_alvo": cargos,
                    "target_roles": cargos,
                    "has_resume": resume_exists
                })
            except Exception:
                profiles.append({
                    "id": name,
                    "name": name.capitalize(),
                    "display_name": name.capitalize(),
                    "cargos_alvo": [],
                    "target_roles": [],
                    "has_resume": False
                })
                
    return profiles


def get_profile(username: str = "eduardo") -> Dict[str, Any]:
    """Retorna os dados de configuração YAML do perfil solicitado."""
    init_profiles()
    cfg_file = os.path.join(PROFILES_CONFIG_DIR, username, "candidate_profile.yaml")
    if not os.path.exists(cfg_file):
        # Fallback para o perfil padrão
        cfg_file = os.path.join(CONFIG_DIR, "candidate_profile.yaml")
    
    if os.path.exists(cfg_file):
        with open(cfg_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_profile(username: str, data: Dict[str, Any]):
    """Salva a configuração YAML de um perfil específico."""
    init_profiles()
    p_dir = os.path.join(PROFILES_CONFIG_DIR, username)
    os.makedirs(p_dir, exist_ok=True)
    cfg_file = os.path.join(p_dir, "candidate_profile.yaml")
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def get_resume_path(username: str = "eduardo") -> Optional[str]:
    """Retorna o caminho do PDF do currículo do perfil."""
    init_profiles()
    user_pdf = os.path.join(PROFILES_DATA_DIR, username, "curriculo.pdf")
    if os.path.exists(user_pdf):
        return user_pdf
    root_pdf = os.path.join(DATA_DIR, "curriculo.pdf")
    if os.path.exists(root_pdf):
        return root_pdf
    return None


def get_resume_text(username: str = "eduardo") -> str:
    """Extrai e retorna o texto completo do currículo em PDF do perfil."""
    pdf_path = get_resume_path(username)
    if not pdf_path or not os.path.exists(pdf_path):
        return ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n".join(text_parts).strip()
    except Exception as e:
        print(f"[Profiles] Erro ao extrair texto do currículo de {username}: {e}")
        return ""


def save_resume_file(username: str, file_bytes: bytes) -> str:
    """Salva o arquivo PDF de curriculo para o perfil indicado."""
    init_profiles()
    user_dir = os.path.join(PROFILES_DATA_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    target_path = os.path.join(user_dir, "curriculo.pdf")
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    return target_path


def create_or_update_profile(
    username: str,
    nome_completo: str,
    email: str = "",
    telefone: str = "",
    cidade: str = "Diadema",
    estado: str = "SP",
    cargos_alvo: Optional[List[str]] = None,
    salario_min: float = 3000.0,
    distancia_km: int = 30,
    linkedin_url: str = ""
) -> Dict[str, Any]:
    """Cria ou atualiza as configuracoes de um perfil."""
    init_profiles()
    current = get_profile(username)
    
    cand = current.get("candidato", {})
    cand["nome_completo"] = nome_completo.strip() if nome_completo else cand.get("nome_completo", username.capitalize())
    if email: cand["email"] = email.strip()
    if telefone: cand["telefone"] = telefone.strip()
    if cidade: cand["cidade"] = cidade.strip()
    if estado: cand["estado"] = estado.strip()
    if linkedin_url: cand["linkedin_url"] = linkedin_url.strip()
    
    prefs = current.get("preferencias_de_vaga", {})
    if cargos_alvo is not None:
        prefs["cargos_alvo"] = [c.strip() for c in cargos_alvo if c.strip()]
    if salario_min:
        prefs["salario_minimo_pretendido"] = float(salario_min)
        
    mods = prefs.get("modalidades", {})
    if not mods:
        mods = {
            "remoto": {"aceitar": True, "distancia_maxima_km": 99999},
            "hibrido": {"aceitar": True, "distancia_maxima_km": distancia_km},
            "presencial": {"aceitar": True, "distancia_maxima_km": distancia_km}
        }
    else:
        if "hibrido" in mods: mods["hibrido"]["distancia_maxima_km"] = distancia_km
        if "presencial" in mods: mods["presencial"]["distancia_maxima_km"] = distancia_km
    prefs["modalidades"] = mods

    current["candidato"] = cand
    current["preferencias_de_vaga"] = prefs
    
    save_profile(username, current)
    return current


def delete_profile(username: str) -> bool:
    """Remove pastas e dados do perfil (nao permite remover eduardo)."""
    if username.lower() == "eduardo":
        return False
    init_profiles()
    try:
        cfg_dir = os.path.join(PROFILES_CONFIG_DIR, username)
        if os.path.exists(cfg_dir):
            shutil.rmtree(cfg_dir, ignore_errors=True)
        data_dir = os.path.join(PROFILES_DATA_DIR, username)
        if os.path.exists(data_dir):
            shutil.rmtree(data_dir, ignore_errors=True)
        return True
    except Exception as e:
        print(f"[Profiles] Erro ao deletar perfil {username}: {e}")
        return False
