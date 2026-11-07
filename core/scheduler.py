"""
Agendador de Tarefas 24/7 - Hermes Job AI.
Executa varreduras e triagens em intervalos inteligentes,
priorizando horários humanos e respeitando a máquina doméstica.
"""

import os
import time
import random
from datetime import datetime
from dotenv import load_dotenv

from core.database import init_db, get_connection
from core.radar import scan_jobs
from core.ats_brain import run_ats_evaluation_batch
from core.notifier import notify_high_score_job

load_dotenv()

# Configurações de Intervalo (em segundos)
INTERVAL_SCAN_HOURS = float(os.getenv("INTERVAL_SCAN_HOURS", 2.0)) # A cada 2 horas
PAUSE_NIGHT = os.getenv("PAUSE_NIGHT", "true").lower() == "true"   # Pausa entre 23h e 07h


def is_working_hours() -> bool:
    """Verifica se está em horário comercial/diurno para parecer comportamento humano."""
    if not PAUSE_NIGHT:
        return True
    current_hour = datetime.now().hour
    # Ativo entre 07:00 e 22:59
    return 7 <= current_hour <= 22


def check_and_notify_top_jobs():
    """Busca vagas recentes com nota >= 80% que ainda não foram notificadas."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE match_score >= 80 
              AND status IN ('reviewed', 'approve')
            ORDER BY match_score DESC 
            LIMIT 5;
        """)
        top_jobs = [dict(row) for row in cursor.fetchall()]
        
        for job in top_jobs:
            notify_high_score_job(job)


def run_cycle():
    """Executa um ciclo completo: Radar -> IA Gemini -> Notificação."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Iniciando ciclo do Hermes...")
    
    # 1. Coleta novas vagas
    new_jobs = scan_jobs(results_wanted_per_term=12)
    
    # 2. Se achou vagas novas, avalia com Gemini Flash
    if new_jobs > 0:
        time.sleep(2)
        run_ats_evaluation_batch(batch_size=25)
        # 3. Notifica pelo Telegram se encontrou vagas excelentes
        check_and_notify_top_jobs()
    else:
        print("[Hermes Scheduler] Nenhuma vaga nova neste ciclo.")


def start_scheduler():
    """Loop contínuo 24/7 com intervalos humanos e sem sobrecarregar o servidor."""
    init_db()
    print("[Hermes Scheduler] ⏳ Agendador 24/7 iniciado no servidor.")
    
    while True:
        try:
            if is_working_hours():
                run_cycle()
            else:
                print(f"[{datetime.now().strftime('%H:%M')}] 🌙 Horário noturno de repouso (anti-detecção). Dormindo...")

            # Intervalo com pequena variação aleatória (jitter) para evitar padrões robóticos
            jitter = random.randint(-300, 300) # +/- 5 minutos
            sleep_seconds = max(1800, int(INTERVAL_SCAN_HOURS * 3600) + jitter)
            
            print(f"[Hermes Scheduler] Próximo ciclo em aproximadamente {sleep_seconds // 60} minutos.\n")
            time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            print("\n[Hermes Scheduler] Encerrado pelo usuário.")
            break
        except Exception as e:
            print(f"[Hermes Scheduler ⚠️] Erro inesperado no ciclo: {e}")
            time.sleep(600) # Espera 10 minutos antes de tentar novamente se houver falha de rede


if __name__ == "__main__":
    start_scheduler()
