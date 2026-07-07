# ClickMe 문서

## 공용 문서 (전체 팀)

| 문서 | 범위 |
|---|---|
| [api-spec.md](api-spec.md) | API 요청/응답 스키마 상세(수기) |
| [api-endpoints.md](api-endpoints.md) | **자동 생성** — 전체 엔드포인트 목록(`backend/scripts/gen_docs.py`) |
| [frontend-routes.md](frontend-routes.md) | **자동 생성** — 프론트 라우트 전체 목록 |
| [db-schema.md](db-schema.md) | DB 스키마 (`core/models.py`·Alembic 기준) |
| [db-erd.md](db-erd.md) | 실 DB introspection 기반 ERD(도메인별 Mermaid + 컬럼표) |
| [langsmith-guide.md](langsmith-guide.md) | LangSmith 트레이싱 가이드 |
| [db-cleanup.md](db-cleanup.md) | DB 정리 작업 노트 |

> 인프라 프로비저닝·배포 운영 가이드는 저장소 루트의 [`infra/README.md`](../infra/README.md) 참고.

## 팀별 문서

| 팀 | 폴더 | 코드 위치 |
|---|---|---|
| 광고 생성 | [generator/](generator/) | `backend/domain/generator/` |
| 광고 매니지먼트 | [management/](management/) | `backend/domain/management/` |
| 시뮬레이터 | [simulation/](simulation/) | `backend/domain/simulation/` |
| 채팅 어시스턴트 | [chat/](chat/) | `backend/domain/chat/` · 오케스트레이터 `backend/api/assistant/` |

### management/
- [structure-and-roles.md](management/structure-and-roles.md) — 폴더 구조 & 역할 분담 (A/B)

---

**정리 원칙**: 전체에 영향을 주는 **공용 문서는 `docs/` 루트**, 도메인 내부 설계 등 **팀 전용 문서는 `docs/<팀>/`** 에 둔다. 문서 폴더는 `backend/domain/<팀>/` 코드 폴더와 1:1로 맞춘다.
