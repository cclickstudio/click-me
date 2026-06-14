import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
# .env 는 프로젝트 루트 우선(현 배치), 없으면 backend/.env.
_ROOT_ENV = _BACKEND_ROOT.parent / ".env"
load_dotenv(_ROOT_ENV if _ROOT_ENV.exists() else _BACKEND_ROOT / ".env")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("clickme")

# API 라우터 재구성 진행 중 — 현재 도메인 구조로 이전 완료된 라우터만 등록.
# (이전 평면 라우터 admin/ads/chat/generator/inquiries/personas/projects/simulate 는 이전 중.)
from api.routers.simulation.router import router as simulation_router
from core.config import settings

if not settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING_V2"] = "false"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ClickMe API",
    version="2.0.0",
    description="AI Ad Simulation Platform",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        "422 Validation error on %s %s — errors: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(simulation_router, prefix="/api/simulation", tags=["simulation"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0", "env": settings.app_env}
