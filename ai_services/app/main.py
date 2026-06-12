import os
from fastapi import FastAPI

_DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

app = FastAPI(
    title="AI IT Support — AI Services",
    version="1.0.0",
    docs_url="/docs" if _DEBUG else None,
    redoc_url="/redoc" if _DEBUG else None,
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "AI Services"}

@app.get("/health")
async def health():
    anthropic_key_ok = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    chroma_ok = False
    try:
        import chromadb
        chroma_path = os.environ.get("CHROMA_DIR", "data/knowledge_base")
        chromadb.PersistentClient(path=chroma_path)
        chroma_ok = True
    except Exception:
        pass

    all_ok = anthropic_key_ok and chroma_ok
    return {
        "status":       "healthy" if all_ok else "degraded",
        "anthropic_key": anthropic_key_ok,
        "chroma":        chroma_ok,
    }
