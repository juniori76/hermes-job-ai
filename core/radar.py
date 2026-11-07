"""
Motor de Radar de Vagas - Hermes Job AI.
Utiliza a biblioteca JobSpy para coletar oportunidades em tempo real
no LinkedIn, Glassdoor e Indeed com base nos termos e localização.
"""

import os
import hashlib
import yaml
from typing import List, Dict, Any
from jobspy import scrape_jobs
from core.database import save_jobs, init_db
from core.gupy_radar import search_gupy_jobs

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def load_profile() -> Dict[str, Any]:
    """Carrega o perfil do candidato (se o real não existir, carrega o example)."""
    real_profile = os.path.join(CONFIG_PATH, "candidate_profile.yaml")
    example_profile = os.path.join(CONFIG_PATH, "candidate_profile.example.yaml")
    
    target_file = real_profile if os.path.exists(real_profile) else example_profile
    with open(target_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_job_id(site: str, job_url: str) -> str:
    """Gera um hash MD5 único baseado na URL para evitar duplicações."""
    return hashlib.md5(f"{site}_{job_url}".encode("utf-8")).hexdigest()


def scan_jobs(results_wanted_per_term: int = 15) -> int:
    """
    Executa a varredura nos portais de emprego configurados.
    Retorna o número de novas vagas adicionadas ao banco.
    """
    init_db()
    profile = load_profile()
    prefs = profile.get("preferencias_de_vaga", {})
    candidato = profile.get("candidato", {})
    
    cargos = prefs.get("cargos_alvo", ["Analista de Suporte", "Administrador de Redes"])
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
                site_name=["linkedin", "glassdoor", "indeed"],
                search_term=cargo,
                location=localizacao,
                results_wanted=results_wanted_per_term,
                country_indeed='brazil',
                distance=distance_miles,
                is_remote=is_remote,
                hours_old=72 # Apenas vagas recentes dos últimos 3 dias
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
                    
                vaga = {
                    "id": generate_job_id(site, url),
                    "site": site,
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "Confidencial")),
                    "location": str(row.get("location", "")),
                    "job_type": str(row.get("job_type", "")),
                    "is_remote": bool(row.get("is_remote", False)),
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

    print(f"\n[Hermes Radar] 🎯 Varredura concluída. Total de novas vagas registradas: {total_novas}\n")
    return total_novas


if __name__ == "__main__":
    scan_jobs()
