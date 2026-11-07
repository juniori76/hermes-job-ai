"""
Conector da API da Gupy - Hermes Job AI.
Consulta a API pública do portal da Gupy para capturar vagas
em tempo real no Brasil com filtros de cargo e modalidade.
"""

import requests
import hashlib
from typing import List, Dict, Any


def generate_gupy_id(job_id: int) -> str:
    return hashlib.md5(f"gupy_{job_id}".encode("utf-8")).hexdigest()


def search_gupy_jobs(job_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Busca vagas no portal oficial da Gupy via API pública.
    """
    url = "https://portal.gupy.io/api/v1/jobs"
    params = {
        "jobName": job_name,
        "limit": limit,
        "offset": 0
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"[Gupy API ⚠️] Status code inesperado: {resp.status_code}")
            return []

        data = resp.json()
        results = data.get("data", [])
        formatted_jobs = []

        for item in results:
            job_id = item.get("id")
            if not job_id:
                continue

            # Monta localização
            city = item.get("city", "")
            state = item.get("state", "")
            location = f"{city} - {state}" if city and state else (city or state or "Brasil")

            workplace_type = item.get("workplaceType", "").lower()
            is_remote = workplace_type in ["remote", "remoto"]

            job_url = item.get("jobUrl") or f"https://portal.gupy.io/job/{job_id}"

            formatted_jobs.append({
                "id": generate_gupy_id(job_id),
                "site": "gupy",
                "title": item.get("name", ""),
                "company": item.get("careerPageName", "Empresa Gupy"),
                "location": location,
                "job_type": item.get("type", "Efetivo"),
                "is_remote": is_remote,
                "job_url": job_url,
                "description": item.get("description", "") or item.get("prerequisites", ""),
                "date_posted": item.get("publishedDate", ""),
                "salary_min": None,
                "salary_max": None
            })

        return formatted_jobs

    except Exception as e:
        print(f"[Gupy API ⚠️] Erro na consulta de '{job_name}': {e}")
        return []
