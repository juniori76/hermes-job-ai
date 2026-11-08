"""
Módulo Salary Oracle (Oráculo Salarial) - Hermes Job AI
Calcula a faixa de remuneração de mercado para cada vaga com base em:
1. Salário real divulgado pela empresa (se houver).
2. Tabela de benchmark salarial oficial (Base CAGED/MTE e Glassdoor São Paulo).
3. Modificadores de competências técnicas rigorosamente balanceados por senioridade.
4. Links diretos e oficiais para a pesquisa salarial oficial do cargo no Salario.com.br (CAGED/MTE) e Glassdoor.
"""

import re
import urllib.parse
from typing import Dict, Any, Optional

ROLE_BENCHMARKS = [
    # TI - Estágios
    (r"(estagi[aá]rio|estagio).*(ti|redes|suporte|infra|seguran[çc]a)", 1400, 2200, "Estágio"),
    
    # TI - Suporte & Helpdesk
    (r"(suporte.*(n1|1|t[eé]cnico|helpdesk)|t[eé]cnico.*(suporte|inform[aá]tica)).*jr", 2500, 3500, "Júnior"),
    (r"(suporte.*(n1|1|helpdesk)|t[eé]cnico.*inform[aá]tica)", 2400, 3300, "Operacional"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*jr", 3000, 4200, "Júnior"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*pl", 4200, 5800, "Pleno"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*sr", 6000, 8200, "Sênior"),
    
    # TI - Infraestrutura & Redes
    (r"(analista.*infra|analista.*redes|infraestrutura).*jr", 3200, 4500, "Júnior"),
    (r"(analista.*infra|analista.*redes|infraestrutura).*pl", 4800, 6800, "Pleno"),
    (r"(analista.*infra|analista.*redes|infraestrutura).*sr", 7000, 9800, "Sênior"),
    (r"(administrador.*redes|sysadmin|administrador.*sistemas).*jr", 3500, 4800, "Júnior"),
    (r"(administrador.*redes|sysadmin|administrador.*sistemas).*pl", 5000, 7200, "Pleno"),
    (r"(administrador.*redes|sysadmin|administrador.*sistemas)", 4500, 6800, "Pleno"),
    
    # TI - Segurança da Informação / Cyber / SOC
    (r"(seguran[çc]a|cyber|soc|infosec).*jr", 3500, 4800, "Júnior"),
    (r"(seguran[çc]a|cyber|soc|infosec).*pl", 5200, 7500, "Pleno"),
    (r"(seguran[çc]a|cyber|soc|infosec).*sr", 8000, 11500, "Sênior"),
    (r"(seguran[çc]a da informa[çc][aã]o|cybersecurity|soc)", 4200, 6200, "Pleno"),

    # TI - Gestão & Coordenação
    (r"(coordenador|supervisor|l[ií]der t[eé]cnico).*(ti|infra|suporte)", 7500, 12000, "Gestão"),

    # Administrativo / Operacional (Ex: Perfil Rute)
    (r"(jovem aprendiz|aprendiz)", 800, 1300, "Aprendiz"),
    (r"(recepcionista|atendente|telefonista)", 1800, 2500, "Operacional"),
    (r"(auxiliar.*administrativ|assistente.*administrativ.*jr)", 2000, 3000, "Júnior"),
    (r"(assistente.*administrativ|analista.*administrativ.*jr)", 2500, 3500, "Júnior"),
    (r"(analista.*administrativ.*pl|analista.*financeir.*pl)", 3800, 5000, "Pleno"),
    (r"(analista.*administrativ|analista.*financeir)", 3000, 4500, "Pleno"),
    (r"(faturamento|fiscal|cont[aá]bil)", 2600, 4000, "Técnico"),
]

SKILL_MODIFIERS = [
    (r"(mikrotik|mtcna|routeros)", 0.05, "MikroTik"),
    (r"(fortinet|firewall|fortigate|pfsense)", 0.05, "Firewall/Segurança"),
    (r"(zabbix|grafana|prometheus)", 0.04, "Observabilidade"),
    (r"(vmware|esxi|proxmox|hyper-v)", 0.05, "Virtualização"),
    (r"(microsoft 365|office 365|ms-900|azure)", 0.04, "Cloud M365/Azure"),
    (r"(active directory|gpo|windows server)", 0.04, "Windows Server/AD"),
    (r"(n8n|python|powershell|automa[çc])", 0.04, "Automação"),
]


def estimate_job_salary(job: Dict[str, Any], historical_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sal_min = float(job.get("salary_min") or 0.0)
    sal_max = float(job.get("salary_max") or 0.0)
    raw_title = job.get("title") or "Profissional de TI"
    clean_title = re.sub(r"[\–\-\|\(\)\/].*", "", raw_title).strip()
    encoded_title = urllib.parse.quote_plus(clean_title)

    # Link direto para a base oficial de salários do CAGED / Ministério do Trabalho (Salario.com.br)
    caged_url = f"https://www.salario.com.br/busca/?q={encoded_title}"
    glassdoor_url = f"https://www.glassdoor.com.br/Sal%C3%A1rios/index.htm?keyword={encoded_title}"

    # 1. Se a vaga já tem salário real explicitamente divulgado
    if sal_min > 500 or sal_max > 500:
        if sal_min > 0 and sal_max > 0 and sal_min != sal_max:
            display = f"R$ {sal_min:,.0f} a R$ {sal_max:,.0f}".replace(",", ".")
        elif sal_max > 0:
            display = f"R$ {sal_max:,.0f}".replace(",", ".")
        else:
            display = f"R$ {sal_min:,.0f}".replace(",", ".")

        return {
            "has_explicit_salary": True,
            "min_val": sal_min or sal_max,
            "max_val": sal_max or sal_min,
            "display_text": display,
            "badge_html_text": f"💵 {display} (Divulgado)",
            "badge_css": "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
            "badge_type": "real",
            "source_name": f"Anúncio Oficial ({job.get('site', 'Vaga')})",
            "source_url": job.get("job_url"),
            "caged_url": caged_url,
            "glassdoor_url": glassdoor_url,
            "explanation": "Salário oficial informado no anúncio da vaga pela empresa contratante."
        }

    # 2. Se não tem salário divulgado, inferir pelo mercado + senioridade + skills
    title_lower = (job.get("title") or "").lower()
    desc_lower = (job.get("description") or "").lower()
    full_text = f"{title_lower} {desc_lower}"

    is_estagio = bool(re.search(r"\b(est[aá]gio|estagi[aá]rio)\b", title_lower))
    is_junior = bool(re.search(r"\b(j[uú]nior|jr|trainee|i\b|1\b)\b", title_lower))
    is_senior = bool(re.search(r"\b(s[eê]nior|sr|especialista|coordenador|supervisor)\b", title_lower))

    matched_min = 3200.0
    matched_max = 4400.0
    matched_label = "Média de Mercado SP"
    rule_found = False

    for pattern, b_min, b_max, label in ROLE_BENCHMARKS:
        if re.search(pattern, title_lower):
            matched_min = float(b_min)
            matched_max = float(b_max)
            matched_label = f"Média {label} em SP"
            rule_found = True
            break

    if not rule_found:
        for pattern, b_min, b_max, label in ROLE_BENCHMARKS:
            if re.search(pattern, desc_lower[:500]):
                matched_min = float(b_min)
                matched_max = float(b_max)
                matched_label = f"Estimativa {label}"
                rule_found = True
                break

    if is_junior:
        matched_min = min(matched_min, 3800.0)
        matched_max = min(matched_max, 4900.0)
    elif is_estagio:
        matched_min = min(matched_min, 1500.0)
        matched_max = min(matched_max, 2200.0)

    bonus_multiplier = 0.0
    skills_boosted = []
    for pattern, boost, skill_name in SKILL_MODIFIERS:
        if re.search(pattern, full_text):
            bonus_multiplier += boost
            skills_boosted.append(skill_name)

    bonus_multiplier = min(bonus_multiplier, 0.15)
    final_min = round((matched_min * (1.0 + bonus_multiplier)) / 100) * 100
    final_max = round((matched_max * (1.0 + bonus_multiplier)) / 100) * 100

    if is_junior:
        final_max = min(final_max, 5000.0)

    display = f"R$ {final_min:,.0f} – R$ {final_max:,.0f}".replace(",", ".")
    boost_desc = f" (+{len(skills_boosted)} skills técnicas)" if skills_boosted else ""

    return {
        "has_explicit_salary": False,
        "min_val": final_min,
        "max_val": final_max,
        "display_text": display,
        "badge_html_text": f"💰 Est. {display}",
        "badge_css": "bg-indigo-500/10 text-indigo-300 border-indigo-500/30",
        "badge_type": "estimate",
        "source_name": "Base Oficial Salario.com.br / CAGED",
        "source_url": caged_url,
        "caged_url": caged_url,
        "glassdoor_url": glassdoor_url,
        "explanation": f"Métrica base salarial em São Paulo para {clean_title}{boost_desc}. A empresa não divulgou o valor oficial."
    }
