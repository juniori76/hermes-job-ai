"""
Laboratório de Análise ATS Independente - Hermes Job AI 2.0.
Permite testar, avaliar e pontuar QUALQUER currículo de forma 100% isolada,
sem alterar nem interferir no perfil mestre cadastrado ou no robô de vagas.
"""

import os
import json
import io
from typing import Dict, Any, Optional
from pypdf import PdfReader
from core import llm


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extrai texto de um stream de bytes de PDF."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"[ATSLab] Erro ao extrair texto do PDF: {e}")
        return ""


def analyze_standalone_resume(
    pdf_bytes: Optional[bytes] = None,
    raw_text: Optional[str] = None,
    target_role: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analisa um currículo avulso e gera diagnóstico completo de aderência a sistemas ATS (Gupy, Kenoby, Workday, LinkedIn).
    Não salva nem sobrescreve nenhum dado do sistema.
    """
    text = ""
    if pdf_bytes:
        text = extract_text_from_pdf_bytes(pdf_bytes)
    elif raw_text:
        text = raw_text.strip()

    if not text:
        return {
            "success": False,
            "error": "Não foi possível extrair texto do currículo. Verifique se o arquivo PDF contém texto selecionável (não pode ser foto/imagem escaneada)."
        }

    role_context = f"Cargo pretendido informado pelo candidato: '{target_role}'." if target_role and target_role.strip() else "O candidato não especificou um cargo; deduza o melhor posicionamento a partir do histórico."

    prompt = f"""
Você é o mais rigoroso especialista em Recrutamento e Algoritmos ATS (Gupy, Kenoby, Workday, Taleo, LinkedIn Recruiter).
Sua missão é auditar o currículo abaixo de forma totalmente imparcial, técnica e construtiva.

CONTEXTO:
{role_context}

TEXTO EXTRAÍDO DO CURRÍCULO:
\"\"\"
{text[:7000]}
\"\"\"

Critérios de pontuação ATS:
- Clareza estrutural e legibilidade por robôs (contatos no topo, cabeçalhos padrão, sem colunas confusas).
- Densidade de palavras-chave da profissão/área.
- Presença de verbos de ação e resultados quantificados (números, prazos, %, métricas).
- Atualidade e coerência da trajetória profissional.

Responda ESTRITAMENTE em formato JSON com as chaves:
{{
  "ats_score": 78,
  "nivel_identificado": "Júnior / Pleno / Sênior / Operacional / Especialista",
  "cargo_principal_identificado": "Título que melhor define o currículo atual",
  "veredicto_geral": "Diagnóstico executivo de 2 a 3 frases sobre a chance de aprovação na triagem de robôs.",
  "pontos_fortes": [
    "Ponto forte 1 identificado pelos robôs de RH",
    "Ponto forte 2",
    "Ponto forte 3"
  ],
  "falhas_criticas": [
    "Gargalo 1 que faz robôs de ATS descartarem ou pontuarem baixo",
    "Gargalo 2",
    "Gargalo 3"
  ],
  "palavras_chave_ausentes": [
    "Palavra-chave essencial recomendada 1",
    "Palavra-chave 2",
    "Palavra-chave 3",
    "Palavra-chave 4"
  ],
  "sugestoes_de_melhoria": [
    "Ação prática 1 para o candidato alterar no texto do currículo",
    "Ação prática 2",
    "Ação prática 3"
  ],
  "resumo_profissional_sugerido": "Um modelo de resumo profissional pronto e de alto impacto (3 a 5 linhas) reescrito sob medida para o candidato copiar e colar no topo do seu currículo."
}}
"""

    try:
        result = llm.generate_json(prompt, smart=False, temperature=0.2)
        if not result or not isinstance(result, dict):
            # Fallback usando generate padrão
            raw = llm.generate(prompt, smart=False, temperature=0.2)
            clean = raw.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            result = json.loads(clean.strip())

        return {
            "success": True,
            "filename": filename or "curriculo_analisado.pdf",
            "target_role": target_role or result.get("cargo_principal_identificado", "Geral"),
            "data": result
        }
    except Exception as e:
        print(f"[ATSLab Error] Falha na análise: {e}")
        return {
            "success": False,
            "error": f"Falha na análise com a IA: {e}"
        }
