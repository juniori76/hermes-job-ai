"""
Conector Gupy - Hermes Job AI.
A API JSON pública não existe mais (retorna HTML/404). O portal é Next.js com
renderização no servidor: a lista de vagas vem embutida em __NEXT_DATA__
(pageProps.initialJobList.data), então basta uma requisição HTTP simples.
"""

import re
import json
import hashlib
from typing import List, Dict, Any
from urllib.parse import quote

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def generate_gupy_id(job_id: Any) -> str:
    return hashlib.md5(f"gupy_{job_id}".encode("utf-8")).hexdigest()


def search_gupy_jobs(job_name: str, limit: int = 12, remote_only: bool = False) -> List[Dict[str, Any]]:
    url = f"https://portal.gupy.io/job-search/term={quote(job_name)}"
    if remote_only:
        url += "&workplaceTypes[]=remote"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"[Gupy] HTTP {resp.status_code} para '{job_name}'")
            return []
        m = NEXT_DATA_RE.search(resp.text)
        if not m:
            print("[Gupy] Estrutura da página mudou (__NEXT_DATA__ ausente).")
            return []
        items = json.loads(m.group(1))["props"]["pageProps"]["initialJobList"]["data"]
    except Exception as e:
        print(f"[Gupy] Erro na consulta de '{job_name}': {e}")
        return []

    jobs: List[Dict[str, Any]] = []
    for item in items[:limit]:
        jid = item.get("id")
        if not jid:
            continue
        city, state = item.get("city") or "", item.get("state") or ""
        wt = (item.get("workplaceType") or "").lower()
        jobs.append({
            "id": generate_gupy_id(jid),
            "site": "gupy",
            "title": item.get("name", ""),
            "company": item.get("careerPageName", "Empresa Gupy"),
            "location": f"{city} - {state}".strip(" -") or "Brasil",
            "job_type": item.get("type", ""),
            "is_remote": wt == "remote",
            "job_url": item.get("jobUrl") or f"https://portal.gupy.io/job/{jid}",
            "description": item.get("description", "") or "",
            "date_posted": item.get("publishedDate", ""),
            "salary_min": None,
            "salary_max": None,
        })
    return jobs


if __name__ == "__main__":
    for j in search_gupy_jobs("suporte de ti"):
        print(j["company"], "|", j["title"], "|", j["location"], "|", j["job_url"])
