"""
Sincronizador Automático de Perfil com IA - Hermes Job AI.
Multi-perfil: extrai dados do currículo do usuário logado e atualiza seu perfil estruturado.
"""

import os
import yaml
from typing import Dict, Any

from core import llm
from core.profiles_manager import get_profile, save_profile, get_resume_path
from core.resume_analyzer import extract_text_from_pdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config")


def sync_profile_from_resume_ai(username: str = "eduardo") -> Dict[str, Any]:
    """
    Lê o PDF do currículo do usuário e pede para a IA extrair dados estruturados
    completos para atualizar o perfil de candidatura específico desse usuário.
    """
    pdf_path = get_resume_path(username)
    if not pdf_path or not os.path.exists(pdf_path):
        return {"status": "error", "message": f"Nenhum arquivo de currículo encontrado para @{username}."}

    text = extract_text_from_pdf(pdf_path=pdf_path, username=username)
    if not text:
        return {"status": "error", "message": f"Não foi possível extrair texto do currículo de @{username}."}

    prompt = f"""
Você é um especialista em Recrutamento e estruturação de dados profissionais para sistemas de RH.
Leia o currículo abaixo do candidato @{username} e extraia com precisão absoluta os dados para um arquivo de perfil estruturado.

--- TEXTO DO CURRÍCULO ---
\"\"\"
{text[:6000]}
\"\"\"

--- REGRAS DE EXTRAÇÃO ---
1. Extraia o nome completo, e-mail, telefone, cidade, estado e links profissionais (LinkedIn, GitHub se houver).
2. Resumo Profissional: crie um texto conciso de 3 a 4 linhas destacando a área de atuação, principais competências e histórico.
3. Cargos Alvo: sugira de 3 a 6 cargos compatíveis com a área e histórico do candidato.
4. Competências Chave: liste de 8 a 15 competências reais mencionadas.
5. Experiências Relevantes: liste as empresas com cargo, período aproximado e principais atividades.

Responda SOMENTE um JSON puro com as chaves:
{{
  "candidato": {{
    "nome_completo": "",
    "email": "",
    "telefone": "",
    "cidade": "",
    "estado": "",
    "linkedin_url": "",
    "github_url": "",
    "resumo_profissional": ""
  }},
  "cargos_alvo": ["...", "..."],
  "competencias_chave": ["...", "..."],
  "experiencias": [
    {{
      "empresa": "",
      "cargo": "",
      "periodo": "",
      "atividades": ""
    }}
  ]
}}
"""
    try:
        data = llm.generate_json(prompt)
        current_profile = get_profile(username)
        
        # Atualiza dados do candidato
        candidato = current_profile.setdefault("candidato", {})
        cand_ai = data.get("candidato", {})
        for k in ["nome_completo", "email", "telefone", "cidade", "estado", "linkedin_url", "github_url", "resumo_profissional"]:
            if cand_ai.get(k):
                candidato[k] = cand_ai[k]

        # Atualiza competências e cargos recomendados
        if data.get("competencias_chave"):
            current_profile["competencias_chave"] = data["competencias_chave"]
        
        prefs = current_profile.setdefault("preferencias_de_vaga", {})
        if data.get("cargos_alvo"):
            prefs["cargos_alvo"] = list(dict.fromkeys(data["cargos_alvo"] + prefs.get("cargos_alvo", [])))

        current_profile["historico_experiencias"] = data.get("experiencias", [])

        # Salva no perfil do usuário
        save_profile(username, current_profile)
        if username == "eduardo":
            root_yaml = os.path.join(CONFIG_PATH, "candidate_profile.yaml")
            with open(root_yaml, "w", encoding="utf-8") as f:
                yaml.safe_dump(current_profile, f, allow_unicode=True)

        return {
            "status": "success",
            "message": f"Perfil de @{username} sincronizado com sucesso com o currículo!",
            "dados": data
        }

    except Exception as e:
        print(f"[Profile Sync ⚠️] Erro ao sincronizar perfil de {username}: {e}")
        return {"status": "error", "message": f"Erro na IA: {str(e)[:150]}"}
