# 채팅 AI 어시스턴트 — 생성(Generator) 담당

> 원본 작업 노트: `context-notes.md` / 기준: 2026-06-26

---

## 생성 담당이 하는 일

사용자가 "광고 만들어줘" 같은 생성 요청을 하면 오케스트레이터가 생성 담당(`slot_agent`)으로 라우팅한다.
슬롯필링으로 필요한 정보를 채우고, 다 차면 이미지 생성 잡을 트리거한다.

**5개 전략 기반 시안 3개 생성·순위.**

---

## 동작 흐름

```
사용자: "광고 만들어줘"
    │
    ▼  오케스트레이터  →  GENERATE 의도 분류  →  slot_agent 호출
    │
    ├─ 슬롯 부족           →  ASK (되묻기)
    ├─ 프로젝트 미확정     →  ASK "어느 프로젝트에 저장할까요?"
    ├─ 이미지 없음         →  ASK + needs_assets: true  →  인라인 카드
    └─ 슬롯 충족           →  TRIGGER  →  StartedEvent(stream_url)
                                              └─ 프론트가 SSE 구독
```

**개선모드** — `improve_context`가 실려 오면(시뮬 결과 바통터치) 슬롯필링·의도분류 없이 곧장 TRIGGER.

---

## 이미지 업로드 흐름

```
생성 요청 → 슬롯 채우기 → 프로젝트 해결
    │
    ├─ 로고 키 없음  →  ASK + meta.needs_assets: true
    │     └─ 프론트가 AssetUploadCard 인라인 표시
    │           ├─ "생성 시작"(로고 업로드 후)  →  키 포함 재요청  →  TRIGGER
    │           └─ "이미지 없이 진행"  →  skip_asset_prompt: true  →  TRIGGER
    │
    └─ 로고 키 있음  →  TRIGGER
```

- 업로드 엔드포인트: `POST /api/generator/product-image` → `temp_key`
- 로고 엔드포인트: `POST /api/generator/logo` → `s3_key`
- `GenerationMode`: `CREATE` / `IMPROVE` 두 가지. 상품 이미지(`product_image_temp_key`) 유무로 내부 경로 자동 분기.
- `skip_asset_prompt`는 세션 내 유지 — 한 번 건너뛰면 같은 세션에서 다시 묻지 않음.

---

## 현재 상태 (2026-06-26 완료)

- 오케스트레이터 ↔ 라이브 라우터(`chat.py`) 연결
- 키워드 버그 수정: `"광고"` 키워드가 관리로 새던 문제 해결
- JWT 사용자 연결 (`user_id` → `SubagentRequest`)
- 프로젝트 목록 자동 조회 → "어느 프로젝트에 저장?" 되묻기
- 이미지 키 전달 경로 (`product_image_temp_key`, `brand_logo_s3_key`)
- 생성 이미지 인라인 카드(`AssetUploadCard`) — 채팅 흐름 안에 표시

---

## 주요 파일

| 역할 | 경로 |
|------|------|
| 슬롯 에이전트 | `domain/generator/chat/slot_agent.py` |
| 에이전트 진입 | `domain/generator/chat/agent.py` |
| 스트림 엔드포인트 | `GET /api/generator/generations/{id}/stream` |
| 라이브 라우터 | `api/routers/chat.py` |
| 오케스트레이터 계약 | `core/assistant_contracts.py` |

---

## 용어

| 용어 | 뜻 |
|------|----|
| 슬롯필링 | 필요 정보를 되물어 채우고 작업 시작하는 방식 |
| ASK | 정보 부족 → 되묻기 액션 |
| TRIGGER | 롱러닝 잡 시작 액션 |
| StartedEvent | TRIGGER 시 프론트로 보내는 스트림 URL 이벤트 |
| improve_context | 시뮬 결과를 생성 개선모드로 넘기는 컨텍스트 |
| needs_assets | 이미지 카드 표시 신호 (`meta`에 포함) |

> 더 자세한 내용은 `context-notes.md` 원본 참조.
