"""
Extrator e Analisador de Currículo com IA - Hermes Job AI.
"""

import os
from typing import Dict, Any

from pypdf import PdfReader
from core import llm, config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_PDF = os.path.join(BASE_DIR, "data", "curriculo.pdf")


def extract_text_from_pdf(pdf_path: str = RESUME_PDF) -> str:
    if not os.path.exists(pdf_path):
        return ""
    try:
        reader = PdfReader(pdf_path)
        parts = [(p.extract_text() or "") for p in reader.pages]
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"[PDF Parser] Erro ao extrair texto: {e}")
        return ""


def analyze_resume_with_ai() -> Dict[str, Any]:
    if not os.path.exists(RESUME_PDF):
        return {"status": "not_found", "message": "Nenhum curriculo.pdf enviado. Faça upload na aba Preferências."}

    text = extract_text_from_pdf()
    if not text:
        return {"status": "error", "message": "Não consegui extrair texto do PDF (pode ser um PDF escaneado/imagem). Envie um PDF com texto selecionável."}

    if not config.has_api_key():
        return {"status": "no_key", "message": "Chave da API Gemini não configurada."}

    prompt = f"""
Você é especialista em recrutamento de TI e sistemas ATS. Analise o currículo e gere um diagnóstico.
Use apenas o que está no texto.

CURRÍCULO:
\"\"\"
{text[:6000]}
\"\"\"

Responda SOMENTE JSON com as chaves:
{{"candidate_name": "", "seniority_level": "", "primary_roles": [], "top_skills": [],
  "ats_strength_score": <0-100>, "strengths_summary": "", "improvement_tips": ""}}
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
