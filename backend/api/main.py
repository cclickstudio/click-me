import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("clickme")

from api.routers import (
    admin,
    ads,
    auth,
    chat,
    company,
    dashboard,
    generator,
    inquiries,
    personas,
    projects,
    simulate,
)
from core.config import settings
from domain.generator.adapters.instagram import load_meta_credentials
from tools.simulation.ssr_scorer import SSRScorer

if not settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING_V2"] = "false"

ssr_scorer = SSRScorer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    token, ig_user_id, _ = load_meta_credentials()
    if token and ig_user_id:
        logger.info("Instagram publisher: MetaGraph (ig_user_id=%s…)", ig_user_id[:6])
    else:
        logger.warning(
            "Instagram publisher: Mock — .env에 META_ACCESS_TOKEN, META_IG_USER_ID 설정 필요"
        )
    await ssr_scorer.precompute_anchors()
    app.state.ssr_scorer = ssr_scorer
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

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(company.router, prefix="/api/company", tags=["company"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(simulate.router, prefix="/api/simulate", tags=["simulate"])
app.include_router(ads.router, prefix="/api/ads", tags=["ads"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(inquiries.router, prefix="/api/inquiries", tags=["inquiries"])
app.include_router(personas.router, prefix="/api/personas", tags=["personas"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(generator.router, prefix="/api/generator", tags=["generator"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0", "env": settings.app_env}
