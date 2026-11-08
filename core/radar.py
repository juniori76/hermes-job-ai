"""
Motor de Radar de Vagas - Hermes Job AI.
Utiliza a biblioteca JobSpy para coletar oportunidades em tempo real
no LinkedIn, Glassdoor e Indeed com base nos termos e localização.
"""

import os
import hashlib
import yaml
from typing import List, Dict, Any, Optional
from jobspy import scrape_jobs
from core.database import save_jobs, init_db
from core.gupy_radar import search_gupy_jobs
from core.brazilian_radars import search_vagas_com, search_infojobs
from core.profiles_manager import get_profile, list_profiles

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def load_profile(username: str = "eduardo") -> Dict[str, Any]:
    """Carrega o perfil do candidato específico ou padrão."""
    return get_profile(username)


def generate_job_id(site: str, job_url: str) -> str:
    """Gera um hash MD5 único baseado na URL para evitar duplicações."""
    return hashlib.md5(f"{site}_{job_url}".encode("utf-8")).hexdigest()


def scan_jobs(results_wanted_per_term: int = 15, custom_cargos: Optional[List[str]] = None) -> int:
    """
    Executa a varredura nos portais de emprego configurados.
    Retorna o número de novas vagas adicionadas ao banco.
    """
    init_db()
    profile = load_profile()
    prefs = profile.get("preferencias_de_vaga", {})
    candidato = profile.get("candidato", {})
    
    if custom_cargos and len(custom_cargos) > 0:
        cargos = custom_cargos
    else:
        # Varre automaticamente os cargos de TODOS os perfis da família cadastrados
        cargos_set = set()
        for p_meta in list_profiles():
            p_data = get_profile(p_meta["id"])
            p_cargos = p_data.get("preferencias_de_vaga", {}).get("cargos_alvo", [])
            for c in p_cargos:
                if c and c.strip():
                    cargos_set.add(c.strip())
        cargos = list(cargos_set) if cargos_set else prefs.get("cargos_alvo", ["Analista de Suporte", "Administrador de Redes"])
    localizacao = f"{candidato.get('cidade', 'São Paulo')}, {candidato.get('estado', 'SP')}, Brasil"
    is_remote = prefs.get("modalidades_aceitas", {}).get("remoto", True)
    distance_km = prefs.get("raio_maximo_km_hibrido", 30)
    
    # Converte km para milhas (o JobSpy espera distance em milhas)
    distance_miles = int(distance_km * 0.621371)
    
    total_novas = 0
    print(f"\n[Hermes Radar] 📡 Iniciando busca em {localizacao} (Raio: ~{distance_km}km)...")

    for cargo in cargos:
        print(f"[Hermes Radar] 🔍 Buscando vagas para: '{cargo}'...")
        try:
            # JobSpy faz scraping direto e seguro
            jobs_df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=cargo,
                location=localizacao,
                results_wanted=results_wanted_per_term,
                country_indeed='brazil',
                distance=distance_miles,
                is_remote=is_remote,
                easy_apply=True, # Apenas vagas com Candidatura Simplificada no LinkedIn!
                hours_old=24 # Vagas publicadas nas últimas 24 HORAS para ser o primeiro da fila!
            )

            if jobs_df is None or jobs_df.empty:
                print(f"[Hermes Radar] Nenhuma vaga nova encontrada para '{cargo}'.")
                continue

            vagas_formatadas: List[Dict[str, Any]] = []
            for _, row in jobs_df.iterrows():
                site = str(row.get("site", "web"))
                url = str(row.get("job_url", ""))
                if not url or url == "nan":
                    continue
                    
                loc_str = str(row.get("location", "") or "")
                loc_lower = loc_str.lower()
                is_rem = bool(row.get("is_remote", False))
                
                # Descarte de vagas internacionais fora do Brasil (ex: China, EUA, Índia)
                foreign_signals = ["china", "united states", "india", "europe", "germany", "canada", "mexico", "reino unido", "uk", "usa", "asia"]
                if any(fs in loc_lower for fs in foreign_signals) and not is_rem:
                    continue

                # Garante que seja no Brasil ou 100% Remoto
                is_brazil = any(bz in loc_lower for bz in ["brasil", "brazil", "sp", "são paulo", "sao paulo", "diadema", "abc", "santo andré", "são bernardo", "grande são paulo", "remote", "remoto"])
                if not is_brazil and not is_rem:
                    continue

                vaga = {
                    "id": generate_job_id(site, url),
                    "site": site,
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "Confidencial")),
                    "location": loc_str,
                    "job_type": str(row.get("job_type", "")),
                    "is_remote": is_rem,
                    "job_url": url,
                    "description": str(row.get("description", "")),
                    "date_posted": str(row.get("date_posted", "")),
                    "salary_min": float(row.get("min_amount")) if row.get("min_amount") and str(row.get("min_amount")) != "nan" else None,
                    "salary_max": float(row.get("max_amount")) if row.get("max_amount") and str(row.get("max_amount")) != "nan" else None,
                }
                vagas_formatadas.append(vaga)

            novas_inseridas = save_jobs(vagas_formatadas)
            total_novas += novas_inseridas
            print(f"[Hermes Radar] ✅ '{cargo}': {len(vagas_formatadas)} encontradas, {novas_inseridas} novas salvas no banco.")

        except Exception as e:
            print(f"[Hermes Radar ⚠️] Erro ao buscar '{cargo}': {e}")

        # Busca dedicada na Gupy
        try:
            print(f"[Hermes Radar] 🟣 Consultando portal Gupy para: '{cargo}'...")
            gupy_jobs = search_gupy_jobs(job_name=cargo, limit=15)
            if gupy_jobs:
                novas_gupy = save_jobs(gupy_jobs)
                total_novas += novas_gupy
                print(f"[Hermes Radar] ✅ Gupy '{cargo}': {len(gupy_jobs)} encontradas, {novas_gupy} novas salvas.")
        except Exception as eg:
            print(f"[Hermes Radar ⚠️] Erro na busca Gupy: {eg}")

        # Busca no Vagas.com.br
        try:
            print(f"[Hermes Radar] 🔵 Consultando Vagas.com.br para: '{cargo}'...")
            vagas_jobs = search_vagas_com(term=cargo, limit=15)
            if vagas_jobs:
                novas_v = save_jobs(vagas_jobs)
                total_novas += novas_v
                print(f"[Hermes Radar] ✅ Vagas.com '{cargo}': {len(vagas_jobs)} encontradas, {novas_v} novas salvas.")
        except Exception as ev:
            print(f"[Hermes Radar ⚠️] Erro na busca Vagas.com: {ev}")

        # Busca no InfoJobs Brasil
        try:
            print(f"[Hermes Radar] 🟠 Consultando InfoJobs Brasil para: '{cargo}'...")
            info_jobs = search_infojobs(term=cargo, limit=15)
            if info_jobs:
                novas_i = save_jobs(info_jobs)
                total_novas += novas_i
                print(f"[Hermes Radar] ✅ InfoJobs '{cargo}': {len(info_jobs)} encontradas, {novas_i} novas salvas.")
        except Exception as ei:
            print(f"[Hermes Radar ⚠️] Erro na busca InfoJobs: {ei}")

    print(f"\n[Hermes Radar] 🎯 Varredura concluída. Total de novas vagas registradas: {total_novas}\n")
    return total_novas


if __name__ == "__main__":
    scan_jobs()
