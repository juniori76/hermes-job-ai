"""
Cérebro ATS & Triagem com IA - Hermes Job AI.
Utiliza o modelo rápido Gemini Flash para avaliar a compatibilidade
das vagas com o currículo do candidato (Match Score 0-100%).
"""

import os
import json
from typing import Dict, Any, List
from google import genai
from google.genai import types
from dotenv import load_dotenv

from core.database import get_pending_evaluations, update_job_evaluation
from core.radar import load_profile

load_dotenv()

# Configuração da API do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FAST_MODEL = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash")


def get_gemini_client() -> genai.Client:
    """Retorna o cliente autenticado do Google GenAI SDK."""
    if not GEMINI_API_KEY:
        raise ValueError("Chave GEMINI_API_KEY não encontrada nas variáveis de ambiente.")
    return genai.Client(api_key=GEMINI_API_KEY)


def evaluate_job_match(client: genai.Client, job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compara a descrição da vaga com o perfil do candidato usando Gemini Flash.
    Retorna o Score (0-100), palavras-chave batidas e recomendação.
    """
    candidato = profile.get("candidato", {})
    competencias = profile.get("competencias_chave", [])
    prefs = profile.get("preferencias_de_vaga", {})

    prompt = f"""
Você é um avaliador especialista em recrutamento técnico e quebra de filtros ATS (Applicant Tracking Systems).
Sua missão é analisar com rigor a descrição da vaga abaixo contra o perfil real do candidato.

--- PERFIL DO CANDIDATO ---
Competências Chave: {', '.join(competencias)}
Modalidades Aceitas: {prefs.get('modalidades_aceitas')}
Raio Aceitável para Híbrido: {prefs.get('raio_maximo_km_hibrido')} km a partir de {candidato.get('cidade')}-{candidato.get('estado')}

--- DADOS DA VAGA ---
Título: {job.get('title')}
Empresa: {job.get('company')}
Localização: {job.get('location')}
É Remoto?: {job.get('is_remote')}
Descrição da Vaga:
\"\"\"
{job.get('description', '')[:3000]}
\"\"\"

--- CRITÉRIOS DE AVALIAÇÃO ---
1. Score (0 a 100):
   - 90-100: Bate perfeitamente com os requisitos obrigatórios (ex: Windows Server, AD, Suporte/Redes).
   - 70-89: Bom encaixe, faltam apenas alguns requisitos desejáveis/secundários.
   - Abaixo de 60: Fora do escopo técnico ou modalidade incompatível (ex: presencial a 100km).
2. Palavras-chave: Identifique termos técnicos da vaga que casam com o candidato.
3. Decisão: "approve" (se score >= 75), "review" (se entre 60 e 74), "reject" (se < 60).

--- RESPOSTA OBRIGATÓRIA EM JSON PURO ---
Responda EXATAMENTE no formato JSON com as chaves:
{{
  "score": <inteiro de 0 a 100>,
  "decision": "approve" | "review" | "reject",
  "match_reasons": "<resumo claro em 2 frases destacando os pontos fortes e eventuais faltas>",
  "matched_keywords": ["keyword1", "keyword2"]
}}
"""

    try:
        response = client.models.generate_content(
            model=FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2 # Baixa temperatura para avaliação estável e objetiva
            ),
        )

        data = json.loads(response.text.strip())
        return data

    except Exception as e:
        print(f"[ATS Brain ⚠️] Erro ao avaliar vaga '{job.get('title')}': {e}")
        # Retorno de fallback seguro em caso de indisponibilidade momentânea
        return {
            "score": 50,
            "decision": "review",
            "match_reasons": f"Falha na avaliação automática: {str(e)[:100]}",
            "matched_keywords": []
        }


def run_ats_evaluation_batch(batch_size: int = 30) -> int:
    """
    Pega vagas pendentes no banco e roda a triagem de IA com Gemini Flash.
    """
    if not GEMINI_API_KEY:
        print("[ATS Brain ⚠️] GEMINI_API_KEY não configurada no .env. Pulei avaliação.")
        return 0

    client = get_gemini_client()
    profile = load_profile()
    
    pending_jobs = get_pending_evaluations(limit=batch_size)
    if not pending_jobs:
        print("[ATS Brain] Nenhuma vaga pendente de avaliação no banco.")
        return 0

    print(f"\n[ATS Brain] 🧠 Iniciando avaliação de {len(pending_jobs)} vagas com Gemini Flash...")
    evaluated_count = 0

    for job in pending_jobs:
        eval_result = evaluate_job_match(client, job, profile)
        score = eval_result.get("score", 50)
        reasons = eval_result.get("match_reasons", "")
        keywords = ", ".join(eval_result.get("matched_keywords", []))
        status = eval_result.get("decision", "reviewed")

        update_job_evaluation(
            job_id=job["id"],
            score=score,
            reasons=reasons,
            keywords=keywords,
            status=status
        )

        evaluated_count += 1
        print(f"  ⭐ [{score}%] {job.get('company')} - {job.get('title')} -> {status.upper()}")

    print(f"[ATS Brain] ✅ {evaluated_count} vagas avaliadas e ranqueadas com sucesso!\n")
    return evaluated_count


if __name__ == "__main__":
    run_ats_evaluation_batch()
