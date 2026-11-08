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
                
                -- Campos de Inteligencia (ATS)
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

        # Tabela de Reputação e Saúde de Empresas (Company Health Insights)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_insights (
                company_clean TEXT PRIMARY KEY,
                company_display TEXT NOT NULL,
                rating REAL,
                rating_label TEXT,
                sentiment TEXT,
                pros TEXT,
                cons TEXT,
                culture_summary TEXT,
                is_confidential BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Tabela do Funil / Histórico de Gestão de Candidaturas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'eduardo',
                job_title TEXT NOT NULL,
                company TEXT NOT NULL,
                site TEXT,
                job_url TEXT,
                match_score INTEGER DEFAULT 0,
                stage TEXT NOT NULL DEFAULT 'em_processo', -- em_processo, entrevista, desclassificado, aprovado
                notes TEXT DEFAULT '',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, user_id)
            );
        """)

        # Auto-migra vagas antigas marcadas como applied para o funil
        cursor.execute("""
            INSERT OR IGNORE INTO job_applications (job_id, user_id, job_title, company, site, job_url, match_score, stage, applied_at)
            SELECT id, 'eduardo', title, company, site, job_url, COALESCE(match_score, 0), 'em_processo', updated_at
            FROM jobs
            WHERE status IN ('applied', 'success');
        """)

        # Migração: Coluna target_user para isolamento estrito por perfil
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN target_user TEXT DEFAULT 'eduardo';")
        except Exception:
            pass

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_target_user ON jobs(target_user);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(match_score);")

        # Atualiza vagas antigas sem target_user definido
        try:
            cursor.execute("SELECT id, title, description, keywords_found FROM jobs WHERE target_user IS NULL OR target_user = '';")
            unrouted = cursor.fetchall()
            if unrouted:
                from core.profiles_manager import list_profiles
                from core.telegram_multi_router import route_job_to_user
                cached_profiles = list_profiles()
                for r in unrouted:
                    jid, jtitle, jdesc, jkw = r["id"], r["title"], r["description"], r["keywords_found"]
                    assigned_u = route_job_to_user({"title": jtitle, "description": jdesc, "keywords_found": jkw}, cached_profiles)
                    cursor.execute("UPDATE jobs SET target_user = ? WHERE id = ?", (assigned_u, jid))
        except Exception as e:
            print(f"[DB Migration ⚠️] Erro ao rotear vagas: {e}")
        
        conn.commit()


def save_jobs(jobs_list: List[Dict[str, Any]]) -> int:
    """Salva uma lista de vagas no banco ignorando duplicatas por URL e vinculando ao perfil apropriado."""
    if not jobs_list:
        return 0
        
    inserted_count = 0
    from core.profiles_manager import list_profiles
    from core.telegram_multi_router import route_job_to_user
    cached_profiles = list_profiles()

    with get_connection() as conn:
        cursor = conn.cursor()
        for job in jobs_list:
            try:
                if not job.get("target_user"):
                    job["target_user"] = route_job_to_user(job, cached_profiles)
                cursor.execute("""
                    INSERT OR IGNORE INTO jobs (
                        id, site, title, company, location, job_type,
                        is_remote, job_url, description, date_posted,
                        salary_min, salary_max, target_user
                    ) VALUES (
                        :id, :site, :title, :company, :location, :job_type,
                        :is_remote, :job_url, :description, :date_posted,
                        :salary_min, :salary_max, :target_user
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


def record_application(job_id: str, user_id: str = "eduardo", stage: str = "em_processo", notes: str = "") -> Dict[str, Any]:
    """Registra ou atualiza a candidatura de um candidato para uma vaga no pipeline."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Puxa dados da vaga se existir
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job_row = cursor.fetchone()
        
        if job_row:
            job_dict = dict(job_row)
            job_title = job_dict.get("title") or "Vaga sem título"
            company = job_dict.get("company") or "Empresa não informada"
            site = job_dict.get("site") or "Outro"
            job_url = job_dict.get("job_url") or ""
            match_score = job_dict.get("match_score") or 0
        else:
            job_title = "Vaga Externa"
            company = "Empresa"
            site = "Web"
            job_url = ""
            match_score = 0
            
        cursor.execute("""
            INSERT INTO job_applications (
                job_id, user_id, job_title, company, site, job_url, match_score, stage, notes, applied_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id, user_id) DO UPDATE SET
                stage = excluded.stage,
                notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE job_applications.notes END,
                updated_at = CURRENT_TIMESTAMP
        """, (job_id, user_id, job_title, company, site, job_url, match_score, stage, notes))
        
        # Também atualiza o status na tabela principal de jobs
        cursor.execute("UPDATE jobs SET status = 'applied', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        conn.commit()
        
        return {
            "success": True,
            "job_id": job_id,
            "user_id": user_id,
            "stage": stage
        }


def get_user_applications(user_id: Optional[str] = None, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retorna o histórico de candidaturas com filtros por usuário e estágio do funil."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM job_applications WHERE 1=1"
        params = []
        
        if user_id and user_id != "all":
            query += " AND user_id = ?"
            params.append(user_id)
            
        if stage and stage != "all":
            query += " AND stage = ?"
            params.append(stage)
            
        query += " ORDER BY applied_at DESC"
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def update_application_stage(app_id: int, stage: str, notes: Optional[str] = None) -> bool:
    """Atualiza o estágio da candidatura (ex: em_processo, entrevista, desclassificado, aprovado)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if notes is not None:
            cursor.execute("""
                UPDATE job_applications 
                SET stage = ?, notes = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (stage, notes, app_id))
        else:
            cursor.execute("""
                UPDATE job_applications 
                SET stage = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (stage, app_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_application(app_id: int) -> bool:
    """Exclui uma candidatura do histórico."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_applications WHERE id = ?", (app_id,))
        conn.commit()
        return cursor.rowcount > 0
