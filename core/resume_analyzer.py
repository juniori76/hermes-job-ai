"""
Extrator e Analisador de Currículo com IA - Hermes Job AI.
Extrai texto de PDFs, gera um resumo de perfil ATS e
destaca os pontos fortes para você revisar na Dashboard.
"""

import os
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_PDF = os.path.join(BASE_DIR, "data", "curriculo.pdf")


def extract_text_from_pdf(pdf_path: str = RESUME_PDF) -> str:
    """Extrai todo o texto legível de um arquivo PDF."""
    if not os.path.exists(pdf_path):
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text.strip()
    except Exception as e:
        print(f"[PDF Parser ⚠️] Erro ao extrair texto do PDF: {e}")
        return ""


def analyze_resume_with_ai() -> Dict[str, Any]:
    """
    Lê o PDF do currículo atual e solicita à LLM um diagnóstico ATS detalhado.
    """
    text = extract_text_from_pdf()
    if not text:
        return {
            "status": "not_found",
            "message": "Nenhum arquivo 'curriculo.pdf' encontrado em data/. Faça upload no painel."
        }

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "no_key",
            "message": "Chave da API Gemini não configurada."
        }

    client = genai.Client(api_key=api_key)
    fast_model = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash")

    prompt = f"""
Você é um especialista em Recrutamento de TI e sistemas de triagem ATS (Applicant Tracking Systems).
Analise o currículo abaixo e gere um diagnóstico completo e estruturado para o candidato.

--- TEXTO DO CURRÍCULO ---
\"\"\"
{text[:6000]}
\"\"\"

--- RESPOSTA OBRIGATÓRIA EM JSON PURO ---
Responda EXATAMENTE no formato JSON com as chaves:
{{
  "candidate_name": "<Nome identificado>",
  "seniority_level": "<ex: Júnior, Pleno, Especialista>",
  "primary_roles": ["Cargo ideal 1", "Cargo ideal 2"],
  "top_skills": ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5"],
  "ats_strength_score": <nota de 0 a 100 baseada na clareza e palavras-chave do CV>,
  "strengths_summary": "<resumo dos 3 principais pontos fortes profissionais>",
  "improvement_tips": "<2 ou 3 dicas práticas de palavras-chave ou detalhes para melhorar o currículo>"
}}
"""

    try:
        resp = client.models.generate_content(
            model=fast_model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        )
        import json
        data = json.loads(resp.text.strip())
        data["status"] = "success"
        data["raw_length"] = len(text)
        return data
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro na análise de IA: {str(e)[:150]}"
        }
