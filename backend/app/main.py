from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.funds import router as funds_router
from app.api.health import router as health_router
from app.api.portfolio import router as portfolio_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(funds_router)
app.include_router(portfolio_router)
