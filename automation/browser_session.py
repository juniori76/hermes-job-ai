"""
Gerenciador de sessão do navegador (Playwright) com perfil persistente.
Mantém cookies/logins (LinkedIn, Gupy, etc.) em data/browser_profile.
"""

import os
import random
import time
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, BrowserContext, Page

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE_DIR, "data", "browser_profile")


def human_pause(min_s: float = 0.6, max_s: float = 1.8):
    """Pausa aleatória para simular comportamento humano."""
    time.sleep(random.uniform(min_s, max_s))


def human_type(page: Page, selector: str, text: str):
    """Digita caractere a caractere com atraso variável."""
    page.click(selector)
    page.fill(selector, "")
    for ch in text:
        page.keyboard.type(ch, delay=random.randint(30, 110))
    human_pause(0.3, 0.8)


@contextmanager
def open_session(headless: bool = True):
    """
    Abre o navegador reutilizando o perfil salvo.
    headless=False é usado só no primeiro login manual (setup).
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with sync_playwright() as p:
        context: BrowserContext = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=headless,
            viewport={"width": 1366, "height": 850},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield context
        finally:
            context.close()


def manual_login_setup():
    """Abre o navegador visível para você logar uma única vez nos sites."""
    print("Abrindo navegador. Faça login no LinkedIn/Gupy e feche a janela quando terminar.")
    with open_session(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        page.wait_for_event("close", timeout=0)


if __name__ == "__main__":
    manual_login_setup()
