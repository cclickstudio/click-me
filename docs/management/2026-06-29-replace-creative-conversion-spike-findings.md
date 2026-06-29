# B-0 Spike Findings — REPLACE_CREATIVE 소재 변환·등록 + ad 레벨 교체

> spec: `docs/superpowers/specs/2026-06-29-replace-creative-conversion-spike-design.md`
> 작성 누적 — 각 Q는 **확정(근거)** 또는 **추정(문서 근거 + B-1 재확인)** 으로 닫는다.

## 상태표

| Q | 주제 | 상태 | 근거 |
|---|---|---|---|
| Q0.1 | 변환 단계 사슬 | 🟡 추정 | writer.py:330,49,304; client.py:153; generator_service.py:433 |
| Q0.2 | 변환 책임 위치 | ⬜ | |
| Q0.3 | 크로스도메인 핸드오프 | ⬜ | |
| Q0.4 | /adcreatives POST·validate_only | ⬜ | |
| Q0b.1 | ad fan-out 방식 | ⬜ | |
| Q0b.2 | ad creative 교체 방식 | ⬜ | |
| Q0b.3 | 영향 ad 조회 | ⬜ | |

## Q0.1 변환 단계

**상태: 🟡 추정** — 단계 1~3은 코드 확정, 단계 4(adcreatives 독립 POST)·PNG 허용 여부는 B-1 라이브 재확인 필요.

### 단계 사슬

| # | 단계 | 있는 부품 | 없는 부품/갭 |
|---|---|---|---|
| 1 | S3 PNG 바이트 획득 | `download_bytes(cand.s3_key)` — management.py:1918 패턴 | — |
| 2 | PNG → JPEG 변환 | `generator_service.py:433 png_to_jpeg` (generator 도메인) | management 내 변환 유틸 없음 — B-1이 tools/ 이동 또는 인라인 구현 필요 |
| 3 | `/adimages` 업로드 → `image_hash` | `writer.upload_image` (writer.py:330~345) + `client.post_image` (client.py:153~164) **있음** | `client.post_image`가 content-type을 `"image/jpeg"`로 하드코딩 — PNG 바이트를 그대로 보내면 MIME 불일치. 변환 선행 필수(Q0.4 추정 근거) |
| 4 | `object_story_spec` 빌드 | `_build_link_creative(config, page_id, image_hash)` (writer.py:49~59) **있음** | — |
| 5 | `/act_{id}/adcreatives` POST → `creative_id` | **없음** | `create_link_ad`(writer.py:304~328)는 creative를 ad에 **인라인**으로 박을 뿐, standalone adcreatives POST 메서드 없음 — B-1이 만들 부품 |
| 6 | ad의 creative 교체 | `writer.replace_creative(campaign_id, creative_id, idem_key)` (writer.py:123~137) **있음** | 현재 executor(executor.py:388)가 `evidence_metrics["selected_candidate_id"]`(generator DB UUID)를 그대로 전달 → Meta creative_id가 아니라 LIVE 꼬리가 끊김. 단계 5 완료 후에야 유효 creative_id 전달 가능 |

### 핵심 갭 요약

1. **단계 5 없음** — `/act_{id}/adcreatives` POST를 독립 메서드로 만들어야 creative_id를 얻을 수 있다.
2. **PNG→JPEG 변환** — `client.post_image`는 JPEG content-type 하드코딩(client.py:162). 업로드 전 변환 필요. 변환 함수 `png_to_jpeg`(generator_service.py:433)는 generator 도메인 소유 → B-1이 `tools/`로 이동하거나 관리 도메인에 인라인 구현.
3. **executor 수정** — `REPLACE_CREATIVE` 분기(executor.py:388)가 UUID → Meta creative_id로 대체되도록 증거 메트릭 구조 변경 필요.

> 추정 근거: Meta Graph API 문서상 `/adimages`는 JPEG/PNG 모두 허용하나, 코드가 JPEG만 전송하므로 PNG-as-JPEG 동작이 통과하는지 Q0.4 라이브 probe로 재확인.

## Q0.2 변환 책임 위치

## Q0.3 크로스도메인 핸드오프

## Q0.4 /adcreatives POST·validate_only

## Q0b.1 ad fan-out 방식

## Q0b.2 ad creative 교체 방식

## Q0b.3 영향 ad 조회

## 결론 — B-1 경로 ① go/no-go

## B-1이 만들 Port/메서드 제안 (추천, 잠금은 B-1)
