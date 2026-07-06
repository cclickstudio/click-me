import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

# Windows 콘솔(cp949 등) 코드페이지에서 한글·em-dash 같은 비ASCII print가
# UnicodeEncodeError로 백그라운드 태스크를 죽이지 않도록 표준 출력을 UTF-8로 고정한다.
# (서버 로그 인코딩은 OS 콘솔 코드페이지와 무관해야 함. pytest 캡처 등 reconfigure 불가 환경은 무시)
for _stream in (sys.stdout, sys.stderr):
    with suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")

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

# Windows 한정: 챗 오케스트레이터 체크포인터(langgraph AsyncPostgresSaver→psycopg async)는
# 기본 ProactorEventLoop에서 InterfaceError를 내고, AsyncConnectionPool이 이를 재시도하다
# 30초 PoolTimeout으로 가린다. SelectorEventLoop를 강제해 회피(배포 타깃 Linux EC2는 무영향).
# 백엔드에 asyncio subprocess 사용처가 없어 selector 정책의 subprocess 비활성화 영향도 없음.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("clickme")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # 서드파티 라이브러리 INFO 로그까지 켜지 않도록 "clickme" 로거에만 핸들러를 붙인다
    # (logging.basicConfig는 root에 적용돼 botocore·sqlalchemy 등도 시끄러워짐).
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)

# 시뮬레이션은 도메인 구조 라우터(api/routers/simulation)를 사용 — 구 simulate 라우터 대체.
from api.routers import (
    admin,
    ads,
    auth,
    automation,
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
    # 능동 매니지먼트 스케줄러 — 기본 off(management_scheduler_enabled일 때만 기동).
    from domain.management.scheduler import start_scheduler  # noqa: PLC0415

    start_scheduler(settings)

    # 제너레이터 자동화 스케줄러 — 기본 off(generator_scheduler_enabled일 때만 기동).
    from domain.generator.scheduler import (
        start_scheduler as start_generator_scheduler,  # noqa: PLC0415
    )

    start_generator_scheduler(settings)

    # KB 인제스터 — 비차단 백그라운드 태스크(서버 시작 안 막음). 키 없으면 graceful 스킵.
    async def _run_kb_ingest() -> None:
        # fire-and-forget 태스크라 런타임 예외를 여기서 잡아 로깅한다.
        # (안 잡으면 "Task exception was never retrieved"로 조용히 사라져 KB가 미적재됨)
        try:
            from domain.management.assistant.kb_ingest import ingest  # noqa: PLC0415

            await ingest()
        except Exception:
            logger.exception("[startup] KB ingest 실패")

    asyncio.create_task(_run_kb_ingest())
    yield
    # shutdown — 챗 오케스트레이터 체크포인터(psycopg) 풀 정리(누수 방지, 미생성이면 no-op)
    await chat.close_orchestrator()
    await close_pg_checkpointer()


_is_prod = settings.app_env == "production"
app = FastAPI(
    title="ClickMe API",
    version="2.0.0",
    description="AI Ad Simulation Platform",
    lifespan=lifespan,
    # 운영에선 Swagger/OpenAPI 비활성화(외부 노출 방지). nginx에서도 한 겹 차단.
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
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
        # 운영 배포 주소 등은 env(CORS_ALLOW_ORIGINS, 콤마 구분)로 추가
        *[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
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
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0", "env": settings.app_env}
