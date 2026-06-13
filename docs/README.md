# ClickMe 문서

## 공용 문서 (전체 팀)

| 문서 | 범위 |
|---|---|
| [api-spec.md](api-spec.md) | 전체 API 엔드포인트 레퍼런스 |
| [db-schema.md](db-schema.md) | DB 스키마 (`core/models.py` 기준) |

## 팀별 문서

| 팀 | 폴더 | 코드 위치 |
|---|---|---|
| 광고 생성 | [generator/](generator/) | `backend/domain/generator/` |
| 광고 매니지먼트 | [management/](management/) | `backend/domain/management/` |
| 시뮬레이터 | [simulation/](simulation/) | `backend/domain/simulation/` |

### management/
- [structure-and-roles.md](management/structure-and-roles.md) — 폴더 구조 & 역할 분담 (A/B)

---

**정리 원칙**: 전체에 영향을 주는 **공용 문서는 `docs/` 루트**, 도메인 내부 설계 등 **팀 전용 문서는 `docs/<팀>/`** 에 둔다. 문서 폴더는 `backend/domain/<팀>/` 코드 폴더와 1:1로 맞춘다.
