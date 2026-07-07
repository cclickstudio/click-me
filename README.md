# ClickMe

AI 기반 광고 성과 예측 플랫폼. 가상 소비자(페르소나)에게 광고를 먼저 테스트해 구매의향 분포를 예측한다.

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | Next.js (TypeScript) + Tailwind CSS |
| Backend | FastAPI (Python) + LangGraph |
| DB | NeonDB (PostgreSQL + pgvector) |
| AI | GPT-4o Vision / GPT-4o-mini / Gemini 2.0 Flash |
| 비동기 잡 / 스토리지 | 인프로세스 async (asyncio) / AWS S3 |
| 배포 | EC2 + Nginx + Docker |

---

## 로컬 실행

**사전 조건**: `uv`, `pnpm`, Docker 설치

```bash
# 백엔드
cd backend && uv run dev.py

# 프론트엔드
cd frontend && pnpm dev

# 전체 (Docker)
docker compose up --build
```

환경변수는 `backend/.env`, `frontend/.env.local`에 설정. 필요한 키 목록은 `CLAUDE.md` 참고.

---

## 패키지 매니저 규칙

- `backend/` — **uv 전용** (pnpm 사용 금지)
- `frontend/` — **pnpm 전용** (uv 사용 금지)

---

## 주요 문서

| 문서 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 아키텍처 결정, 개발 규칙, 환경변수 전체 목록 |
| [docs/README.md](docs/README.md) | 문서 인덱스(공용·팀별) |
| [docs/api-spec.md](docs/api-spec.md) | API 엔드포인트 명세 |
| [docs/db-schema.md](docs/db-schema.md) | DB 스키마 및 Alembic 마이그레이션 |
| [docs/db-erd.md](docs/db-erd.md) | 실 DB introspection 기반 ERD(도메인별 Mermaid) |
| [infra/README.md](infra/README.md) | 인프라 프로비저닝·배포 운영 가이드 |
| [docs/create_issues_template.py](docs/create_issues_template.py) | GitHub Issues 일괄 생성 스크립트 템플릿 |

---

## CI/CD

- **단일 파이프라인** (`.github/workflows/ci-cd.yml`): 구 `ci.yml`+`cd.yml`을 하나로 병합.
- **CI**: Ruff lint + pytest(backend), ESLint + Next.js build(frontend). PR·push 모두 실행.
- **CD**: `main`·`ci-cd` 브랜치 push에서만 CI 성공 시 ECR 이미지 빌드·push → EC2에서 `docker-compose.prod.yml`로 배포. Nginx + Let's Encrypt(certbot 자동 발급·갱신).
- 배포 인프라(EC2 프로비저닝·Elastic IP·PEM 공유)는 [`infra/README.md`](infra/README.md) 참고.

---

## 커밋 컨벤션

```
add: 새 기능    edit: 기존 수정    fix: 버그 수정    delete: 삭제
```

예시: `add: 시뮬레이션 결과 PDF 생성 기능`
