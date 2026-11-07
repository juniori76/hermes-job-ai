"""
Ponto de Entrada Principal - Hermes Job AI.
Inicia o servidor Web FastAPI para o Dashboard e orquestra
as rotinas em background.
"""

import os
import uvicorn
from dotenv import load_dotenv
from core.database import init_db

load_dotenv()

PORT = int(os.getenv("PORT", 8088))
HOST = os.getenv("HOST", "0.0.0.0")

if __name__ == "__main__":
    # Garante que as tabelas do banco estejam criadas
    init_db()
    
    print(f"\n=======================================================")
    print(f"🚀 Hermes Job AI rodando com sucesso!")
    print(f"📡 Painel Web acessível em: http://localhost:{PORT}")
    print(f"🌐 No servidor acesse em: http://192.168.0.123:{PORT}")
    print(f"=======================================================\n")
    
    uvicorn.run("web.app:app", host=HOST, port=PORT, reload=False)
