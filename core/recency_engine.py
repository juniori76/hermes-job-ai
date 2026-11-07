"""
Calculador de Recência de Vagas - Hermes Job AI.
Converte datas relativas (ex: 'há 2 horas', 'há 30 minutos', '2026-11-06')
em idade real para priorizar vagas recém-abertas no topo da fila.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple


def calculate_job_age_hours(date_posted_str: str) -> float:
    """
    Retorna a idade aproximada da vaga em horas.
    Exemplos aceitos: 'há 2 horas', 'há 45 minutos', 'há 1 dia', '2026-11-06T14:30:00'
    """
    if not date_posted_str:
        return 999.0

    raw = str(date_posted_str).lower().strip()

    # Formatos em minutos
    m_min = re.search(r'(\d+)\s*(min|minuto)', raw)
    if m_min:
        return round(int(m_min.group(1)) / 60.0, 2)

    # Formatos em horas (ex: 'há 3 horas', '2h')
    m_hora = re.search(r'(\d+)\s*(h|hora)', raw)
    if m_hora:
        return float(m_hora.group(1))

    # Formatos em dias (ex: 'há 1 dia', '2 dias')
    m_dia = re.search(r'(\d+)\s*(d|dia)', raw)
    if m_dia:
        return float(int(m_dia.group(1)) * 24.0)

    # Formatos ISO de data (ex: '2026-11-06T18:00:00')
    try:
        clean_date = raw.split(".")[0].replace("z", "")
        if "t" in clean_date:
            dt = datetime.fromisoformat(clean_date)
        else:
            dt = datetime.strptime(clean_date[:10], "%Y-%m-%d")
        diff = datetime.now() - dt
        return max(0.1, round(diff.total_seconds() / 3600.0, 1))
    except Exception:
        pass

    return 24.0 # Padrão para datas genéricas


def format_job_badge(age_hours: float) -> Tuple[str, str, str]:
    """
    Retorna (texto_badge, classe_css, icone) para exibição na Dashboard.
    """
    if age_hours <= 2.0:
        mins = int(age_hours * 60)
        return (f"🔥 Aberta há {max(5, mins)} min", "bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse font-black", "fa-solid fa-fire")
    elif age_hours <= 6.0:
        return (f"⚡ Aberta há {int(age_hours)}h (Top Prioridade)", "bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold", "fa-solid fa-bolt")
    elif age_hours <= 24.0:
        return (f"🕒 Hoje ({int(age_hours)}h atrás)", "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 font-medium", "fa-regular fa-clock")
    elif age_hours <= 48.0:
        return ("Ontem", "bg-slate-800 text-slate-400 border-slate-700", "fa-regular fa-calendar")
    else:
        dias = int(age_hours / 24)
        return (f"{dias} dias atrás", "bg-slate-900 text-slate-500 border-slate-800", "fa-regular fa-calendar-xmark")
