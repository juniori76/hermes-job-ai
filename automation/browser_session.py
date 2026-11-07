"""
Gerenciador de sessão do navegador (Playwright) com perfil persistente.
Mantém cookies/logins (LinkedIn, Gupy, etc.) em data/browser_profile.
Conecta-se ao DISPLAY virtual :99 para permitir visualização via noVNC (porta 6080).
Protegido contra concorrência e travamentos de perfil.
"""

import os
import random
import time
import subprocess
from typing import Dict
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, BrowserContext, Page

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE_DIR, "data", "browser_profile")


def human_pause(min_s: float = 0.6, max_s: float = 1.8):
    """Pausa aleatória para simular comportamento humano natural."""
    time.sleep(random.uniform(min_s, max_s))


def human_type(page: Page, selector: str, text: str):
    """Digita caractere a caractere com atraso variável simulando digitação humana."""
    page.click(selector)
    page.fill(selector, "")
    for ch in text:
        page.keyboard.type(ch, delay=random.randint(30, 110))
    human_pause(0.3, 0.8)


def _kill_stale_chrome():
    """Finaliza processos órfãos do Chrome para evitar conflito de concorrência."""
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.4)
    except Exception:
        pass


def _clear_singleton_locks():
    """Remove symlinks de trava de instâncias anteriores e reseta status de crash."""
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = os.path.join(PROFILE_DIR, lock_name)
        try:
            if os.path.islink(lock_path) or os.path.exists(lock_path):
                os.unlink(lock_path)
        except Exception:
            pass

    # Previne a mensagem 'Restore pages? Chromium didn't shut down correctly'
    pref_file = os.path.join(PROFILE_DIR, "Default", "Preferences")
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as pf:
                content = pf.read()
            if '"exit_type":"Crashed"' in content or '"exited_cleanly":false' in content:
                content = content.replace('"exit_type":"Crashed"', '"exit_type":"Normal"')
                content = content.replace('"exited_cleanly":false', '"exited_cleanly":true')
                with open(pref_file, "w", encoding="utf-8") as pf:
                    pf.write(content)
        except Exception:
            pass


@contextmanager
def open_session(headless: bool = False):
    """
    Abre o navegador reutilizando o perfil persistente de cookies.
    Por padrão roda headless=False conectando ao DISPLAY=:99 (Xvfb virtual),
    o que permite acompanhar tudo ao vivo via noVNC na porta 6080!
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _clear_singleton_locks()
    
    with sync_playwright() as p:
        context: BrowserContext = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=headless,
            viewport={"width": 1366, "height": 850},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
                "--no-first-run",
                "--start-maximized"
            ],
        )
        try:
            yield context
        finally:
            try:
                context.close()
            except Exception:
                pass
            _clear_singleton_locks()


def check_auth_status() -> Dict[str, bool]:
    """
    Verifica se existem sessões ativas e válidas para o LinkedIn e a Gupy.
    Primeiro verifica o banco de cookies do Chromium (instantâneo, sem abrir janela).
    Se inconclusivo, faz verificação rápida via Playwright.
    """
    status = {"linkedin": False, "gupy": False}
    
    # Método 1: Verificação direta via SQLite de cookies do Chromium
    cookie_paths = [
        os.path.join(PROFILE_DIR, "Default", "Network", "Cookies"),
        os.path.join(PROFILE_DIR, "Default", "Cookies"),
    ]
    for cp in cookie_paths:
        if os.path.exists(cp):
            try:
                import sqlite3, shutil
                tmp_db = "/tmp/hermes_chk_cookies.db" if os.name != "nt" else os.path.join(PROFILE_DIR, "chk_cookies.db")
                shutil.copy2(cp, tmp_db)
                conn = sqlite3.connect(tmp_db)
                cur = conn.cursor()
                
                # Check LinkedIn
                cur.execute("SELECT name FROM cookies WHERE host_key LIKE '%linkedin%'")
                li_names = {r[0] for r in cur.fetchall()}
                if "li_at" in li_names:
                    status["linkedin"] = True
                
                # Check Gupy (procura tokens reais de sessão, não apenas cookies de analytics)
                cur.execute("SELECT name FROM cookies WHERE host_key LIKE '%gupy%'")
                gu_names = {r[0] for r in cur.fetchall()}
                gupy_auth_keys = {"auth_token", "jwt_token", "gupy_session", "candidate_token", "user_id", "access_token"}
                if gu_names.intersection(gupy_auth_keys):
                    status["gupy"] = True
                    
                conn.close()
                if os.path.exists(tmp_db):
                    os.remove(tmp_db)
            except Exception as ce:
                print(f"[Auth Status] Aviso check cookies db: {ce}")
                
    if status["linkedin"] and status["gupy"]:
        return status

    # Método 2: Verificação rápida via Playwright se ainda houver dúvida
    try:
        with open_session(headless=True) as ctx:
            page = ctx.new_page()

            # Checagem LinkedIn
            if not status["linkedin"]:
                try:
                    page.goto("https://www.linkedin.com/feed/", timeout=10000)
                    human_pause(1.0, 1.8)
                    if "/feed" in page.url or "/in/" in page.url:
                        status["linkedin"] = True
                except Exception:
                    pass

            # Checagem Gupy
            if not status["gupy"]:
                try:
                    page.goto("https://portal.gupy.io/", timeout=10000)
                    human_pause(1.0, 1.8)
                    content = page.content().lower()
                    if "minhas candidaturas" in content or "sair" in content or "meu perfil" in content:
                        status["gupy"] = True
                except Exception:
                    pass

    except Exception as e:
        print(f"[Auth Status ⚠️] Erro ao verificar sessões: {e}")

    return status


def launch_assisted_login(platform: str = "linkedin"):
    """
    Abre o navegador no DISPLAY=:99 apontando para a página de login da plataforma desejada.
    Limpa instâncias anteriores, abre a página e monitora até que o usuário conclua o login.
    Assim que o login for detectado, aguarda a gravação dos cookies e encerra limpo.
    """
    url_map = {
        "linkedin": "https://www.linkedin.com/login",
        "gupy": "https://portal.gupy.io/login",
        "indeed": "https://secure.indeed.com/auth",
    }
    target_url = url_map.get(platform, "https://www.linkedin.com/login")
    
    # Finaliza qualquer sessão travada anterior
    _kill_stale_chrome()
    _clear_singleton_locks()
    
    with open_session(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(target_url)
        print(f"[Assisted Login] Navegador aberto em {target_url}. Acesse o noVNC (porta 6080) para logar.")
        
        # Aguarda interação e detecta conclusão do login
        start_time = time.time()
        while time.time() - start_time < 600:
            human_pause(3.0, 4.5)
            try:
                cur_url = (page.url or "").lower()
                if platform == "linkedin":
                    if "/feed" in cur_url or "/in/" in cur_url or "/mynetwork" in cur_url:
                        print("[Assisted Login] ✅ Login no LinkedIn concluído com sucesso!")
                        human_pause(3.0, 5.0)
                        break
                elif platform == "gupy":
                    if "portal.gupy.io" in cur_url and "/login" not in cur_url:
                        content = page.content().lower()
                        if "minhas candidaturas" in content or "sair" in content or "meu perfil" in content:
                            print("[Assisted Login] ✅ Login na Gupy concluído com sucesso!")
                            human_pause(3.0, 5.0)
                            break
            except Exception:
                break
