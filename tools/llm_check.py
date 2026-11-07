"""
Diagnóstico da IA: testa chave e vários modelos candidatos, medindo latência.
Uso: python -m tools.llm_check
"""

import time
from google.genai import types
from core import config, llm

CANDIDATES = [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    "gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite", "gemini-3.1-pro-preview", "gemini-pro-latest",
    "gemini-2.5-pro", "gemini-4-argon",
]


def main():
    print("Chave configurada:", config.has_api_key())
    client = llm.get_client()
    for name in CANDIDATES:
        t = time.time()
        try:
            r = client.models.generate_content(
                model=name, contents="Responda apenas: ok",
                config=types.GenerateContentConfig(temperature=0))
            print(f"[OK ] {name}: {time.time() - t:.1f}s -> {r.text.strip()[:30]!r}")
        except Exception as e:
            msg = str(e).replace("\n", " ")
            code = next((c for c in ("429", "503", "404", "403", "400") if msg.startswith(c)), "ERR")
            print(f"[{code}] {name}: {time.time() - t:.1f}s -> {msg[:90]}")


if __name__ == "__main__":
    main()
