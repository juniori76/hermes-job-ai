"""
Gerador de Cartas de Apresentação e Mensagens para Recrutadores (Cover Letter & InMail Pitch)
Hermes Job AI - Multi-perfil.
Gera textos persuasivos sob medida para candidaturas na Gupy, LinkedIn e Indeed.
"""

from typing import Dict, Any, Optional
from core import llm
from core.database import get_connection
from core.profiles_manager import get_profile
from core.resume_analyzer import extract_text_from_pdf


def generate_cover_letter(job_id: str, username: str = "eduardo", tone: str = "persuasivo") -> Dict[str, Any]:
    """
    Gera uma carta de apresentação sob medida para uma vaga específica,
    cruzando os requisitos reais da vaga com a trajetória do candidato.
    """
    # 1. Busca a vaga no banco de dados
    job = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            job = dict(row)
    except Exception as e:
        return {"success": False, "error": f"Erro ao consultar vaga no banco: {e}"}

    if not job:
        return {"success": False, "error": f"Vaga #{job_id} não encontrada."}

    # 2. Carrega o perfil e o currículo do candidato
    if not username or username == "all":
        username = job.get("target_user") or "eduardo"
    if not username or username == "all":
        username = job.get("target_user") or "eduardo"
    profile = get_profile(username)
    candidate_name = profile.get("candidato", {}).get("nome_completo") or username.capitalize()
    candidate_city = profile.get("candidato", {}).get("cidade") or "São Paulo"
    candidate_state = profile.get("candidato", {}).get("estado") or "SP"
    
    cv_text = extract_text_from_pdf(username=username)
    if not cv_text:
        # Fallback para as experiências listadas no profile.json
        exps = profile.get("experiencia_profissional", [])
        exp_summary = "\n".join([f"- {e.get('cargo')} na {e.get('empresa')}: {e.get('descricao', '')}" for e in exps])
        cv_text = f"Candidato: {candidate_name}\nResumo: {profile.get('candidato', {}).get('resumo_profissional', '')}\nExperiências:\n{exp_summary}"

    job_title = job.get("title", "")
    company = job.get("company", "")
    job_loc = job.get("location", "")
    job_desc = (job.get("description") or job.get("keywords_found") or "")[:2500]
    is_remote = bool(job.get("is_remote"))

    prompt = f"""
Você é um especialista sênior em recrutamento e redação executiva de cartas de apresentação para processos seletivos.
Escreva uma CARTA DE APRESENTAÇÃO / PITCH PROFISSIONAL de alto impacto para o candidato se destacar perante o recrutador.

DADOS DA VAGA:
- Cargo: {job_title}
- Empresa: {company}
- Localização: {job_loc} {'(100% Remoto)' if is_remote else ''}
- Requisitos e Descrição:
{job_desc}

DADOS DO CANDIDATO:
- Nome: {candidate_name}
- Localização: {candidate_city} - {candidate_state}
- Histórico / Competências:
{cv_text[:3000]}

DIRETRIZES DE ESCRITA:
1. Tom: {tone.capitalize()}, profissional, seguro, direto e cordial.
2. Tamanho: Entre 2 e 3 parágrafos concisos (ideal para copiar e colar na Gupy, Indeed ou enviar por mensagem/InMail no LinkedIn).
3. Conexão real: Cite 2 ou 3 ferramentas/competências concretas do candidato que respondem diretamente ao que a empresa procura.
4. Sem clichês vazios: Não use frases como "venho por meio desta", "sou pontual e esforçado". Vá direto ao valor que o profissional gera para a vaga.
5. Finalize com chamada para ação amigável convidando para um bate-papo técnico ou entrevista.

Responda APENAS o texto pronto da carta, sem introduções ou explicações suas.
"""

    try:
        letter = llm.generate(prompt, smart=False, temperature=0.35)
        letter = letter.strip()
        if letter.startswith("```"):
            letter = letter.replace("```markdown", "").replace("```", "").strip()

        return {
            "success": True,
            "job_id": job_id,
            "job_title": job_title,
            "company": company,
            "candidate_name": candidate_name,
            "cover_letter": letter
        }
    except Exception as e:
        return {"success": False, "error": f"Falha na geração com IA: {e}"}
