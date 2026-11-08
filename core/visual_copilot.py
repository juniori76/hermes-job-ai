"""
Copiloto IA de Formulários e Questões (Visual Copilot) - Hermes 2.0.
Recebe prints de tela (ou texto) de formulários de vagas (Gupy, LinkedIn, Workday, etc.),
lê as perguntas via Visão Computacional (Gemini 2.5 Flash Multimodal)
e gera a resposta personalizada exata, em 1ª pessoa, fundamentada no currículo do usuário.
"""

from typing import Dict, Any, Optional
import yaml

from core.llm import generate, generate_with_image
from core.profiles_manager import get_profile, get_resume_text


def answer_job_question(
    image_bytes: Optional[bytes] = None,
    text_question: Optional[str] = None,
    username: str = "eduardo",
    mime_type: str = "image/png"
) -> Dict[str, Any]:
    """
    Processa a imagem ou texto da pergunta do formulário da vaga
    e devolve a resposta pronta para copiar e colar.
    """
    profile = get_profile(username)
    resume_text = get_resume_text(username)
    
    cand = profile.get("candidato", {})
    candidate_name = cand.get("nome_completo", username.capitalize())
    profile_summary = yaml.dump(profile, allow_unicode=True, sort_keys=False)
    
    system_prompt = f"""Você é o Copiloto IA de Candidaturas Profissionais do Hermes 2.0.
Sua missão é responder com máxima autoridade, naturalidade e precisão a qualquer pergunta, formulário ou teste de vaga que o candidato esteja preenchendo.

DADOS REAIS DO CANDIDATO:
Nome: {candidate_name}
Currículo Oficial:
---
{resume_text}
---
Configurações e Preferências:
---
{profile_summary}
---

DIRETRIZES DE RESPOSTA:
1. Responda em PRIMEIRA PESSOA ("Atuo...", "Minha experiência com...", "Implementei...").
2. Seja 100% autêntico e embasado nas tecnologias, métricas e projetos reais descritos no currículo. Não invente certificados ou empregos que não existem.
3. Se for uma pergunta dissertativa/cultural (ex: "Por que você quer trabalhar conosco?", "Descreva um desafio técnico superado", "Qual sua maior conquista?"):
   - Escreva um parágrafo objetivo, maduro, técnico e persuasivo.
4. Se for teste técnico ou de múltipla escolha:
   - Destaque no início a alternativa recomendada: **Opção Recomendada: [Alternativa]** seguido de breve justificativa técnica.
5. Se a imagem contiver múltiplos campos, organize com títulos claros para cada campo.
6. A formatação deve ser limpa para permitir COPIAR E COLAR diretamente no campo de resposta da vaga.
"""

    try:
        if image_bytes:
            user_instruction = (
                "Analise a imagem da tela com atenção. Identifique a pergunta, enunciado ou campo do formulário de vaga "
                "que precisa ser preenchido e elabore a resposta definitiva para eu copiar e colar agora."
            )
            if text_question and text_question.strip():
                user_instruction += f"\nObservação adicional do candidato: {text_question.strip()}"
                
            full_prompt = f"{system_prompt}\n\n{user_instruction}"
            answer = generate_with_image(full_prompt, image_bytes=image_bytes, mime_type=mime_type)
        elif text_question and text_question.strip():
            user_instruction = f"Pergunta / Campo do formulário para responder:\n\"{text_question.strip()}\""
            full_prompt = f"{system_prompt}\n\n{user_instruction}"
            answer = generate(full_prompt, smart=True, temperature=0.2)
        else:
            return {"success": False, "error": "Nenhuma imagem ou texto de pergunta foi fornecido."}

        return {
            "success": True,
            "username": username,
            "answer_markdown": answer,
            "copy_text": answer.strip()
        }

    except Exception as e:
        return {"success": False, "error": f"Erro ao processar resposta com a IA: {e}"}
