"""
Gerenciador do Banco de Dados SQLite para o Hermes Job AI.
Armazena vagas coletadas, pontuações de compatibilidade (ATS Score),
histórico de candidaturas e respostas de formulários.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "hermes.db")


def get_connection() -> sqlite3.Connection:
    """Cria o diretório se não existir e retorna conexão com o SQLite."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa as tabelas com suporte a concorrência rápida (WAL mode)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Ativa o modo WAL (Write-Ahead Logging) para alta performance
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Tabela de Vagas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                site TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                job_type TEXT,
                is_remote BOOLEAN DEFAULT 0,
                job_url TEXT UNIQUE NOT NULL,
                description TEXT,
                date_posted TEXT,
                salary_min REAL,
                salary_max REAL,
                
                # Campos de Inteligência (ATS)
                match_score INTEGER DEFAULT NULL,
                match_reasons TEXT DEFAULT NULL,
                keywords_found TEXT DEFAULT NULL,
                status TEXT DEFAULT 'discovered', -- discovered, reviewed, approved, applied, rejected, failed
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Tabela de Histórico de Candidaturas (Auditoria de respostas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                answers_json TEXT,
                screenshot_path TEXT,
                status TEXT NOT NULL, -- success, failed, requires_human
                error_message TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs (id)
            );
        """)
        
        conn.commit()


def save_jobs(jobs_list: List[Dict[str, Any]]) -> int:
    """Salva uma lista de vagas no banco ignorando duplicatas por URL."""
    if not jobs_list:
        return 0
        
    inserted_count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for job in jobs_list:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO jobs (
                        id, site, title, company, location, job_type,
                        is_remote, job_url, description, date_posted,
                        salary_min, salary_max
                    ) VALUES (
                        :id, :site, :title, :company, :location, :job_type,
                        :is_remote, :job_url, :description, :date_posted,
                        :salary_min, :salary_max
                    )
                """, job)
                if cursor.rowcount > 0:
                    inserted_count += 1
            except Exception as e:
                print(f"[Erro DB] Falha ao inserir vaga: {e}")
        conn.commit()
        
    return inserted_count


def get_pending_evaluations(limit: int = 50) -> List[Dict[str, Any]]:
    """Retorna vagas recém-descobertas que ainda não foram avaliadas pela LLM."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE match_score IS NULL 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def update_job_evaluation(job_id: str, score: int, reasons: str, keywords: str, status: str = 'reviewed'):
    """Atualiza a pontuação de compatibilidade gerada pela LLM."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE jobs 
            SET match_score = ?, match_reasons = ?, keywords_found = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (score, reasons, keywords, status, job_id))
        conn.commit()
