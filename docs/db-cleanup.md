# ClickMe DB 정리 분석 (불필요·통합 후보)

> 개인 NeonDB(공용 복제본, alembic 스탬프 `024`, 70테이블)를 introspection하고 백엔드 코드 전반과 교차 검증한 결과다. 동반 문서 [db-erd.md](db-erd.md)는 스키마 레퍼런스, 이 문서는 **무엇을 지우고/합치고/남길지** 판단 근거다.
> **본 분석은 권장이며 코드/마이그레이션을 변경하지 않는다.** 실제 정리는 후속 합의 후 진행한다.

## ⚠ 먼저 읽을 것 — 3중 드리프트

정리를 실행하기 전에 반드시 인지해야 한다.

1. **실 DB(70테이블·스탬프 024) ≠ 레포 마이그레이션(head 021) ≠ ORM(`core/models.py`+`domain/simulation/models.py`의 `__tablename__` 38개).** 셋이 서로 다르다.
2. 정리/보류 후보 다수(`chat_long_term_memory`·`checkpoints*`·`management_chat_*`·`management_kb_documents/eval_cases/feedback` 등)는 **레포 마이그레이션이 만든 적이 없다.** 022~024가 레포에 없어(라이브 DB에만 존재) `alembic downgrade`로는 정리를 표현조차 못 한다.
3. 역방향 드리프트 — `regeneration_jobs`는 ORM+마이그레이션 020에 있으나 **실 DB엔 없다.** 즉 스탬프 024가 실제 적용 스키마와 불일치한다.
4. **권고** — 파괴적 정리 전에 레포 마이그레이션을 실 DB와 먼저 정합(022~024 복구/작성)시켜야 안전하다. 지금 대상은 개인 복제본이라 실험은 안전하지만, **공용 DB에 적용하기 전 동일 분석을 재확인**해야 한다.

## 한눈에 요약

| 범주 | 테이블 수 | 의미 |
|---|---|---|
| 🟢 A. KEEP | 35 | ORM+코드로 실제 사용 중인 활성 코어 |
| ⏸ B. 보류 | 14 | 진행 중 챗 오케스트레이터(4-4)·LangGraph HITL 스캐폴딩 — **삭제 금지** |
| 🗑 C. 정리(DROP) 후보 | 21 | 미사용·레거시·대체됨 (확신도별) |
| **계** | **70** | |

통합(merge) 후보 7군과 컬럼 수준 발견 5건은 아래 별도 섹션 참조.

---

## A. KEEP — 활성 코어 (35)

ORM이 있고 코드가 실제로 읽고 쓴다. 손대지 않는다.

| 테이블 | 행수 | 비고 |
|---|---|---|
| users · teams · organization_members · organizations | 11·5·10·5 | 인증/조직/팀 |
| projects | 9 | 캠페인 루트 |
| ads | 19 | 광고 소재 (단 ORM 드리프트 심함 — 컬럼 섹션 참조) |
| simulations · simulation_aggregates · persona_responses · rubric_scores · ad_analyses | 25·22·581·65·23 | 시뮬 본체+KPI+반응+루브릭+해석 |
| personas · panels | 51·2 | 페르소나/패널 |
| persona_debates · persona_debate_participants · persona_debate_utterances | 21·145·500 | 토론 |
| ad_generations · ad_generation_candidates · ad_publish_logs | 140·289·7 | 생성/후보/게시 |
| ad_campaign_logs · created_campaigns · campaign_kpi_overrides · meta_connections | 2·63·1·3 | 매니지먼트 캠페인/Meta |
| action_proposals · approvals · audit_events · execution_runs · idempotency_keys · remediation_escalations | 0·0·24·0·12·0 | 매니지먼트 단일 지출 경로 (행 0은 dry_run이라 비었을 뿐 코드 활성) |
| management_kb_chunks | 17 | 어시스턴트 RAG 정본 (`assistant/retriever.py` 사용) |
| brand_profiles | 5 | generator 브랜드 프로필 (`domain/generator`) |
| payment_orders · credit_ledger | 2·0 | 결제/크레딧 원장 |
| inquiries | 0 | 문의 (ORM 있음, company 라우터) |
| alembic_version | 1 | 시스템(마이그레이션 스탬프) |

> 행수 0이어도 KEEP인 이유 — `action_proposals`·`approvals`·`execution_runs`·`credit_ledger` 등은 dry_run/mock 운영이라 런타임에 안 채워질 뿐, ORM과 도메인 코드가 실제로 쓴다.

---

## B. 보류 — 챗 오케스트레이터 스캐폴딩 (14, 삭제 금지)

현재 repo 코드/ORM/마이그레이션에 없어 "미사용"처럼 보이지만, **지금 만들고 있는 챗 오케스트레이터(4-4)와 LangGraph HITL 영속이 쓸 바로 그 테이블들**이다. 라이브 DB에만 존재하는 022~024 + 라이브러리 산물이다.

| 테이블 | 행수 | ORM | 정체 / 처리 방향 |
|---|---|---|---|
| chat_sessions | 3 | ✅ | 챗 세션. ORM은 있으나 `chat.py`가 아직 write 안 함(Gemini 직접+키워드 라우팅). 오케스트레이터가 흡수 |
| chat_messages | 0 | ✗ | 챗 메시지 |
| chat_long_term_memory | 0 | ✗ | 챗 장기기억 |
| chat_brand_profiles | 0 | ✗ | 챗용 브랜드 프로필 |
| management_chat_sessions · management_chat_messages | 2·4 | ✗ | 매니지먼트 어시스턴트 대화 (데이터 있음 — 외부 브랜치에서 적재) |
| management_agent_runs | 2 | ✗ | 어시스턴트 실행 로그 |
| management_kb_documents · management_kb_eval_cases · management_kb_feedback | 4·6·1 | ✗ | 어시스턴트 KB 문서/평가/피드백 (정본 청크는 A의 `management_kb_chunks`) |
| checkpoints · checkpoint_blobs · checkpoint_writes · checkpoint_migrations | 10·16·26·10 | ✗ | **LangGraph 체크포인터가 관리.** 현재 `MemorySaver`(인메모리) 사용, `AsyncPostgresSaver` 전환 시 이 테이블 사용 (`domain/management/wiring.py:122-130`). grep에 안 잡히는 건 라이브러리 소유라 그렇지 dead 아님 |

- **권장** — 삭제하지 말고 **repo로 정합**한다. 오케스트레이터를 구현하며 ORM/마이그레이션(022~024 상당)을 작성해 이 스키마를 공식화하고, `chat_*`와 `management_chat_*`는 아래 통합안대로 단일 스키마로 수렴 검토.

---

## C. 정리(DROP) 후보 (21)

### 확신 높음 — ORM·코드·로드맵 전무, cascade delete에서만 등장 (17)

| 테이블 | 행수 | 사유 | 근거 |
|---|---|---|---|
| generated_ads | 0 | `ad_generations`+`ad_generation_candidates`로 대체된 구 생성 테이블 | ORM 없음, 코드 0 |
| ad_templates | 0 | 미구현 템플릿 스텁 | ORM 없음, 코드 0 |
| generator_kb_chunks | 0 | 미사용 KB (정본은 `management_kb_chunks`) | ORM 없음, 코드 0 |
| rag_chunks | 0 | 구 분류형 KB 스텁(tier/dimension) | ORM 없음, 코드 0 |
| simulation_kb_chunks | 6 | 미사용 KB (데이터 있으나 코드 0) | ORM 없음, 코드 0 |
| diagnoses | 0 | 진단 결과는 outcome dict로 전달, DB 미사용 | ORM 없음, `projects.py` cascade delete에서만 |
| recommendations | 0 | 미구현 추천 | ORM 없음, cascade delete에서만 |
| reports | 0 | 미사용 리포트 스텁 | ORM 없음, cascade delete에서만 |
| audit_logs | 0 | `audit_events`로 완전 대체된 구 범용 감사 | ORM 없음, 코드 0 |
| simulation_comparisons | 0 | 생성 경로 없음 | ORM 없음, cascade delete에서만 |
| persona_templates | 0 | 미구현(재사용 템플릿) | ORM 없음, 코드 0 |
| project_members | 0 | 미구현(협업은 팀 단위 사용 중) | ORM 없음, 코드 0 |
| user_settings | 0 | 구 테이블, ORM 폐기됨 | ORM 없음, 코드 0 |
| subscription_plans | 0 | 플랜 enforcement 미구현 (`organizations.plan` 컬럼으로 대체) | ORM 없음, 코드 0 |
| organization_subscriptions | 0 | 동상 — 미사용 구독 인스턴스 | ORM 없음, 코드 0 |
| benchmarks | 0 | 미구현 | ORM 없음, 코드 0 |
| calibration_data | 0 | 미구현(KOBACO calibration 미해금) | ORM 없음, 코드 0 |

### 확신 중간 — ORM이 있어 삭제 시 ORM 편집 동반 (2)

| 테이블 | 행수 | 사유 | 근거 |
|---|---|---|---|
| simulation_results | 0 | `simulation_aggregates`로 대체된 구 결과 테이블 | ORM 있음(`models.py:142`), `dashboard.py:41` "구 simulation_results 아님" 주석, `Ad.simulations` 관계도 함께 레거시 |
| ad_embeddings | 0 | 한 번도 write 안 되는 RAG 스텁 | ORM 있음(`models.py:155`, vector(1536)), cascade delete에서만 |

### 확신 낮음 — 검토 필요 (2)

| 테이블 | 행수 | 사유 | 근거 |
|---|---|---|---|
| refresh_tokens | 0 | JWT 리프레시 미구현. 인증 강화 시 필요할 수 있음 | ORM 없음, 코드 0 |
| brand_kits | 3 | repo 코드 0이나 데이터 3행 + 조직 공유 브랜드 자산 기능 가능성 | ORM 없음, 코드 0 (통합 섹션 참조) |

---

## 통합(merge) 후보

| # | 군 | 멤버 (행수) | 판정 | 메모 |
|---|---|---|---|---|
| 1 | 벡터 KB | management_kb_chunks(17, 정본) / simulation_kb_chunks(6) / generator_kb_chunks(0) / rag_chunks(0) | **시뮬·생성 KB 로드맵 있으면 MERGE, 없으면 DROP 3종** | 스키마 동형(`embedding vector(1536)`+`chunk`+`source`). MERGE 시 `domain` discriminator 단일 `kb_chunks`. retriever `assistant/retriever.py`에 `domain` 필터 추가 |
| 2 | 챗 2세트 | chat_*(범용 4-4) / management_chat_*(어시스턴트) | **단일 스키마로 수렴 권장** | 둘 다 repo 코드 0. 오케스트레이터 설계 시 `sessions`+`messages` 한 벌 + `source`/`agent_type` discriminator로. 스키마 2벌 유지 회피 (B 보류와 연계) |
| 3 | 브랜드 3종 | brand_profiles(5, client_id·generator 사용) / brand_kits(3, org_id) / chat_brand_profiles(0) | **KEEP-SEPARATE (단 컬럼 중복 메모)** | 소유주·생명주기 다름(브라우저 client_id vs 조직 org_id). `brand_color`·`brand_logo_key`·`tone` 컬럼은 중복 → 향후 `brand_context` discriminator로 통합 여지 |
| 4 | 감사 | audit_events(24, 정본) / audit_logs(0) | **DROP audit_logs** | C와 동일 |
| 5 | 페르소나 | personas(51) / panels(2) / persona_templates(0) | **personas+panels KEEP, persona_templates DROP** | personas(샘플)·panels(캐시)는 역할 다름. templates는 미사용 |
| 6 | 제안/추천/리포트 | action_proposals(0, 활성) / recommendations(0) / reports(0) | **action_proposals KEEP, 나머지 DROP** | recommendations·reports는 ORM 없고 미사용 |
| 7 | 플랜/구독 | organizations.plan(컬럼, 사용) / subscription_plans(0) / organization_subscriptions(0) | **컬럼 KEEP, 테이블 2종 DROP/보류** | 실과금 전까지 컬럼으로 충분 (CLAUDE.md "UI만") |

---

## 컬럼 수준 정리

| 심각도 | 대상 | 발견 | 권장 |
|---|---|---|---|
| 🔴 높음 | `ads` (ORM `Ad`) | ORM은 `id/project_id/title/ad_type/s3_key/analysis/created_at` 7개뿐인데 실 DB는 `media_type/asset_url/copy_text/industry_category/product_category/ad_objective/target_filter/status/created_by/updated_at` 보유. 실DB 컬럼은 raw SQL로만 접근(`domain/simulation/repositories/persistence.py`, `api/routers/management.py:1485`) | ORM 재동기화. `ad_type`→`media_type`, `s3_key` 제거(실제는 `ad_generation_candidates.s3_key`), `analysis` 제거(정규화돼 `ad_analyses`로 이전) |
| 🟡 중간 | `projects`·`simulations` (soft delete) | 실 DB엔 `deleted_at` 있고 raw SQL이 쓰는데 ORM엔 없음. `projects` ORM은 `description/status/created_by/updated_at/deleted_at` 5개 누락 | ORM에 누락 컬럼 추가, soft delete 일관화 |
| 🟢 낮음 | `organizations.default_landing_url` | 실 DB에만 존재, 코드 0 (고아 컬럼) | DROP 또는 용도 명시 |
| 🟢 낮음 | `projects.status` vs `deleted_at` | 'ACTIVE'/'DELETED'와 타임스탬프가 soft delete를 이중 인코딩 | `deleted_at IS NOT NULL` 단일 기준으로 정규화 검토 |
| 🟢 검토 | jsonb 과다 | `ad_generations.{input,product_analysis,strategies}`·`ad_generation_candidates.{copy,qa_result}`·`simulation_aggregates.payload`·`simulations.target_filter` | 의도적 schemaless. 조인/검색 필요 전까지 KEEP |

---

## 부록

### 범주 정의

- **KEEP** — ORM이 있고 도메인 코드가 실제로 읽고 쓴다. 행수 0이어도 dry_run/mock이라 비었을 뿐 활성.
- **보류** — repo엔 없지만(라이브 DB 전용) 진행 중 기능이 쓸 스캐폴딩. 삭제 대신 repo로 정합.
- **정리(DROP)** — ORM·코드·로드맵 어디서도 안 쓰거나 신 테이블로 대체된 레거시. 확신도 = 높음(코드/ORM 전무) · 중간(ORM 있어 편집 동반) · 낮음(향후 필요 가능성).
- **통합(MERGE)** — 목적·스키마가 겹쳐 discriminator로 한 테이블로 합칠 수 있는 군.

### 재현 방법

- 스키마 대조 — [db-erd.md](db-erd.md)(실 DB introspection 산출)와 본 분류를 대조.
- 코드 사용처 — `core/models.py`·`domain/simulation/models.py`의 `__tablename__` 38개가 ORM 보유 테이블. 나머지 32개는 ORM 없음(raw SQL/라이브러리/고아).
- 미참조 확인 — backend(.venv 제외)에서 테이블명 grep이 0이면 정리/보류 후보. `chat.py`는 챗 테이블에 write하지 않음.
- 파괴적 변경이 없어 런타임 검증 불요. 실제 정리 시에는 위 "3중 드리프트" 경고대로 레포 마이그레이션 정합을 선행.
