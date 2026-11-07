"""
Diagnóstico da IA: mede latência e testa chave/modelos configurados.
Uso: python -m tools.llm_check
"""

import time
from core import config, llm


def main():
    print("Chave configurada:", config.has_api_key())
    for smart in (False, True):
        name = config.get("GEMINI_MODEL_SMART" if smart else "GEMINI_MODEL_FAST")
        t = time.time()
        try:
            out = llm.generate("Responda apenas: ok", smart=smart, retries=1)
            print(f"[OK ] {name}: {time.time() - t:.1f}s -> {out[:40]!r}")
        except Exception as e:
            print(f"[ERR] {name}: {time.time() - t:.1f}s -> {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    main()
