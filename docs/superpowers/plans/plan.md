# Meta Marketing API 온보딩 및 권한 준비 문서

작성일: 2026-06-16

> 목적: ClickMe의 Meta Marketing API 연동을 위해 개발자 등록, 비즈니스 인증, 앱 설정, 토큰 발급, 권한 심사, Insights 첫 호출까지 필요한 작업을 한곳에 정리한다.
>
> 보안 주의: 실제 access token, app secret은 문서에 평문으로 저장하지 않는다. 로컬 `.env` 또는 운영 시크릿 매니저에만 저장한다.

---

## 1. 진행 순서

### 1. 개발자 등록 및 앱 생성

- Meta for Developers 접속: <https://developers.facebook.com>
- 로그인 후 `My Apps` 이동
- 앱 생성 페이지: <https://developers.facebook.com/apps>
- `Create App` 선택
- 앱 유형: `Business`

### 2. 비즈니스 포트폴리오 및 자산 연결

- Meta Business 접속: <https://business.facebook.com>
- Business Settings: <https://business.facebook.com/settings>
- 아래 자산을 같은 비즈니스 포트폴리오에 연결한다.
  - 광고계정: `act_...`
  - Facebook 페이지
  - Instagram 비즈니스 계정
- Instagram 광고 집행을 위해서는 광고계정, Facebook 페이지, Instagram 비즈니스 계정이 함께 묶여 있어야 한다.

### 3. Business Verification 신청

가장 오래 걸리는 단계이므로 가장 먼저 신청한다.

- Security Center: <https://business.facebook.com/settings/security-center>
- 입력 정보:
  - 법인명
  - 주소
  - 전화번호
  - HTTPS 웹사이트
- 공개 기록 매칭이 실패하면 사업자등록증 등 증빙 문서를 업로드한다.
- 도메인, 이메일, 전화 중 Meta가 요구하는 방식으로 본인 증명을 완료한다.

### 4. 앱에 Marketing API 추가

- 앱 대시보드 이동
- `Add Product` 선택
- `Marketing API` 추가
- 공식 가이드: <https://developers.facebook.com/docs/marketing-api/get-started>

### 5. 토큰 발급 및 검증

- 테스트 호출: Graph API Explorer  
  <https://developers.facebook.com/tools/explorer>
- 토큰 만료 및 스코프 확인: Access Token Debugger  
  <https://developers.facebook.com/tools/debug/accesstoken>
- 프로덕션 권장 방식:
  - Business Settings
  - Users
  - System Users
  - System User 장기 토큰 발급

### 6. Standard 등급에서 실호출 500개 적립

- 목적: Advanced 등급 상향 자격 확보
- 본인 계정에서 `ads_read` 권한으로 Insights 호출을 반복한다.
- 기준: 15일 내 실호출 500개 적립
- Insights 레퍼런스: <https://developers.facebook.com/docs/marketing-api/insights>

### 7. App Review 및 Marketing API Access Tier 상향

- 권한 심사:
  - 앱 대시보드
  - App Review
  - Permissions
  - 필요한 권한 요청
- 등급 상향:
  - 앱 대시보드
  - Marketing API
  - Access 또는 Marketing API Access Tier 신청

### 8. Ads Manager 수동 캠페인 및 골든샘플 확보

- Ads Manager: <https://www.facebook.com/adsmanager>
- 소액 캠페인을 수동으로 집행한다.
- 목적:
  - 실제 광고 구조 확인
  - Insights 응답 샘플 확보
  - reader/writer 테스트 기준 데이터 확보

---

## 2. 병렬 진행 흐름

```text
지금 동시 시작:

Business Verification 신청
  └─ 시간이 가장 오래 걸리므로 즉시 신청

앱 생성 + 자산 연결 + Marketing API 추가 + 토큰 발급
  └─ Insights 500콜 적립 시작

위 두 흐름 완료 후:
  └─ App Review + Marketing API Access Tier Advanced 신청

병렬:
  └─ Ads Manager 소액 캠페인으로 골든샘플 확보
```

우선순위는 `Business Verification`과 `Insights 500콜 적립`이다.

---

## 3. App Review 요청 권한

### Reader 권한

| 권한 | 용도 |
|---|---|
| `ads_read` | 광고 게시물 성과 읽기. A파트 reader 핵심 권한 |
| `instagram_basic` | Instagram 일반 게시물 및 미디어 읽기 |
| `instagram_manage_insights` | Instagram 게시물 인사이트 읽기. 도달, 노출, 참여 등 오가닉 성과 비교용 |
| `pages_show_list` | 페이지 목록 조회. Instagram 계정이 연결된 Facebook 페이지 찾기 |
| `pages_read_engagement` | Facebook 페이지 게시물 및 참여 데이터 읽기 |
| `pages_read_user_content` | 페이지 게시물 및 댓글 콘텐츠 읽기 |
| `read_insights` | 페이지 및 게시물 인사이트 읽기 |

### Writer 권한

| 권한 | 용도 |
|---|---|
| `ads_management` | 광고 생성, 수정, 예산 변경, pause. `writer.py` 핵심 권한 |
| `pages_manage_posts` | Facebook 페이지 게시 |
| `instagram_content_publish` | Instagram 게시 |
| `business_management` | 비즈니스 자산 관리가 필요한 경우 사용 |

---

## 4. 앱 설정에 미리 준비할 항목

- 개인정보처리방침 URL, HTTPS 필수
- 이용약관 URL, HTTPS 필수
- 앱 아이콘
- OAuth 리디렉트 URI
  - ClickMe 콜백 URL
  - 예: `https://<clickme-domain>/auth/meta/callback`

---

## 5. 환경변수

실제 값은 `.env` 또는 시크릿 매니저에 저장한다. 문서에는 토큰과 앱 시크릿을 직접 남기지 않는다.

```env
META_TOKEN_READ=<60일 reader용 Meta access token>
META_API_VERSION=v21.0

META_APP_ID=1364757435562410
META_APP_SECRET=<Meta app secret>
META_BUSINESS_ID=1735649427615338
META_AD_ACCOUNT_ID=act_882448327559337
META_PAGE_ID=1206025682584276
META_IG_USER_ID=<Instagram 비즈니스 계정 숫자 ID>
```

### 현재 확인된 값

| 항목 | 값 |
|---|---|
| `META_API_VERSION` | `v21.0` |
| `META_APP_ID` | `1364757435562410` |
| `META_BUSINESS_ID` | `1735649427615338` |
| `META_AD_ACCOUNT_ID` | `act_882448327559337` |
| `META_PAGE_ID` | `1206025682584276` |
| `META_IG_USER_ID` | 미확인 |

---

## 6. Instagram 비즈니스 계정 ID 확인 방법

`META_IG_USER_ID`는 Instagram 핸들이 아니라 숫자 ID다.

1. Facebook 페이지 ID가 준비되어 있어야 한다.
2. Graph API Explorer 또는 reader 코드에서 아래 Graph API를 호출한다.

```http
GET /{META_PAGE_ID}?fields=instagram_business_account
```

예상 응답:

```json
{
  "instagram_business_account": {
    "id": "1784..."
  },
  "id": "1206025682584276"
}
```

응답의 `instagram_business_account.id` 값을 `META_IG_USER_ID`에 저장한다.

---

## 7. Insights 첫 호출 체크리스트

### 광고 계정 Insights

```http
GET /act_882448327559337/insights
  ?fields=campaign_id,campaign_name,impressions,reach,clicks,spend,cpc,ctr
  &date_preset=last_7d
```

필요 권한:

- `ads_read`

### Instagram 오가닉 미디어 목록

```http
GET /{META_IG_USER_ID}/media
  ?fields=id,caption,media_type,media_url,permalink,timestamp
```

필요 권한:

- `instagram_basic`

### Instagram 미디어 인사이트

```http
GET /{IG_MEDIA_ID}/insights
  ?metric=impressions,reach,engagement
```

필요 권한:

- `instagram_manage_insights`

---

## 8. App Review 제출 준비 메모

### `ads_read`

- 사용 목적: 광고 성과 지표를 읽어 노출 저하, 클릭 저하, 예산 소진, 소재 성과 차이를 진단한다.
- 화면 또는 기능 증빙: 광고 계정 선택, 캠페인 목록, 캠페인별 Insights 조회 화면.

### `ads_management`

- 사용 목적: 사용자 승인 이후 광고 pause, 예산 변경, 소재 교체 또는 신규 캠페인 생성 요청을 실행한다.
- 안전장치:
  - 사용자 승인 없이는 writer 실행 불가
  - Tier 정책 적용
  - 예산 한도 및 idempotency key 적용
  - 감사 로그 저장

### `instagram_basic`

- 사용 목적: 연결된 Instagram 비즈니스 계정의 미디어 목록을 읽어 광고 소재 후보 및 오가닉 성과 비교에 사용한다.

### `instagram_manage_insights`

- 사용 목적: Instagram 게시물의 도달, 노출, 참여 지표를 읽어 광고 성과와 비교한다.

### `pages_show_list`

- 사용 목적: 사용자의 Facebook 페이지 목록을 조회하고, 해당 페이지에 연결된 Instagram 비즈니스 계정을 찾는다.

### `pages_read_engagement`

- 사용 목적: Facebook 페이지 게시물과 참여 데이터를 읽어 소재 성과 및 페이지 반응을 비교한다.

### `pages_read_user_content`

- 사용 목적: 페이지 게시물과 댓글 콘텐츠를 읽어 광고 소재 맥락과 사용자 반응을 분석한다.

### `read_insights`

- 사용 목적: 페이지 및 게시물 인사이트를 읽어 오가닉 성과와 광고 성과를 비교한다.

### `business_management`

- 사용 목적: 비즈니스 자산, 광고계정, 페이지, Instagram 비즈니스 계정 연결 상태를 확인하고 System User 기반 운영 토큰을 관리한다.

---

## 9. 보안 운영 원칙

- access token과 app secret은 문서, Git 커밋, 로그에 남기지 않는다.
- HTTP client 로그에는 `access_token`, `app_secret`, `appsecret_proof`를 마스킹한다.
- reader 토큰과 writer 토큰은 분리한다.
- writer 토큰은 최소 권한으로 운영하고, 승인된 실행 경로에서만 사용한다.
- 장기 운영은 개인 토큰보다 System User 토큰을 우선한다.
- 토큰 검증은 Access Token Debugger로 주기적으로 확인한다.

---

## 10. 다음 작업

- [ ] `META_IG_USER_ID` 숫자 ID 확인
- [ ] reader용 Insights 첫 호출 구현 또는 수동 호출 검증
- [ ] 15일 500콜 적립 스크립트 또는 작업 스케줄 준비
- [ ] App Review 권한별 제출 사유와 화면 증빙 준비
- [ ] Ads Manager 소액 캠페인으로 골든샘플 생성
- [ ] Business Verification 신청 상태 추적
