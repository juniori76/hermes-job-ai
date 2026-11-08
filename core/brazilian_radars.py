"""
Radares Nacionais de Vagas (Vagas.com.br & InfoJobs Brasil) - Hermes 2.0.
Varredura direta via HTTP com alta performance, sem necessidade de navegador headless,
sem risco de bloqueios de login e sem captchas.
"""

import urllib.request
import urllib.parse
import hashlib
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _clean_text(text: str) -> str:
    """Remove excesso de espaços e quebras de linha."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def search_vagas_com(term: str, location: str = "sao-paulo", limit: int = 15) -> List[Dict[str, Any]]:
    """
    Varre o portal Vagas.com.br para o termo e localidade solicitados.
    """
    slug_term = urllib.parse.quote(term.lower().replace(" ", "-"))
    slug_loc = urllib.parse.quote(location.lower().replace(" ", "-"))
    url = f"https://www.vagas.com.br/vagas-de-{slug_term}-em-{slug_loc}"

    vagas: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("li.vaga")

        for art in articles[:limit]:
            a_tag = art.find("a", class_=lambda c: c and "link-detalhes" in c.lower())
            if not a_tag or not a_tag.get("href"):
                continue

            raw_href = a_tag.get("href")
            job_url = f"https://www.vagas.com.br{raw_href}" if raw_href.startswith("/") else raw_href
            title = _clean_text(a_tag.get_text())

            # Empresa
            emp_el = art.find(class_=lambda c: c and ("empr" in c.lower() or "empresa" in c.lower()))
            company = _clean_text(emp_el.get_text()) if emp_el else "Confidencial"

            # Localização / Nível
            loc_el = art.find(class_=lambda c: c and ("local" in c.lower() or "regiao" in c.lower()))
            job_loc = _clean_text(loc_el.get_text()) if loc_el else "Grande São Paulo, SP"

            # Descrição rápida
            det_el = art.find("div", class_=lambda c: c and "detalhes" in c.lower())
            desc = _clean_text(det_el.get_text()) if det_el else title

            # Detecta se é remoto
            is_remote = any(k in (title + " " + desc).lower() for k in ["remoto", "home office", "teletrabalho", "100% remoto"])

            job_id = hashlib.md5(f"vagas.com_{job_url}".encode("utf-8")).hexdigest()

            vagas.append({
                "id": job_id,
                "site": "vagas.com",
                "title": title,
                "company": company,
                "location": job_loc,
                "job_type": "CLT",
                "is_remote": is_remote,
                "job_url": job_url,
                "description": desc,
                "date_posted": "Recente",
                "salary_min": None,
                "salary_max": None,
            })

    except Exception as e:
        print(f"[Vagas.com Radar ⚠️] Erro ao buscar '{term}': {e}")

    return vagas


def search_infojobs(term: str, location: str = "sao-paulo,-sp", limit: int = 15) -> List[Dict[str, Any]]:
    """
    Varre o portal InfoJobs Brasil para o termo e localidade solicitados.
    """
    slug_term = urllib.parse.quote(term.lower().replace(" ", "-"))
    slug_loc = urllib.parse.quote(location.lower().replace(" ", "-"))
    url = f"https://www.infojobs.com.br/vagas-de-emprego-{slug_term}-em-{slug_loc}.aspx"

    vagas: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        soup = BeautifulSoup(html, "html.parser")
        seen_urls = set()

        # Localiza links de vagas
        links = soup.find_all("a", href=lambda h: h and "/vaga-de-" in h)
        for a_tag in links:
            raw_href = a_tag.get("href")
            if not raw_href or raw_href in seen_urls:
                continue

            title = _clean_text(a_tag.get_text())
            if not title or len(title) < 4:
                continue

            seen_urls.add(raw_href)
            job_url = f"https://www.infojobs.com.br{raw_href}" if raw_href.startswith("/") else raw_href

            # Tenta capturar o container pai da vaga para ler empresa e localização
            card = a_tag.find_parent("div")
            company = "Empresa Confidencial"
            job_loc = "São Paulo, SP"
            desc = title

            if card:
                full_card_text = _clean_text(card.get_text())
                if len(full_card_text) > len(desc):
                    desc = full_card_text

            is_remote = any(k in (title + " " + desc).lower() for k in ["remoto", "home office", "teletrabalho"])
            job_id = hashlib.md5(f"infojobs_{job_url}".encode("utf-8")).hexdigest()

            vagas.append({
                "id": job_id,
                "site": "infojobs",
                "title": title,
                "company": company,
                "location": job_loc,
                "job_type": "CLT",
                "is_remote": is_remote,
                "job_url": job_url,
                "description": desc[:800],
                "date_posted": "Recente",
                "salary_min": None,
                "salary_max": None,
            })

            if len(vagas) >= limit:
                break

    except Exception as e:
        print(f"[InfoJobs Radar ⚠️] Erro ao buscar '{term}': {e}")

    return vagas
