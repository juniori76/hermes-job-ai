"""
Filtro de Relevância e Sanidade de Vagas - Hermes Job AI.
Impede a ingestão de anúncios aleatórios e vagas completamente fora da área dos candidatos
(ex: Mecânico de Refrigeração, Jovem Aprendiz de Lanchonete, Analista de Obras/Facilities).
"""

import re
import unicodedata
from typing import List, Optional, Set

# Termos que desqualificam a vaga imediatamente (trabalho manual, construção civil, alimentação, etc.)
UNWANTED_TITLE_BLACKLIST = [
    # Manutenção física, refrigeração e mecânica
    "refrigeracao", "refrigerador", "freezer", "ar condicionado", "mecanico",
    "eletromecanico", "torneiro", "soldador", "serralheiro", "funileiro",
    "manutencao predial", "hidraulico", "eletricista",
    
    # Construção, Obras, Facilities físico
    "obras", "construcao civil", "facilities", "engenheiro civil", "mestre de obras",
    
    # Serviços Gerais, Cozinha, Portaria
    "jovem aprendiz", "aprendiz", "menor aprendiz", "estagio ensino medio",
    "limpeza", "auxiliar de limpeza", "copeiro", "copeira", "cozinheiro", "cozinha", 
    "servicos gerais", "portaria", "porteiro", "vigilante", "zelador",
    
    # Vendas e atendimento presencial físico não-corporativo
    "lanchonete", "atendente de lanchonete", "caixa de supermercado", "balconista", "frentista",
    "motorista", "motoboy", "entregador", "ajudante de carga", "operador de empilhadeira",
    "corretor", "cabeleireiro", "barbeiro", "estetica", "manicure",
    
    # Áreas corporativas totalmente divergentes
    "sustentabilidade", "atuarial", "cro", "landing page", "compras", "suprimentos",
    "fiscal", "contabil", "folha de pagamento", "hospitalidade", "hotelaria", "camareira"
]

# Stop-words e prefixos hierárquicos genéricos que não definem a área técnica
GENERIC_TITLE_PREFIXES = {
    "analista", "assistente", "auxiliar", "especialista", "consultor", "consultora",
    "tecnico", "tecnica", "coordenador", "coordenadora", "gerente", "supervisor",
    "junior", "pleno", "senior", "estagiario", "estagiaria", "lider", "pessoa",
    "para", "com", "em", "de", "do", "da", "dos", "das", "e", "ou",
    "jr", "pl", "sr", "n1", "n2", "n3", "i", "ii", "iii", "iv"
}

# Domínios técnicos e administrativos aceitos no ecossistema Hermes
VALID_PROFESSIONAL_DOMAINS = [
    # TI, Infraestrutura, Redes, NOC, Suporte
    "ti", "suporte", "redes", "rede", "noc", "soc", "telecom", "telecomunicacoes",
    "infraestrutura", "infra", "sistemas", "seguranca", "ciberseguranca", "cloud",
    "nuvem", "linux", "windows", "devops", "monitoramento", "observabilidade",
    "helpdesk", "service desk", "field service", "informatica", "tecnologia",
    "datacenter", "banco de dados", "software", "desenvolvedor", "programador",
    
    # Administrativo, Backoffice, Relacionamento Corporativo
    "administrativo", "administrativa", "atendimento", "relacionamento",
    "backoffice", "recepcao", "recepcionista", "secretaria", "escritorio"
]


def strip_accents(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def is_job_title_acceptable(title: str, search_term: Optional[str] = None) -> bool:
    """
    Avalia se o título da vaga é aceitável para o perfil dos candidatos.
    Rejeita lixo comercial, vagas de mecânica/refrigeração/portaria/aprendiz e
    títulos que não pertencem a nenhuma das áreas profissionais cadastradas.
    """
    if not title:
        return False

    t_clean = strip_accents(title)

    # 1. Checagem imediata contra a Blacklist
    for blacklisted in UNWANTED_TITLE_BLACKLIST:
        if blacklisted in t_clean:
            return False

    # 2. Se a vaga tem apenas a palavra "analista" ou prefixo genérico sem qualificador aceito
    # Ex: "Analista de Obras", "Analista de Facilities" já caem na blacklist.
    # Ex: "Analista de Suporte", "Analista de Monitoramento" têm domínio válido.
    words = set(re.findall(r'\b[a-z]{2,}\b', t_clean))

    # Remove os prefixos genéricos
    meaningful_words = words - GENERIC_TITLE_PREFIXES

    # Se não sobrou nenhuma palavra técnica ou a vaga não bate em nenhum domínio profissional aceito
    matches_domain = any(domain in t_clean for domain in VALID_PROFESSIONAL_DOMAINS)
    if not matches_domain:
        return False

    # 3. Se um termo de busca específico foi fornecido (ex: "Analista de Monitoramento")
    if search_term:
        term_clean = strip_accents(search_term)
        term_meaningful = set(re.findall(r'\b[a-z]{3,}\b', term_clean)) - GENERIC_TITLE_PREFIXES
        
        # Se o termo tinha palavras específicas (ex: "monitoramento", "redes")
        if term_meaningful:
            # Pelo menos uma palavra do termo ou da área deve estar presente no título
            has_term_match = any(tw in t_clean for tw in term_meaningful)
            if not has_term_match:
                # Permite sinônimos técnicos diretos
                synonyms_map = {
                    "noc": ["monitoramento", "observabilidade", "redes", "telecom", "incidentes", "conectividade"],
                    "monitoramento": ["noc", "observabilidade", "infraestrutura", "suporte", "redes", "telecom", "ti"],
                    "redes": ["telecom", "noc", "infraestrutura", "cisco", "mikrotik", "conectividade", "suporte"],
                    "soc": ["seguranca", "siem", "incidentes", "ciberseguranca"],
                    "suporte": ["helpdesk", "service desk", "field service", "ti", "infraestrutura", "redes", "tecnico"],
                    "administrativo": ["recepcao", "atendimento", "backoffice", "escritorio"]
                }
                has_synonym = False
                for tm in term_meaningful:
                    if tm in synonyms_map:
                        if any(syn in t_clean for syn in synonyms_map[tm]):
                            has_synonym = True
                            break
                if not has_synonym:
                    return False

    return True
