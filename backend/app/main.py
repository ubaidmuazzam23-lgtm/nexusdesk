# # File: backend/app/main.py

# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from app.core.config import settings
# from app.api.v1.routes import auth, admin, engineer, chat

# app = FastAPI(
#     title=settings.APP_NAME,
#     version="1.0.0",
#     docs_url="/docs",
#     redoc_url="/redoc"
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[settings.FRONTEND_URL],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(auth.router,     prefix="/api/v1")
# app.include_router(admin.router,    prefix="/api/v1")
# app.include_router(engineer.router, prefix="/api/v1")
# app.include_router(chat.router,     prefix="/api/v1")


# @app.get("/")
# async def root():
#     return {"status": "ok", "app": settings.APP_NAME}


# @app.get("/health")
# async def health():
#     return {"status": "healthy"}

# from app.api.v1.routes.analytics import router as analytics_router
# from app.api.v1.routes.knowledge  import router as knowledge_router
 
# # Add these include_router lines alongside your existing ones:
# app.include_router(analytics_router, prefix="/api/v1")
# app.include_router(knowledge_router,  prefix="/api/v1")
 
# File: backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.routes import auth, admin, engineer, chat
from app.api.v1.routes.analytics import router as analytics_router
from app.api.v1.routes.knowledge import router as knowledge_router
from app.api.v1.routes.model_stats import router as model_stats_router
from app.api.v1.routes.routing_simulator import router as routing_router



app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,          prefix="/api/v1")
app.include_router(admin.router,         prefix="/api/v1")
app.include_router(engineer.router,      prefix="/api/v1")
app.include_router(chat.router,          prefix="/api/v1")
app.include_router(analytics_router,     prefix="/api/v1")
app.include_router(knowledge_router,     prefix="/api/v1")
app.include_router(model_stats_router,   prefix="/api/v1")
app.include_router(routing_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health")
async def health():
    return {"status": "healthy"}