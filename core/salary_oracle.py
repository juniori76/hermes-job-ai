"""
Módulo Salary Oracle (Oráculo Salarial) - Hermes Job AI
Calcula a faixa de remuneração de mercado para cada vaga com base em:
1. Salário real divulgado pela empresa (se houver).
2. Histórico de vagas semelhantes no banco de dados SQLite do Hermes.
3. Tabela de benchmark salarial de TI e Administrativo no Estado de São Paulo / Brasil.
4. Modificadores de competências técnicas (ex: MikroTik, Firewall, Zabbix, Virtualização).
"""

import re
from typing import Dict, Any, Optional

# Tabela base de remuneração média de mercado (Região Metropolitana de SP / Remoto nacional)
ROLE_BENCHMARKS = [
    # TI - Infra / Redes / Suporte
    (r"(estagi[aá]rio|estagio).*(ti|redes|suporte|infra)", 1500, 2200, "Estágio"),
    (r"(suporte.*(n1|1|t[eé]cnico|helpdesk)|t[eé]cnico.*(suporte|inform[aá]tica)).*jr", 2600, 3600, "Júnior"),
    (r"(suporte.*(n1|1|helpdesk)|t[eé]cnico.*inform[aá]tica)", 2400, 3400, "Operacional"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*jr", 3200, 4400, "Júnior"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*pl", 4500, 6200, "Pleno"),
    (r"(analista.*ti|analista.*suporte|suporte.*ti).*sr", 6500, 8800, "Sênior"),
    (r"(analista.*infra|analista.*redes|infraestrutura).*jr", 3500, 4800, "Júnior"),
    (r"(analista.*infra|analista.*redes|infraestrutura).*pl", 5000, 7200, "Pleno"),
    (r"(analista.*infra|analista.*redes|infraestrutura).*sr", 7500, 10500, "Sênior"),
    (r"(administrador.*redes|sysadmin|administrador.*sistemas).*pl", 5500, 7800, "Pleno"),
    (r"(administrador.*redes|sysadmin|administrador.*sistemas)", 4800, 7200, "Especialista"),
    (r"(seguran[çc]a da informa[çc][aã]o|cybersecurity|soc)", 5500, 8500, "Pleno"),
    (r"(coordenador|supervisor|l[ií]der t[eé]cnico).*(ti|infra|suporte)", 8000, 13000, "Gestão"),

    # Administrativo / Operacional (Ex: Perfil Rute)
    (r"(jovem aprendiz|aprendiz)", 800, 1300, "Aprendiz"),
    (r"(recepcionista|atendente|telefonista)", 1800, 2600, "Operacional"),
    (r"(auxiliar.*administrativ|assistente.*administrativ.*jr)", 2200, 3200, "Júnior"),
    (r"(assistente.*administrativ|analista.*administrativ.*jr)", 2600, 3600, "Júnior"),
    (r"(analista.*administrativ.*pl|analista.*financeir.*pl)", 3800, 5200, "Pleno"),
    (r"(analista.*administrativ|analista.*financeir)", 3200, 4800, "Pleno"),
    (r"(faturamento|fiscal|cont[aá]bil)", 2800, 4200, "Técnico"),
]

# Modificadores de valorização por habilidades técnicas de alto valor agregado
SKILL_MODIFIERS = [
    (r"(mikrotik|mtcna|routeros)", 0.08, "MikroTik"),
    (r"(fortinet|firewall|fortigate|pfsense)", 0.08, "Firewall/Segurança"),
    (r"(zabbix|grafana|prometheus)", 0.06, "Observabilidade"),
    (r"(vmware|esxi|proxmox|hyper-v)", 0.07, "Virtualização"),
    (r"(microsoft 365|office 365|ms-900|azure)", 0.06, "Cloud M365/Azure"),
    (r"(active directory|gpo|windows server)", 0.05, "Windows Server/AD"),
    (r"(n8n|python|powershell|automa[çc])", 0.05, "Automação"),
]


def estimate_job_salary(job: Dict[str, Any], historical_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Retorna a inteligência salarial da vaga.
    Retorna dict com:
    - has_explicit_salary: bool
    - min_val: float
    - max_val: float
    - display_text: str (Ex: 'R$ 4.000 – R$ 5.200')
    - badge_html_text: str
    - badge_type: 'real' | 'estimate' | 'unknown'
    - explanation: str
    """
    sal_min = float(job.get("salary_min") or 0.0)
    sal_max = float(job.get("salary_max") or 0.0)

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
            "explanation": "Salário oficial informado no anúncio da vaga pela empresa."
        }

    # 2. Se não tem salário divulgado, inferir pelo mercado + senioridade + skills
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    full_text = f"{title} {desc}"

    matched_min = 3000.0
    matched_max = 4200.0
    matched_label = "Média de Mercado SP"
    rule_found = False

    for pattern, b_min, b_max, label in ROLE_BENCHMARKS:
        if re.search(pattern, title):
            matched_min = float(b_min)
            matched_max = float(b_max)
            matched_label = f"Média {label} em SP"
            rule_found = True
            break

    # Se não achou no título, busca palavras-chave no texto geral
    if not rule_found:
        for pattern, b_min, b_max, label in ROLE_BENCHMARKS:
            if re.search(pattern, desc[:500]):
                matched_min = float(b_min)
                matched_max = float(b_max)
                matched_label = f"Estimativa {label}"
                rule_found = True
                break

    # Aplica modificadores de skills de alta complexidade
    bonus_multiplier = 0.0
    skills_boosted = []
    for pattern, boost, skill_name in SKILL_MODIFIERS:
        if re.search(pattern, full_text):
            bonus_multiplier += boost
            skills_boosted.append(skill_name)

    # Limita o bônus a no máximo +30%
    bonus_multiplier = min(bonus_multiplier, 0.30)
    final_min = round((matched_min * (1.0 + bonus_multiplier)) / 100) * 100
    final_max = round((matched_max * (1.0 + bonus_multiplier)) / 100) * 100

    display = f"R$ {final_min:,.0f} – R$ {final_max:,.0f}".replace(",", ".")
    boost_desc = f" (+{len(skills_boosted)} skills de alto valor)" if skills_boosted else ""

    return {
        "has_explicit_salary": False,
        "min_val": final_min,
        "max_val": final_max,
        "display_text": display,
        "badge_html_text": f"💰 Est. {display}",
        "badge_css": "bg-indigo-500/10 text-indigo-300 border-indigo-500/30",
        "badge_type": "estimate",
        "explanation": f"Estimativa de mercado em SP para este cargo{boost_desc}. A empresa não divulgou o valor oficial."
    }
