# ClickMe Frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS 기반 프론트엔드.

---

## 목차

- [요구 사항](#요구-사항)
- [개발 환경 세팅](#개발-환경-세팅)
- [실행 방법](#실행-방법)
- [프로젝트 구조](#프로젝트-구조)
- [경로 alias](#경로-alias)

---

## 요구 사항

| 항목 | 버전 | 설치 방법 |
|---|---|---|
| **Node.js** | 20 이상 | [nodejs.org](https://nodejs.org) — LTS 버전 권장 |
| **pnpm** | 9 이상 | 아래 참고 |

### pnpm 설치

```bash
# Node.js 설치 후 corepack으로 활성화 (권장)
corepack enable
corepack prepare pnpm@latest --activate

# 또는 npm으로 전역 설치
npm install -g pnpm
```

설치 확인:

```bash
node -v   # v20.x.x 이상
pnpm -v   # 9.x.x 이상
```

---

## 개발 환경 세팅

### 1. 의존성 설치

```bash
cd frontend
pnpm install
```

### 2. 환경 변수 설정

```bash
cp .env.example .env.local
```

`.env.local` 파일을 열고 백엔드 URL을 채웁니다:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 실행 방법

### 개발 서버

```bash
pnpm dev           # http://localhost:3000 (Turbopack)
```

### 프로덕션 빌드

```bash
pnpm build
pnpm start
```

### 린트 / 포맷

```bash
pnpm lint          # ESLint 검사
pnpm lint:fix      # ESLint 자동 수정
pnpm format        # Prettier 포맷 적용
pnpm format:check  # Prettier 포맷 검사 (CI용)
```

---

## 프로젝트 구조

```
frontend/
├── src/
│   ├── app/                  # Next.js App Router
│   │   ├── layout.tsx        # 루트 레이아웃
│   │   ├── globals.css       # 전역 스타일 (Tailwind 진입점)
│   │   ├── page.tsx          # 홈 (/)
│   │   ├── sign-in/page.tsx  # 로그인
│   │   ├── sign-up/page.tsx  # 회원가입
│   │   ├── chat/page.tsx     # AI 채팅
│   │   ├── simulation/page.tsx
│   │   ├── generator/page.tsx
│   │   ├── manage/page.tsx
│   │   └── admin/page.tsx
│   └── components/           # 재사용 UI 컴포넌트
│       ├── Navigation.tsx
│       └── AppLayout.tsx
│
├── .env.example              # 환경 변수 템플릿
├── .prettierrc               # Prettier 규칙
├── eslint.config.js          # ESLint 규칙
├── tailwind.config.ts
├── tsconfig.json
├── next.config.ts
└── package.json
```

---

## 경로 alias

`tsconfig.json`에 `baseUrl: "src"`가 설정되어 있어 `@/` prefix로 import할 수 있습니다.

```ts
import Navigation from '@/components/Navigation';
```
