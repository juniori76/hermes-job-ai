"""
Manutenção: devolve para 'pendente' as vagas que receberam score falso
quando a IA estava com falha (fallback antigo gravava 50%).
Uso: python -m tools.reset_failed_scores
"""

from core.database import get_connection


def main():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE jobs
            SET match_score = NULL, match_reasons = NULL, keywords_found = NULL,
                status = 'discovered'
            WHERE match_reasons LIKE 'Falha na avalia%'
        """)
        conn.commit()
        print(f"Vagas devolvidas para reavaliação: {cur.rowcount}")


if __name__ == "__main__":
    main()
