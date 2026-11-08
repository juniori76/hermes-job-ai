"""
Extrator e Analisador de Currículo com IA - Hermes Job AI.
Multi-perfil: analisa o currículo específico de cada usuário cadastrado.
"""

import os
from typing import Dict, Any

from pypdf import PdfReader
from core import llm, config
from core.profiles_manager import get_resume_path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RESUME_PDF = os.path.join(BASE_DIR, "data", "curriculo.pdf")


def extract_text_from_pdf(pdf_path: str = None, username: str = "eduardo") -> str:
    if not pdf_path:
        pdf_path = get_resume_path(username) or DEFAULT_RESUME_PDF
    if not pdf_path or not os.path.exists(pdf_path):
        return ""
    try:
        reader = PdfReader(pdf_path)
        parts = [(p.extract_text() or "") for p in reader.pages]
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"[PDF Parser] Erro ao extrair texto do PDF ({pdf_path}): {e}")
        return ""


def analyze_resume_with_ai(username: str = "eduardo") -> Dict[str, Any]:
    pdf_path = get_resume_path(username)
    if not pdf_path or not os.path.exists(pdf_path):
        return {
            "status": "not_found", 
            "message": f"Nenhum currículo cadastrado para @{username}. Envie um arquivo PDF na aba 'Análise de Currículo ATS'."
        }

    text = extract_text_from_pdf(pdf_path=pdf_path, username=username)
    if not text:
        return {
            "status": "error", 
            "message": "Não foi possível extrair texto do PDF (pode ser escaneado como imagem). Envie um PDF com texto selecionável."
        }

    if not config.has_api_key():
        return {"status": "no_key", "message": "Chave da API Gemini não configurada."}

    prompt = f"""
Você é um especialista em Recrutamento de Recursos Humanos e análise ATS.
Analise o currículo abaixo do candidato @{username} e gere um diagnóstico completo e imparcial.
Use apenas os dados reais presentes no texto.

--- CURRÍCULO ---
\"\"\"
{text[:6000]}
\"\"\"

Responda SOMENTE um JSON puro com as chaves:
{{
  "candidate_name": "Nome identificado",
  "seniority_level": "Júnior / Pleno / Sênior / etc.",
  "primary_roles": ["Cargo 1", "Cargo 2"],
  "top_skills": ["Competência 1", "Competência 2"],
  "ats_strength_score": 85,
  "strengths_summary": "Resumo dos pontos fortes",
  "improvement_tips": "Dicas práticas de melhoria"
}}
"""
    try:
        data = llm.generate_json(prompt)
        data["status"] = "success"
        data["raw_length"] = len(text)
        return data
    except llm.GeminiAuthError as e:
        return {"status": "error", "message": f"Problema de configuração da IA: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Erro na análise de IA: {str(e)[:150]}"}
