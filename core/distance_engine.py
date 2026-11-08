"""
Calculador de Distância Geográfica e Validador de Modalidade - Hermes Job AI.
Calcula a distância aproximada entre a cidade/bairro do candidato e a localização da vaga.
Suporta normalização de acentos, detecção por polos e validação precisa de UFs interestaduais.
"""

import math
import unicodedata
import re
from typing import Dict, Any, Tuple

# Coordenadas aproximadas dos principais polos de SP / ABC para cálculo rápido offline
LOCALIDADES_SP = {
    "diadema": (-23.6865, -46.6234),
    "sao bernardo do campo": (-23.6914, -46.5646),
    "sao bernardo": (-23.6914, -46.5646),
    "santo andre": (-23.6639, -46.5383),
    "sao caetano do sul": (-23.6229, -46.5546),
    "sao caetano": (-23.6229, -46.5546),
    "maua": (-23.6678, -46.4614),
    "ribeirao pires": (-23.7139, -46.4136),
    "sao paulo": (-23.5505, -46.6333),
    "zona sul": (-23.6300, -46.6700),
    "jabaquara": (-23.6450, -46.6430),
    "saude": (-23.6150, -46.6390),
    "vila mariana": (-23.5890, -46.6380),
    "faria lima": (-23.5796, -46.6896),
    "paulista": (-23.5614, -46.6559),
    "berrini": (-23.6083, -46.6974),
    "itaim bibi": (-23.5850, -46.6800),
    "pinheiros": (-23.5670, -46.7020),
    "morumbi": (-23.6000, -46.7200),
    "chacara santo antonio": (-23.6260, -46.7040),
    "santo amaro": (-23.6520, -46.7080),
    "brooklin": (-23.6150, -46.6900),
    "alphaville": (-23.4984, -46.8528),
    "barueri": (-23.5111, -46.8761),
    "osasco": (-23.5329, -46.7916),
    "guarulhos": (-23.4542, -46.5333),
    "taboao da serra": (-23.6080, -46.7570),
    "cotia": (-23.6030, -46.9190),
    "santana de parnaiba": (-23.4440, -46.9180),
    "campinas": (-22.9099, -47.0626),
    "santos": (-23.9608, -46.3336),
    "rio de janeiro": (-22.9068, -43.1729),
    "belo horizonte": (-19.9167, -43.9345),
    "curitiba": (-25.4284, -49.2733),
}


def _strip_accents(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def haversine_distance_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calcula a distância em linha reta (em km) entre duas coordenadas geográficas."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371.0  # Raio da Terra em km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)


def estimate_distance_to_candidate(job_location: str, candidate_city: str = "Diadema") -> float:
    """
    Estima a distância em km a partir da localização da vaga.
    Retorna 0.0 se for remota ou na mesma cidade do candidato.
    """
    if not job_location:
        return 0.0

    loc_clean = _strip_accents(job_location)
    cand_clean = _strip_accents(candidate_city)

    # 1. Se for na mesma cidade do candidato
    if cand_clean and cand_clean in loc_clean:
        return 5.0  # Estimativa média intra-município

    # 2. Coordenadas da residência base do candidato (default Diadema)
    cand_coord = LOCALIDADES_SP.get(cand_clean, (-23.6865, -46.6234))

    # 3. Busca primeiro pelos polos conhecidos de SP / Grande SP
    for polo_name, polo_coord in LOCALIDADES_SP.items():
        if polo_name in loc_clean:
            return haversine_distance_km(cand_coord, polo_coord)

    # 4. Se a vaga contém menção explícita a SP ou São Paulo e não achou bairro específico
    if re.search(r'\b(sp|sao paulo)\b', loc_clean):
        # Média para a Região Metropolitana de São Paulo
        return 16.0

    # 5. Detecção de outros estados interestaduais (fora de SP) com regex rigorosa (sem falso positivo em "paulo" ou "proximas")
    outros_estados_pattern = r'\b(pi|ce|ba|pe|ma|rn|pb|se|al|rj|mg|pr|rs|sc|go|df|mt|ms|am|pa|ac|ro|rr|ap|to)\b'
    capitais_fora = [
        "teresina", "fortaleza", "salvador", "recife", "sao luis", "natal", "joao pessoa",
        "aracaju", "maceio", "rio de janeiro", "belo horizonte", "curitiba", "porto alegre",
        "florianopolis", "goiania", "brasilia", "cuiaba", "campo grande", "manaus", "belem"
    ]

    for cap in capitais_fora:
        if cap in loc_clean:
            return 1200.0

    # Verifica se há sigla de outro estado explicitamente separada (ex: " - RJ", ", PR", "/BA")
    match_uf = re.search(r'[-/,\s]\s*' + outros_estados_pattern + r'(\s+brasil|\s*$)', loc_clean)
    if match_uf:
        sigla = match_uf.group(1)
        if sigla != "sp":
            return 1200.0

    # Padrão seguro para vagas sem estado explícito mas sem polo reconhecido
    return 25.0


def validate_job_policy(job: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Valida se a vaga obedece à política de Modalidade, Raio de Distância e Salário Mínimo.
    Retorna (True, "") se for válida ou (False, "motivo do descarte").
    """
    prefs = profile.get("preferencias_de_vaga", {})
    modalidades = prefs.get("modalidades", {})
    financeiro = prefs.get("financeiro", {})
    cand_cidade = profile.get("candidato", {}).get("cidade", "Diadema")

    # 1. Regra de Salário Mínimo (se a vaga informar salário máximo)
    salary_max = job.get("salary_max")
    salario_min_clt = float(financeiro.get("salario_minimo_clt", 0.0) or 0.0)
    if salary_max and salary_max > 0 and salario_min_clt > 0 and salary_max < salario_min_clt:
        return False, f"Salário oferecido (R$ {salary_max:.2f}) abaixo do mínimo exigido (R$ {salario_min_clt:.2f})"

    # 2. Regra de Modalidade & Distância
    is_remote = bool(job.get("is_remote", False))
    title_and_desc = (str(job.get("title", "")) + " " + str(job.get("description", ""))).lower()

    # Detecta se é Remoto
    if is_remote or "remoto" in title_and_desc or "home office" in title_and_desc:
        if not modalidades.get("remoto", {}).get("aceitar", True):
            return False, "Candidato não aceita vagas remotas"
        return True, ""  # Remoto 100% liberado

    # Detecta se é Híbrido
    is_hybrid = "hibrid" in title_and_desc or "híbrid" in title_and_desc
    dist_km = estimate_distance_to_candidate(job.get("location", ""), cand_cidade)

    if is_hybrid:
        if not modalidades.get("hibrido", {}).get("aceitar", True):
            return False, "Candidato não aceita vagas híbridas"
        max_km = float(modalidades.get("hibrido", {}).get("distancia_maxima_km", 30.0) or 30.0)
        if dist_km > max_km:
            return False, f"Híbrido muito distante: ~{dist_km}km de casa (limite híbrido: {max_km}km)"
        return True, ""

    # Presencial Convencional
    if not modalidades.get("presencial", {}).get("aceitar", True):
        return False, "Candidato não aceita vagas 100% presenciais"

    max_km = float(modalidades.get("presencial", {}).get("distancia_maxima_km", 18.0) or 18.0)
    if dist_km > max_km:
        return False, f"Presencial muito distante: ~{dist_km}km de casa (limite presencial: {max_km}km)"

    return True, ""
