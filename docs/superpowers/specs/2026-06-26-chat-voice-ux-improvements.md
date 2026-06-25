# 채팅 음성 기능 + UX 개선 — 코드 감사 결과 (2026-06-26)

> 브랜치: `feat/management-3k`  
> 작업 범위: `frontend/src/app/(app)/chat/page.tsx`, `frontend/src/app/(app)/manage/campaigns/page.tsx`

---

## 한 장 요약

매니지먼트 프론트엔드 전체 감사 결과, 채팅 UX에서 5개의 개선 항목을 식별·구현했다.  
모든 기능은 **무료(API 키 불필요)**, 브라우저 내장 API 기반이며 빌드 에러 없음이 확인됐다.

| # | 파일 | 변경 내용 | 효과 |
|---|------|-----------|------|
| 1 | `chat/page.tsx` | Web Speech API STT 마이크 버튼 추가 | 음성으로 채팅 입력, 무료 |
| 2 | `chat/page.tsx` | Web SpeechSynthesis TTS 읽어주기 버튼 추가 | AI 답변 음성 출력, 무료 |
| 3 | `chat/page.tsx` | 마크다운 렌더러 구현 | **bold**, `code`, 리스트, 헤딩 시각 표현 |
| 4 | `chat/page.tsx` | 스트리밍 중 입력란 비활성화 제거 | AI 응답 대기 중 다음 질문 선입력 가능 |
| 5 | `chat/page.tsx` + `campaigns/page.tsx` | 캠페인 칩 딥링크 연결 | 채팅에서 특정 캠페인 직접 진입 |

---

## 상세 변경 기록

### 1. 음성 입력(STT) — Web Speech API

**문제** — 채팅 입력은 키보드 전용이었다. 모바일 또는 빠른 질의 시 음성으로 입력하려면 OS 키보드를 사용해야 했다.

**구현 방법**  
브라우저 내장 `SpeechRecognition` API (Chrome/Edge 지원, Android Chrome 포함)를 사용한다. **API 키 없음, 무료**. `.env`에 추가할 키 없음.

```typescript
// SpeechWindow 타입 정의로 window 캐스팅
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecCtor;
  webkitSpeechRecognition?: SpeechRecCtor;
};

const startVoice = () => {
  const sw = window as SpeechWindow;
  const Ctor = sw.SpeechRecognition ?? sw.webkitSpeechRecognition;
  if (!Ctor) return;
  const rec = new Ctor();
  rec.lang = 'ko-KR';           // 한국어
  rec.continuous = false;        // 한 발화 후 자동 종료
  rec.interimResults = true;     // 중간 결과 실시간 반영
  rec.onresult = (e) => {
    let t = '';
    for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
    setInput(t);  // 입력창에 자동 채움
  };
  rec.onend = () => setListening(false);
  // ...
};
```

**UX**  
- `voiceSupported` 상태로 지원 브라우저에서만 마이크 버튼 표시(숨김·뜬금없는 버튼 없음)
- 청취 중: 버튼 빨간색 + `animate-pulse`, 플레이스홀더 "듣는 중…"
- 청취 종료: 입력창에 음성 텍스트 채워짐 → 사용자가 Enter 또는 추가 편집 가능

---

### 2. 음성 출력(TTS) — Web SpeechSynthesis

**문제** — 긴 AI 답변을 눈으로 읽어야 했다. 이동 중 / 멀티태스킹 시 불편.

**구현 방법**  
브라우저 내장 `SpeechSynthesisUtterance` API. **API 키 없음, 무료**. 모든 모던 브라우저 지원.

```typescript
const speakText = (text: string) => {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ko-KR';
  u.rate = 1.1;                          // 약간 빠르게 (자연스러운 속도)
  window.speechSynthesis.cancel();        // 이전 발화 중단
  window.speechSynthesis.speak(u);
};
```

**UX**  
- 어시스턴트 메시지 아래 스피커 아이콘 버튼 표시 (`ttsSupported` 상태로 조건부)
- 클릭 시 즉시 읽기 시작, 재클릭 시 이전 발화 취소 후 재시작
- 버튼은 최소 크기(13px 아이콘)로 방해되지 않게 배치

---

### 3. 마크다운 렌더링 (`renderMarkdown`)

**문제** — 매니지먼트 어시스턴트는 `**굵게**`, `- 리스트`, `## 헤딩` 등의 마크다운으로 답변한다. 기존 `whitespace-pre-wrap` 처리로는 심볼이 그대로 노출됐다.

**구현 방법**  
외부 라이브러리 없이(react-markdown 미설치) 인라인 파서 구현.

```typescript
function renderMarkdown(text: string) {
  const parseInline = (s: string) =>
    s.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**'))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith('`') && part.endsWith('`'))
        return <code key={i} className="...font-mono">{part.slice(1, -1)}</code>;
      // ...
    });

  const nodes = text.split('\n').map((line, i) => {
    if (line.startsWith('## ')) return <p key={i} className="font-semibold ...">...</p>;
    if (line.startsWith('- '))  return <p key={i} className="flex gap-1.5">•...</p>;
    if (/^\d+\. /.test(line))  return <p key={i} className="flex gap-1.5">N....</p>;
    // ...
  });
  return <>{nodes}</>;
}
```

**지원 문법**  
`# ## ###` 헤딩 · `**bold**` · `*italic*` · `` `code` `` · `- bullet` · `• bullet` · `1. ordered`

**적용 범위** — 어시스턴트 메시지만. 사용자 메시지는 `whitespace-pre-wrap` 유지(사용자 입력 형태 보존).

---

### 4. 스트리밍 중 입력 선허용

**문제** — AI 응답 스트리밍 중 `disabled={isStreaming}` 으로 입력란이 잠겨 있었다. 긴 답변을 기다리는 동안 다음 질문을 미리 입력할 수 없었다.

**수정 전**
```tsx
<textarea
  disabled={isStreaming}  // 답변 중 완전 잠금
  ...
/>
```

**수정 후**
```tsx
<textarea
  // disabled 제거 — 선입력 허용
  placeholder={listening ? '듣는 중…' : '메시지를 입력하세요...'}
  ...
/>
// 전송 버튼만 disabled 유지
<button disabled={!input.trim() || isStreaming} ...>
```

**효과** — 답변 완료 후 즉시 다음 질문 전송 가능. Enter 전송도 `isStreaming` 체크(`handleSend` 내부)로 차단.

---

### 5. 캠페인 칩 딥링크

**문제** — 채팅에서 `live_campaigns` 도구 결과로 나타나는 캠페인 칩을 클릭하면 `/manage/campaigns`로 이동만 할 뿐, 어떤 캠페인인지 선택된 상태로 열리지 않았다.

**채팅 페이지 수정** — `href` 에 `?open=<campaign_id>` 쿼리 파라미터 추가:

```tsx
// 전:  href="/manage/campaigns"
// 후:
<Link href={`/manage/campaigns?open=${c.campaign_id}`}>
```

**캠페인 페이지 수정** — 마운트 시 URL 파라미터 읽어 해당 캠페인 상세 자동 열기:

```tsx
// campaigns/page.tsx에 추가
useEffect(() => {
  const openId = new URLSearchParams(window.location.search).get('open');
  if (openId) setSelected(openId);
}, []);
```

기존 `fetchDetail` + `detailCache` 로직이 즉시 동작해 추가 상태 없이 구현됐다.

---

## 음성 기능 구현 방법 (자는 동안 알 수 없었던 것들)

### 브라우저 지원
| 기능 | Chrome | Edge | Safari | Firefox |
|------|--------|------|--------|---------|
| STT (SpeechRecognition) | ✅ | ✅ | ✅ iOS 14.5+ | ❌ |
| TTS (speechSynthesis) | ✅ | ✅ | ✅ | ✅ |

Firefox에서 STT가 안 되지만 `voiceSupported` 상태 체크로 마이크 버튼 자체가 숨겨진다.

### 비용
- STT: **$0** — 브라우저 처리, 서버 왕복 없음
- TTS: **$0** — 브라우저 내장 음성 엔진
- Google Cloud STT / ElevenLabs / OpenAI TTS 등 유료 API 불필요

### 한국어 품질
Chrome의 `lang = 'ko-KR'` STT는 Google의 서버 기반 인식을 사용(Chrome 한정), 정확도가 높다. Safari는 온디바이스 처리로 약간 낮지만 실용적.

### 제한사항
- **HTTPS 필요** — localhost는 예외적으로 허용(개발환경 OK). 프로덕션 EC2에 SSL 필요.
- **마이크 권한** — 첫 사용 시 브라우저 권한 팝업. 거부 시 `onerror` → `setListening(false)`.
- **연속 발화** — `continuous: false` 로 한 발화 종료 시 자동 중지. 긴 발화는 중간에 끊길 수 있음.

---

## 검증 결과

```
pnpm lint    → warnings만 (기존 파일, 신규 파일 에러 없음)
pnpm build   → 성공 ✅ (TypeScript 컴파일 에러 없음)
```
