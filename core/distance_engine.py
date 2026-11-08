"""
Calculador de Distância Geográfica e Validador de Modalidade - Hermes Job AI.
Calcula a distância aproximada entre a cidade/bairro do candidato e a localização da vaga.
"""

from typing import Dict, Any, Tuple

# Coordenadas aproximadas dos principais polos de SP / ABC para cálculo rápido offline
LOCALIDADES_SP = {
    "diadema": (-23.6865, -46.6234),
    "sao bernardo do campo": (-23.6914, -46.5646),
    "santo andre": (-23.6639, -46.5383),
    "sao caetano do sul": (-23.6229, -46.5546),
    "maua": (-23.6678, -46.4614),
    "sao paulo": (-23.5505, -46.6333),
    "faria lima": (-23.5796, -46.6896),
    "paulista": (-23.5614, -46.6559),
    "berrini": (-23.6083, -46.6974),
    "alphaville": (-23.4984, -46.8528),
    "barueri": (-23.5111, -46.8761),
    "osasco": (-23.5329, -46.7916),
    "guarulhos": (-23.4542, -46.5333),
    "campinas": (-22.9099, -47.0626),
    "santos": (-23.9608, -46.3336),
    "rio de janeiro": (-22.9068, -43.1729),
    "belo horizonte": (-19.9167, -43.9345),
    "curitiba": (-25.4284, -49.2733),
}


def haversine_distance_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calcula a distância em linha reta (em km) entre duas coordenadas geográficas."""
    import math
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371.0 # Raio da Terra em km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)


def estimate_distance_to_candidate(job_location: str, candidate_city: str = "Diadema") -> float:
    """
    Estima a distância em km a partir da localização da vaga.
    Retorna 0.0 se for remota ou desconhecida na mesma cidade.
    """
    if not job_location:
        return 0.0

    loc_lower = job_location.lower()
    cand_lower = candidate_city.lower()

    # Se a vaga for na mesma cidade do candidato
    if cand_lower in loc_lower:
        return 5.0 # Estimativa média dentro do município

    # Busca no mapa de polos conhecidos
    cand_coord = LOCALIDADES_SP.get(cand_lower, (-23.6865, -46.6234)) # Default Diadema

    for polo_name, polo_coord in LOCALIDADES_SP.items():
        if polo_name in loc_lower:
            return haversine_distance_km(cand_coord, polo_coord)

    # Se mencionar outro estado ou capital fora de SP (ex: PI, BA, CE, PE, RJ, MG, etc.)
    outros_estados = [
        " pi", " - pi", ", pi", "/pi", "teresina", "piauí", "piaui",
        " ce", " - ce", ", ce", "/ce", "fortaleza", "ceará", "ceara",
        " ba", " - ba", ", ba", "/ba", "salvador", "bahia",
        " pe", " - pe", ", pe", "/pe", "recife", "pernambuco",
        " ma", " - ma", ", ma", "/ma", "são luís", "maranhão",
        " rn", " - rn", ", rn", "/rn", "natal",
        " pb", " - pb", ", pb", "/pb", "joão pessoa",
        " se", " - se", ", se", "/se", "aracaju", "sergipe",
        " al", " - al", ", al", "/al", "maceió", "alagoas",
        " rj", " - rj", ", rj", "/rj", "rio de janeiro",
        " mg", " - mg", ", mg", "/mg", "belo horizonte", "minas gerais",
        " pr", " - pr", ", pr", "/pr", "curitiba", "paraná", "parana",
        " rs", " - rs", ", rs", "/rs", "porto alegre", "rio grande do sul",
        " sc", " - sc", ", sc", "/sc", "florianópolis", "santa catarina",
        " go", " - go", ", go", "/go", "goiânia", "goias",
        " df", " - df", ", df", "/df", "brasília", "distrito federal",
        " mt", " - mt", ", mt", "/mt", "cuiabá", "mato grosso",
        " ms", " - ms", ", ms", "/ms", "campo grande",
        " am", " - am", ", am", "/am", "manaus", "amazonas",
        " pa", " - pa", ", pa", "/pa", "belém", "pará"
    ]
    for uf in outros_estados:
        if uf in loc_lower:
            return 1200.0 # Claramente interestadual fora de SP

    return 25.0 # Média para Grande SP genérico


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
    salario_min_clt = float(financeiro.get("salario_minimo_clt", 0.0))
    if salary_max and salary_max > 0 and salary_max < salario_min_clt:
        return False, f"Salário oferecido (R$ {salary_max:.2f}) abaixo do mínimo exigido (R$ {salario_min_clt:.2f})"

    # 2. Regra de Modalidade & Distância
    is_remote = bool(job.get("is_remote", False))
    title_and_desc = (str(job.get("title", "")) + " " + str(job.get("description", ""))).lower()

    # Detecta se é Remoto
    if is_remote or "remoto" in title_and_desc or "home office" in title_and_desc:
        if not modalidades.get("remoto", {}).get("aceitar", True):
            return False, "Vaga remota recusada pelas suas configurações."
        return True, "Remoto: Aprovado"

    # Detecta se é Híbrido
    is_hybrid = "híbrido" in title_and_desc or "hibrido" in title_and_desc
    distancia_km = estimate_distance_to_candidate(job.get("location", ""), cand_cidade)

    if is_hybrid:
        cfg_hibrido = modalidades.get("hibrido", {})
        if not cfg_hibrido.get("aceitar", True):
            return False, "Vaga híbrida recusada pelas suas preferências."
        max_km = float(cfg_hibrido.get("distancia_maxima_km", 30))
        if distancia_km > max_km:
            return False, f"Híbrido muito distante: ~{distancia_km}km (limite configurado: {max_km}km)"
        return True, f"Híbrido viável (~{distancia_km}km)"

    # Se for 100% Presencial
    cfg_presencial = modalidades.get("presencial", {})
    if not cfg_presencial.get("aceitar", True):
        return False, "Vaga 100% presencial recusada pelas suas preferências."
    max_km_presencial = float(cfg_presencial.get("distancia_maxima_km", 15))
    if distancia_km > max_km_presencial:
        return False, f"Presencial muito distante: ~{distancia_km}km de casa (limite presencial: {max_km_presencial}km)"

    return True, f"Presencial próximo (~{distancia_km}km)"
