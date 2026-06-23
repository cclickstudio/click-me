# 채팅(4-4) End-to-End 테스트 가이드

> 오케스트레이션 챗봇의 전체 흐름을 dev 환경에서 직접 검증하는 절차.
> 대상 — 프로젝트 선택 게이트 · 세션 영속(DB) · 라우팅 · 위젯 자동 채움 · 이미지 첨부 · 동시실행 제한 · 결과 기반 제안.
> 정본 설계는 [architecture.md](architecture.md).

---

## 0. 사전 준비

### 0-1. 환경 변수 (`backend/.env`)

풀모드(실제 LLM 라우팅)로 테스트하려면 키가 필요하다.

```bash
APP_ENV=development
OPENAI_API_KEY=...      # classify_intent·시뮬/제너/매니지 라우팅·advise (필수)
GEMINI_API_KEY=...      # 폴백 경로(CLIO) — 키 없거나 오케스트레이터 실패 시
DATABASE_URL=...        # ★ 반드시 개인 DB인지 확인 (팀 DB 금지)
```

> **DB 호스트 확인** (팀 DB 사고 방지):
> ```bash
> cd backend && uv run python -c "from core.config import settings; import re; print(re.search(r'@([^/]+)/', settings.database_url).group(1))"
> ```
> 개인 DB 호스트(`ep-soft-band-...`)가 맞는지 먼저 확인하고 진행할 것.

### 0-2. 마이그레이션·KB 적재 (개인 DB)

```bash
cd backend
uv run alembic current          # 021 이어야 함
uv run alembic upgrade head      # 아니면 적용
# KB가 비어 있으면(선택, 없어도 degrade 동작)
uv run python -m domain.simulation.assistant.kb_ingest
uv run python -m domain.generator.assistant.kb_ingest
```

### 0-3. 서버 기동

```bash
# 터미널 1 — 백엔드
cd backend && uv run uvicorn api.main:app --reload --port 8000

# 터미널 2 — 프론트
cd frontend && pnpm dev
```

브라우저에서 **로그인** (프로젝트 목록·채팅 모두 로그인 토큰 필요).

> **UI 구조 (중요)** — 채팅 세션 목록은 **좌측 프로젝트 패널**(ProjectPanel / 관리자는 AdminPanel)의 프로젝트 안 **"채팅" 섹션**에 있다. `/chat` 탭은 자체 사이드바가 없고 대화만 전체화면으로 띄운다. 다른 화면에서는 **우측 하단 플로팅**으로 같은 대화를 띄운다. (CompanyPanel에는 채팅 섹션 없음.)

---

## 1. 프로젝트 선택 게이트

| 단계 | 기대 결과 |
| --- | --- |
| 로그인 후 좌측 프로젝트 패널 | 프로젝트 목록 표시 |
| 프로젝트(▸) 펼치기 | 시뮬레이션·제너레이터 아래 **"채팅 (n)"** 섹션 존재 |
| `/chat` 탭 진입(프로젝트 미선택) | "먼저 프로젝트를 선택하세요" 게이트 화면 |
| 프로젝트 선택 후 `/chat` | 사이드바 없이 대화 화면(빈 상태=웰컴) |
| 프로젝트 없음 계정 | "사용 가능한 프로젝트가 없습니다" 안내 |

- 새로고침해도 같은 프로젝트가 유지되는지 확인(localStorage `selectedProjectId`).

---

## 2. 세션 생성·목록·내역 영속 (DB)

> 세션 목록은 **프로젝트 패널의 "채팅" 섹션**에서 본다(별도 사이드바 아님).

| 단계 | 기대 결과 |
| --- | --- |
| 패널에서 프로젝트 펼치고 "채팅" 섹션 열기 | 그 프로젝트의 세션 목록(없으면 "채팅 없음") |
| 패널 "+ 새 채팅" 클릭 | `/chat`이면 대화가 새 채팅으로, 다른 화면이면 플로팅이 새 채팅으로 열림 |
| 첫 메시지 전송 | DB에 세션 1개 생성 → **패널 채팅 섹션에 자동 추가**, 제목이 **첫 사용자 발화**로 설정 |
| 메시지 몇 번 주고받기 | 새로고침 후 패널에서 그 세션 클릭 → **내역이 복원**됨 |
| 패널 세션 hover → ✕ | 세션 삭제(메시지 CASCADE), 목록에서 사라짐. 열려 있던 세션이면 새 채팅으로 |

### DB 직접 확인 (읽기 전용)

```bash
cd backend && uv run python -c "
import asyncio
from sqlalchemy import text
from core.db import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text('SELECT id, title, project_id, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT 5'))
        for row in r: print('session', str(row[0])[:8], '|', row[1], '| proj', str(row[2])[:8] if row[2] else None)
        r = await db.execute(text('SELECT role, left(content,30), (metadata IS NOT NULL) FROM chat_messages ORDER BY created_at DESC LIMIT 6'))
        print('--- 최근 메시지 ---')
        for row in r: print(row[0], '|', row[1], '| meta:', row[2])
asyncio.run(main())
"
```

- 사용자 메시지(role=user)와 어시스턴트 메시지(role=assistant)가 쌍으로 쌓이는지.
- 어시스턴트 메시지의 `metadata`(출처·위젯·인용)가 채워지는지.

---

## 3. 라우팅 (classify → route)

각 입력에 대해 응답 상단의 **출처 배지**(라벨·엔진)와 내용이 도메인에 맞는지 확인.

| 입력 예시 | 기대 라우팅 |
| --- | --- |
| `우리 캠페인 CTR이 어때?` / `예산 소진 현황 알려줘` | **management** (매니지먼트 어시스턴트) |
| `클릭 의향률이 무슨 뜻이야?` | **simulation** (시뮬 어시스턴트, 질문답변) |
| `광고 카피 잘 쓰는 원칙 알려줘` | **generator** (생성 어시스턴트) |
| `20대 타겟 마케팅 아이디어 줘` | **advise** (CLIO) |
| (키 없음/오케스트레이터 실패) | 폴백 — Gemini CLIO 또는 키워드 매니지 |

> 풀모드 확인 — `OPENAI_API_KEY`가 있고 `use_mock`이 꺼져 있어야 LLM 라우팅이 동작한다. 없으면 키워드 폴백(매니지 질문만)·나머지는 Gemini.

---

## 4. 위젯 자동 채움 (핵심)

채팅으로 이미 준 값이 위젯에 **다시 묻지 않고 채워져야** 한다.

| 입력 | 기대 결과 |
| --- | --- |
| `'여름 세일'이라는 제목으로 시뮬레이션 돌려줘. 시원한 음료 광고야.` | `sim_form` 위젯이 뜨고 **제목="여름 세일"**, 설명(카피)이 미리 채워짐 |
| `수분크림 광고 시안 만들어줘. 타깃은 건성 피부 20대 여성.` | `gen_form` 위젯, 상품명·설명·타깃이 미리 채워짐 |
| 위젯에서 값 수정 후 실행 | 수정값으로 실행됨 |

- 추출 안 된 항목(예: 카테고리 미언급)은 빈칸으로 두고 사용자가 채우게 두는지 확인(지어내지 않음).

---

## 5. 이미지 첨부 → 위젯 전달

| 단계 | 기대 결과 |
| --- | --- |
| 입력바 📎(첨부) 버튼 → 이미지 선택 | 입력바 위에 썸네일 미리보기 + "이미지 제거 ✕" |
| 텍스트 없이 전송 시도 | **전송 안 됨**(전송 버튼은 텍스트 필요) |
| `(이미지 첨부) 이걸로 시뮬레이션 돌려줘` 전송 | 사용자 버블에 이미지 썸네일 표시, `sim_form` 위젯에 **"채팅에서 첨부한 이미지를 사용해요"** + 썸네일 |
| 그대로 시뮬 실행 | 첨부 이미지가 `ad_image`로 전송되어 실행 |
| 제너 케이스 동일 | `gen_form`에서 첨부 이미지를 **상품 이미지로 업로드**해 사용 |
| 슬래시 `/시뮬레이션`·`/제너레이터` + 첨부 | 첨부 이미지가 위젯으로 전달됨 |
| 전송 후 새로고침 → 패널에서 그 세션 다시 열기 | **첨부 이미지가 버블에 그대로 복원**(S3 영속화) |

- 첨부 이미지는 전송 시 **S3에 1회 업로드**(`POST /api/chat/image` → `chat-images/`)되어 사용자 메시지 meta(`image_url`)에 영속화된다. 버블은 백엔드 프록시(`GET /api/chat/image?key=…`)로 렌더.
- 위젯 **실행**은 여전히 그 세션의 원본 File을 쓴다(시뮬 `ad_image` / 제너 상품 이미지 업로드) — S3 표시용과 별개 경로.
- **degrade** — S3 미설정/업로드 실패 시 이번 세션 표시는 되지만 내역엔 안 남는다(채팅 흐름은 안 막힘).

### S3 적재 직접 확인 (읽기 전용)

```bash
cd backend && uv run python -c "
import asyncio
from sqlalchemy import text
from core.db import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(\"SELECT content, metadata->>'image_url' FROM chat_messages WHERE role='user' AND metadata ? 'image_url' ORDER BY created_at DESC LIMIT 5\"))
        for row in r: print(row[1], '|', row[0][:30])
asyncio.run(main())
"
```

---

## 6. 위젯 실행 → 결과 → 다음 단계 제안

| 단계 | 기대 결과 |
| --- | --- |
| 시뮬 위젯 실행 | 진행률 스피너(클릭 시 `/simulation/{id}` 이동) → 결과 요약(4대 KPI) + "상세 보기" |
| 결과 후 자동 | `[시뮬결과] …` 메시지가 채팅에 전송되고, **결과가 약하면**(구매의도<3.5·거부율≥30%) 개선 시안 생성 **제안** |
| 제너 위젯 실행 | 진행률 → 시안 N개 요약 + 상세 링크 |
| 생성 후 자동 | `[생성결과] …` → **새 시안으로 재시뮬 제안** |

---

## 7. 동시실행 제한

시뮬/제너는 각각 **한 번에 하나**(채팅 위젯과 입력 페이지가 store 공유).

| 단계 | 기대 결과 |
| --- | --- |
| 시뮬 위젯 실행 중 또 다른 시뮬 실행 시도 | "이미 다른 시뮬레이션이 진행 중이에요" 차단 |
| 시뮬 실행 중 `/simulation` 페이지에서 실행 | 동일 차단(같은 store) |
| 시뮬 실행 중 제너 실행 | **허용**(시뮬+제너 동시는 가능) |
| 완료/실패 후 | 슬롯 해제 → 다시 실행 가능 |

> 알려진 한계 — 위젯/페이지를 실행 중 떠나면(언마운트) 완료 콜백이 안 돌아 슬롯이 점유된 채 남을 수 있다(제너 페이지는 재진입 복원으로 해제). 막히면 새로고침.

---

## 8. 슬래시 커맨드

| 입력 | 기대 결과 |
| --- | --- |
| `/` 입력 | 자동완성 드롭다운(시뮬레이션·제너레이터·위젯), ↑↓·Enter 선택 |
| `/시뮬레이션` | `sim_form` 위젯 즉시 표시(백엔드 호출 없음) |
| `/제너레이터` | `gen_form` 위젯 |
| `/위젯` | 사용 가능 위젯 목록 안내(개발용) |

---

## 9. API 직접 확인 (선택)

```bash
# 세션 생성
curl -s -X POST localhost:8000/api/chat/sessions -H 'Content-Type: application/json' \
  -d '{"project_id":"<프로젝트UUID>","title":"테스트"}'

# 세션 목록
curl -s "localhost:8000/api/chat/sessions?project_id=<프로젝트UUID>"

# 메시지 내역
curl -s localhost:8000/api/chat/sessions/<세션ID>/messages

# 채팅(SSE) — session_id는 위에서 만든 세션
curl -N -X POST localhost:8000/api/chat/complete -H 'Content-Type: application/json' \
  -d '{"session_id":"<세션ID>","messages":[{"role":"user","content":"클릭 의향률이 뭐야?"}]}'
```

- `/api/assistant/chat` 도 동일 로직(같은 핸들러).

---

## 9-A. 플로팅 챗봇 & 패널 연동

플로팅은 **전역**(`/chat` 탭·비로그인 화면 제외)에 뜬다. 세션 선택은 패널 채팅 섹션에서 한다.

| 단계 | 기대 결과 |
| --- | --- |
| 시뮬/제너/대시보드 등 일반 화면 | 우측 하단에 **플로팅 버튼** 표시 |
| `/chat` 탭 | 플로팅 버튼 **숨김**(페이지 자체가 채팅) |
| 로그아웃/로그인 화면 | 플로팅 버튼 **숨김** |
| 플로팅 버튼 클릭 | 패널 펼침. 활성 세션 없으면 **가장 최근 세션** 이어받음, 없으면 새 채팅(웰컴) |
| 플로팅 헤더 + 버튼 | 새 채팅으로 전환 |
| 플로팅 헤더 ✕ | 접힘(버튼만) |
| 프로젝트 미선택 상태에서 플로팅 열기 | "프로젝트를 먼저 선택하세요" 안내 |
| **패널 채팅 섹션에서 세션 클릭 (일반 화면)** | `/chat`로 라우팅되지 **않고** 플로팅이 그 세션으로 열림 |
| **패널 채팅 섹션에서 세션 클릭 (`/chat` 탭)** | 그 페이지 대화가 해당 세션으로 전환 |
| 다른 프로젝트의 세션 클릭 | 그 프로젝트로 선택 전환 + 해당 세션 로드 |
| 플로팅에서 대화 → 화면 이동 | 같은 세션/내역 유지(전역 상태) |
| AdminPanel(관리자 계정) | 프로젝트 채팅 섹션 동일 동작 |
| CompanyPanel(기업 계정) | 채팅 섹션 **없음** |

---

## 10. 체크리스트 요약

- [ ] 프로젝트 미선택 시 `/chat` 게이트, 패널에 "채팅" 섹션 노출
- [ ] 첫 전송 시 세션 생성·제목 자동·**패널 목록에 자동 추가**
- [ ] 새로고침 후 패널에서 세션 클릭 → 내역 복원
- [ ] 패널에서 세션 삭제(CASCADE)
- [ ] 라우팅 4종(management/simulation/generator/advise) 배지 일치
- [ ] 위젯 자동 채움(제목 등) 동작, 미언급 항목은 빈칸
- [ ] 이미지 첨부 → 사용자 버블·위젯 썸네일·실행 반영
- [ ] 텍스트 없이 전송 차단
- [ ] 시뮬/제너 실행 → 결과 → 다음 단계 제안
- [ ] 동시실행 1개 제한(시뮬/제너 각각), 시뮬+제너 동시 허용
- [ ] 슬래시 커맨드 3종
- [ ] **플로팅**: 일반 화면 표시 / `/chat`·비로그인 숨김 / 최근 세션 이어받기
- [ ] **패널 세션 클릭** → 라우팅 없이 플로팅(또는 `/chat` 대화) 전환
- [ ] AdminPanel 채팅 섹션 동작 / CompanyPanel 채팅 섹션 없음
- [ ] DB에 user/assistant 메시지·meta 적재 확인

---

## 11. 트러블슈팅

| 증상 | 원인·조치 |
| --- | --- |
| 모든 응답이 Gemini(CLIO)로만 감 | 풀모드 미동작 — `OPENAI_API_KEY` 확인, `use_mock` 꺼짐 확인 |
| 위젯 자동 채움 안 됨(제목 비어 있음) | 풀모드 아님(폴백은 추출 안 함) 또는 추출 실패 — 백엔드 로그 확인 |
| 채팅 내역이 저장 안 됨 | `session_id`가 DB 세션 UUID가 아님(프론트가 세션 생성 후 사용하는지), 백엔드 `[chat] persist error` 로그 확인 |
| 세션 목록 비어 있음 | 로그인/프로젝트 선택 여부, `project_id` 전달 확인. 패널 "채팅" 섹션을 펼쳤는지 |
| 플로팅 버튼이 안 보임 | `/chat` 탭이거나 비로그인 상태 — 일반 화면+로그인에서 확인 |
| 패널 채팅 클릭해도 플로팅이 안 뜸 | 다른 화면인지 확인(`/chat`에선 페이지 대화가 전환됨). 컨텍스트 provider(layout) 마운트 확인 |
| 시뮬/제너 실행이 계속 차단 | 슬롯 잔존 — 새로고침으로 store 초기화 |
| KB 인용이 안 붙음 | KB 미적재 — 0-2의 `kb_ingest` 실행(없어도 degrade) |
