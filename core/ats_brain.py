"""
Cérebro ATS Gemini Flash - Hermes Job AI.
Avaliação semântica e pontuação de compatibilidade (0-100) contra o perfil e currículo do candidato.
Totalmente multi-perfil: avalia cada vaga contra o currículo e preferências do respectivo candidato.
"""

from typing import Dict, Any, Optional

from core import llm
from core.database import get_pending_evaluations, update_job_evaluation
from core.distance_engine import validate_job_policy
from core.settings_manager import get_operation_mode, load_settings
from core.notifier import notify_high_score_job
from core.profiles_manager import get_profile, get_resume_text


def _build_prompt(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str = "") -> str:
    candidato = profile.get("candidato", {})
    competencias = profile.get("competencias_chave", [])
    prefs = profile.get("preferencias_de_vaga", {})
    cargos_alvo = prefs.get("cargos_alvo") or profile.get("cargos_alvo", [])
    
    # Extrai modalidades aceitas do perfil
    modalidades_cfg = prefs.get("modalidades", {})
    modalidades_list = []
    if modalidades_cfg.get("remoto", {}).get("aceitar", True):
        modalidades_list.append("Remoto (100% Home Office)")
    if modalidades_cfg.get("hibrido", {}).get("aceitar", True):
        max_h = modalidades_cfg.get("hibrido", {}).get("distancia_maxima_km", 30)
        modalidades_list.append(f"Híbrido (até {max_h} km)")
    if modalidades_cfg.get("presencial", {}).get("aceitar", True):
        max_p = modalidades_cfg.get("presencial", {}).get("distancia_maxima_km", 25)
        modalidades_list.append(f"Presencial (até {max_p} km da residência)")
    modalidades_str = ", ".join(modalidades_list) if modalidades_list else "Remoto, Híbrido e Presencial"

    resume_block = f"\nCURRÍCULO REAL (texto oficial do candidato):\n{resume_text[:4000]}\n" if resume_text else "\n(Obs: O candidato ainda não anexou currículo em PDF; avalie com base nas preferências e cargos do perfil)\n"

    return f"""
Você é um avaliador especialista em recrutamento e seleção de RH e motores ATS.
Analise com rigor a vaga contra o perfil e currículo REAL do candidato. Não invente qualificações.

--- PERFIL DO CANDIDATO ---
Candidato: {candidato.get('nome_completo', 'Candidato')} - Residente em {candidato.get('cidade', 'Diadema')}-{candidato.get('estado', 'SP')}
Cargos pretendidos: {', '.join(cargos_alvo)}
Competências e tecnologias: {', '.join(competencias) if competencias else 'Conforme currículo'}
Modalidades Aceitas: {modalidades_str}
{resume_block}
--- VAGA ANUNCIADA ---
Título: {job.get('title')}
Empresa: {job.get('company')}
Localização: {job.get('location')}
Remota: {job.get('is_remote')}
Descrição:
\"\"\"
{(job.get('description') or '')[:3000]}
\"\"\"

--- CRITÉRIOS DE PONTUAÇÃO ATS ---
1. score (0 a 100):
   - 85-100: Encaixe excelente com os requisitos, formação e competências exigidas para o cargo.
   - 70-84: Bom alinhamento com a maioria das responsabilidades da vaga.
   - 50-69: Exige qualificações centrais ou ferramentas que o candidato não possui no perfil/currículo.
   - < 50: Vaga totalmente fora da área de atuação do candidato ou geograficamente inviável.
2. matched_keywords: termos, requisitos e competências reais da vaga que o candidato possui.
3. decision: "approve" (score >= 75), "review" (60-74), "reject" (< 60).

Responda SOMENTE um JSON puro:
{{"score": <int>, "decision": "approve"|"review"|"reject", "match_reasons": "<2 frases explicando a aderência técnica e viabilidade de localização>", "matched_keywords": ["..."]}}
"""


def evaluate_job_match(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str = "") -> Optional[Dict[str, Any]]:
    # Valida política de distância, modalidade e salário antes de gastar cota de IA
    policy_ok, policy_reason = validate_job_policy(job, profile)
    if not policy_ok:
        return {
            "score": 25,
            "decision": "reject",
            "match_reasons": f"Descartada por critério de localização/salário: {policy_reason}",
            "matched_keywords": []
        }

    try:
        data = llm.generate_json(_build_prompt(job, profile, resume_text))
        score = int(data.get("score", 0))
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

    print(f"[ATS Brain] 🧠 Avaliando {len(pending)} vagas com isolamento multi-perfil...")
    done = 0
    consecutive_unavailable = 0

    for job in pending:
        target_user = job.get("target_user") or "eduardo"
        user_profile = get_profile(target_user)
        user_resume_text = get_resume_text(target_user)

        try:
            result = evaluate_job_match(job, user_profile, user_resume_text)
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
        print(f"  [{result['score']}%] (@{target_user}) {job.get('company')} - {job.get('title')} -> {final_status}")

        # --- Telegram: notifica vagas de alto score especificamente para o candidato ---
        try:
            settings = load_settings()
            mode = settings.get("operation_mode", "review")
            threshold = settings.get("smart_score_threshold", 80)
            if mode in ("smart", "auto") and result["score"] >= threshold:
                enriched_job = {
                    **job,
                    "target_user": target_user,
                    "match_score": result["score"],
                    "match_reasons": result.get("match_reasons", ""),
                    "age_hours": job.get("age_hours")
                }
                notify_high_score_job(enriched_job)
        except Exception as tg_err:
            print(f"[ATS Brain] Telegram erro (não crítico): {tg_err}")

    print(f"[ATS Brain] {done}/{len(pending)} vagas avaliadas.")
    return done


if __name__ == "__main__":
    run_ats_evaluation_batch()
