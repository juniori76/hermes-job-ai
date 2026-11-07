"""
Cérebro ATS & Triagem com IA - Hermes Job AI.
Avalia a compatibilidade das vagas com o perfil do candidato (Score 0-100).
Se a IA falhar, a vaga continua PENDENTE (nunca grava score falso).
"""

from typing import Dict, Any, Optional

from core import llm
from core.database import get_pending_evaluations, update_job_evaluation
from core.radar import load_profile
from core.resume_analyzer import extract_text_from_pdf
from core.distance_engine import validate_job_policy
from core.settings_manager import get_operation_mode, load_settings
from core.notifier import notify_high_score_job


def _build_prompt(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str) -> str:
    candidato = profile.get("candidato", {})
    competencias = profile.get("competencias_chave", [])
    prefs = profile.get("preferencias_de_vaga", {})
    resume_block = f"\nCURRÍCULO (texto extraído):\n{resume_text[:4000]}\n" if resume_text else ""

    return f"""
Você é um avaliador especialista em recrutamento técnico e filtros ATS.
Analise com rigor a vaga contra o perfil REAL do candidato. Não invente qualificações.

--- PERFIL DO CANDIDATO ---
Competências Chave: {', '.join(competencias)}
Cargos-alvo: {', '.join(prefs.get('cargos_alvo', []))}
Modalidades Aceitas: {prefs.get('modalidades_aceitas')}
Raio Aceitável para Híbrido: {prefs.get('raio_maximo_km_hibrido')} km a partir de {candidato.get('cidade')}-{candidato.get('estado')}
{resume_block}
--- VAGA ---
Título: {job.get('title')}
Empresa: {job.get('company')}
Localização: {job.get('location')}
Remota: {job.get('is_remote')}
Descrição:
\"\"\"
{(job.get('description') or '')[:3000]}
\"\"\"

--- CRITÉRIOS ---
1. score 0-100: 90+ encaixe perfeito; 70-89 bom; abaixo de 60 fora do escopo ou modalidade incompatível.
2. matched_keywords: termos técnicos da vaga que o candidato realmente possui.
3. decision: "approve" (>=75), "review" (60-74), "reject" (<60).

Responda SOMENTE JSON:
{{"score": <int>, "decision": "approve"|"review"|"reject", "match_reasons": "<2 frases>", "matched_keywords": ["..."]}}
"""


def evaluate_job_match(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str = "") -> Optional[Dict[str, Any]]:
    """Retorna o dicionário da avaliação, ou None se falhar (vaga segue pendente)."""
    # 1. Filtro prévio rígido de Distância, Modalidade e Salário (Sem gastar tokens de IA)
    is_valid, policy_reason = validate_job_policy(job, profile)
    if not is_valid:
        print(f"  🚫 [DESCARTADA PELA POLÍTICA] {job.get('company')} - {job.get('title')}: {policy_reason}")
        return {
            "score": 0,
            "decision": "reject",
            "match_reasons": f"Descartada por critério de localização/salário: {policy_reason}",
            "matched_keywords": []
        }

    try:
        data = llm.generate_json(_build_prompt(job, profile, resume_text))
        score = int(data.get("score"))
        data["score"] = max(0, min(100, score))
        return data
    except (llm.GeminiAuthError, llm.GeminiUnavailable):
        raise
    except Exception as e:
        print(f"[ATS Brain] Falha ao avaliar '{job.get('title')}': {e}")
        return None


def run_ats_evaluation_batch(batch_size: int = 30) -> int:
    pending = get_pending_evaluations(limit=batch_size)
    if not pending:
        print("[ATS Brain] Nenhuma vaga pendente de avaliação.")
        return 0

    profile = load_profile()
    resume_text = extract_text_from_pdf()
    print(f"[ATS Brain] Avaliando {len(pending)} vagas (currículo {'carregado' if resume_text else 'AUSENTE'})...")
    done = 0
    consecutive_unavailable = 0

    for job in pending:
        try:
            result = evaluate_job_match(job, profile, resume_text)
            consecutive_unavailable = 0
        except llm.GeminiAuthError as e:
            print(f"[ATS Brain] ERRO DE CONFIGURAÇÃO, lote interrompido: {e}")
            break
        except llm.GeminiUnavailable as e:
            consecutive_unavailable += 1
            print(f"[ATS Brain] IA indisponível para '{job.get('title')}': {e}")
            if consecutive_unavailable >= 3:
                print("[ATS Brain] 3 falhas seguidas: lote interrompido, tentará no próximo ciclo.")
                break
            continue
        if result is None:
            continue

        final_status = result.get("decision", "review")
        update_job_evaluation(
            job_id=job["id"],
            score=result["score"],
            reasons=result.get("match_reasons", ""),
            keywords=", ".join(result.get("matched_keywords", [])),
            status=final_status,
        )
        done += 1
        print(f"  [{result['score']}%] {job.get('company')} - {job.get('title')} -> {final_status}")

        # --- Telegram: notifica vagas de alto score em modo smart ou auto ---
        try:
            settings = load_settings()
            mode = settings.get("operation_mode", "review")
            threshold = settings.get("smart_score_threshold", 80)
            if mode in ("smart", "auto") and result["score"] >= threshold:
                enriched_job = {**job, "match_score": result["score"],
                                "match_reasons": result.get("match_reasons", ""),
                                "age_hours": job.get("age_hours")}
                notify_high_score_job(enriched_job)
        except Exception as tg_err:
            print(f"[ATS Brain] Telegram erro (não crítico): {tg_err}")

    print(f"[ATS Brain] {done}/{len(pending)} vagas avaliadas.")
    return done


if __name__ == "__main__":
    run_ats_evaluation_batch()
