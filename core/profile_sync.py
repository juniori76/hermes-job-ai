"""
Sincronizador Automático de Perfil com IA - Hermes Job AI.
Extrai todas as experiências, formação, competências e links do curriculo.pdf
e atualiza automaticamente o arquivo candidate_profile.yaml.
"""

import os
import yaml
from typing import Dict, Any

from core import llm
from core.radar import CONFIG_PATH, load_profile
from core.resume_analyzer import extract_text_from_pdf


def sync_profile_from_resume_ai() -> Dict[str, Any]:
    """
    Lê o PDF do currículo e pede para a IA extrair dados estruturados
    completos para atualizar o perfil de candidatura.
    """
    text = extract_text_from_pdf()
    if not text:
        return {"status": "error", "message": "Nenhum arquivo curriculo.pdf encontrado."}

    prompt = f"""
Você é um especialista em Recrutamento de TI e estruturação de dados de carreira.
Leia o currículo abaixo e extraia com precisão absoluta os dados do candidato para um arquivo de perfil estruturado.

--- TEXTO DO CURRÍCULO ---
\"\"\"
{text[:6000]}
\"\"\"

--- REGRAS DE EXTRAÇÃO ---
1. Extraia o nome completo, e-mail, telefone, cidade, estado e links profissionais (LinkedIn, GitHub se houver).
2. Resumo Profissional: crie um texto conciso de 3 a 4 linhas destacando senioridade, tecnologias principais e impacto.
3. Cargos Alvo: sugira de 4 a 6 cargos compatíveis com o histórico (ex: Analista de Suporte Pleno, Analista de Infraestrutura, etc.).
4. Competências Chave: liste de 10 a 15 tecnologias reais mencionadas (ex: MikroTik, Fortinet, VMware, Proxmox, Active Directory, Zabbix, etc.).
5. Experiências Relevantes: liste as 3 ou 4 últimas empresas com cargo, período aproximado e principais atividades técnicas.

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
        data = llm.generate_json(prompt, temperature=0.1)
        profile_path = os.path.join(CONFIG_PATH, "candidate_profile.yaml")
        current_profile = load_profile()

        # Atualiza dados cadastrais sem perder configurações de regras/km
        cand_extraido = data.get("candidato", {})
        cand_atual = current_profile.setdefault("candidato", {})
        for k in ["nome_completo", "email", "telefone", "cidade", "estado", "linkedin_url", "github_url"]:
            if cand_extraido.get(k):
                cand_atual[k] = cand_extraido[k]

        cand_atual["resumo_profissional"] = cand_extraido.get("resumo_profissional", "")

        # Atualiza competências e cargos recomendados
        if data.get("competencias_chave"):
            current_profile["competencias_chave"] = data["competencias_chave"]
        
        prefs = current_profile.setdefault("preferencias_de_vaga", {})
        if data.get("cargos_alvo"):
            # Mantém cargos customizados ou mescla
            prefs["cargos_alvo"] = list(dict.fromkeys(data["cargos_alvo"] + prefs.get("cargos_alvo", [])))

        current_profile["historico_experiencias"] = data.get("experiencias", [])

        # Grava de volta no candidate_profile.yaml
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(current_profile, f, allow_unicode=True)

        return {
            "status": "success",
            "message": "Perfil atualizado e sincronizado com o currículo via IA!",
            "dados": data
        }

    except Exception as e:
        print(f"[Profile Sync ⚠️] Erro ao sincronizar perfil: {e}")
        return {"status": "error", "message": f"Erro na IA: {str(e)[:150]}"}
