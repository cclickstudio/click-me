import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
# .env 는 프로젝트 루트 우선(현 배치), 없으면 backend/.env.
_ROOT_ENV = _BACKEND_ROOT.parent / ".env"
load_dotenv(_ROOT_ENV if _ROOT_ENV.exists() else _BACKEND_ROOT / ".env")

# langsmith ↔ langchain_core 순환 import(tracers.context) 선해소.
# 시뮬/제너는 asyncio.gather로 트레이싱된 LLM 호출을 동시 실행하는데, 이때
# langchain_core.tracers.context를 여러 코루틴이 첫 import하면 부분 초기화 모듈을
# 관측해 "No module named 'langchain_core.tracers.context'"가 발생한다.
# 서버 시작 시 단일 스레드에서 미리 완전 import 해 race를 제거한다.
import langchain_core.tracers.context  # noqa: E402,F401
import langchain_core.tracers.langchain  # noqa: E402,F401
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("clickme")

# 시뮬레이션은 도메인 구조 라우터(api/routers/simulation)를 사용 — 구 simulate 라우터 대체.
from api.routers import (
    admin,
    ads,
    auth,
    billing,
    chat,
    company,
    dashboard,
    debate,
    generator,
    inquiries,
    management,
    personas,
    projects,
)
from api.routers.simulation.router import router as simulation_router
from core.config import settings
from domain.generator.adapters.instagram import load_meta_credentials

if not settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGSMITH_TRACING_V2"] = "false"
else:
    # 별칭(LANGCHAIN_*/LANGSMITH_*)으로 해석된 값을 SDK 표준 변수로 주입 — 어느 쪽 이름을 써도 동작
    os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    os.environ["LANGSMITH_TRACING"] = "true" if settings.LANGSMITH_TRACING_V2 else "false"

    # 전역 트레이싱 클라이언트를 기밀 마스킹 콜백과 함께 1회 생성한다. LangChain 트레이서와
    # @traceable이 이 캐시 클라이언트를 공유하므로, 부모(re_evaluate)·진단·재생성 자식 트레이스
    # 전부에서 예산·크리에이티브가 전송 전에 가려진다(평문 외부 유출 차단).
    from langsmith.run_trees import get_cached_client

    from core.trace_redaction import redact

    get_cached_client(hide_inputs=redact, hide_outputs=redact)


@asynccontextmanager
async def lifespan(app: FastAPI):
    token, ig_user_id, _ = load_meta_credentials()
    if token and ig_user_id:
        logger.info("Instagram publisher: MetaGraph (ig_user_id=%s…)", ig_user_id[:6])
    else:
        logger.warning(
            "Instagram publisher: Mock — .env에 META_ACCESS_TOKEN, META_IG_USER_ID 설정 필요"
        )
    # 어시스턴트 영속 체크포인터(Neon) 준비 — 실패하면 MemorySaver 폴백(앱은 계속 뜬다).
    from domain.management.assistant.checkpointer import (
        close_pg_checkpointer,
        init_pg_checkpointer,
    )

    await init_pg_checkpointer(settings.database_url)
    yield
    await close_pg_checkpointer()


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
    # exc.errors()에는 model_validator가 던진 ValueError 등 직렬화 불가 객체가 ctx에 섞일 수 있다.
    # jsonable_encoder 없이 그대로 넘기면 JSONResponse 인코딩이 깨져
    # CORS 헤더 없는 빈 응답이 나가고 프론트는 "Failed to fetch"만 본다.
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


app.add_middleware(
    CORSMiddleware,
    # Starlette는 allow_origins에 glob(*)을 지원하지 않으므로 vercel 서브도메인은 regex로 매칭
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(company.router, prefix="/api/company", tags=["company"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(simulation_router, prefix="/api/simulation", tags=["simulation"])
app.include_router(ads.router, prefix="/api/ads", tags=["ads"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(inquiries.router, prefix="/api/inquiries", tags=["inquiries"])
app.include_router(personas.router, prefix="/api/personas", tags=["personas"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(management.router, prefix="/api/management", tags=["management"])
app.include_router(generator.router, prefix="/api/generator", tags=["generator"])
app.include_router(debate.router, prefix="/api/debate", tags=["debate"])
app.include_router(chat.assistant_router, prefix="/api/assistant", tags=["assistant"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0", "env": settings.app_env}
