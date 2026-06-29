// SSE 자동 재연결(X2) — 끊긴 스트림을 지수 backoff로 재구독한다.
// 연결이 stabilityMs 이상 유지되면 "안정적"이라 보고 backoff 예산을 리셋한다.
// (메시지 1건마다 리셋하면, 즉시 끊기는 스트림이 무한 재연결되므로 onopen 기준으로 본다.)
// 종료 이벤트(isTerminal)면 더 재연결하지 않는다. 백엔드 stream은 재구독 시 리플레이되어 안전.

type ReconnectOpts = {
  onEvent: (data: unknown) => void; // 파싱된 이벤트 1건
  onGiveUp?: (reason: string) => void; // 최대 재시도 초과 시
  isTerminal?: (data: unknown) => boolean; // 이 이벤트면 정상 종료(재연결 중단)
  maxRetries?: number; // 기본 5
  baseMs?: number; // 기본 1000
  capMs?: number; // 기본 15000 (지수 backoff 상한)
  stabilityMs?: number; // 이 시간 이상 연결 유지 시 backoff 리셋(기본 3000)
  label?: string; // 콘솔 로그 라벨
};

// makeES: 매 (재)연결마다 새 EventSource를 만드는 팩토리(api.*.stream(id) 재사용).
// 반환값: 구독을 종료하는 close 함수(언마운트/취소 시 호출).
export function openReconnectingStream(
  makeES: () => EventSource,
  opts: ReconnectOpts
): () => void {
  const {
    onEvent,
    onGiveUp,
    isTerminal,
    maxRetries = 5,
    baseMs = 1000,
    capMs = 15000,
    stabilityMs = 3000,
    label = 'sse',
  } = opts;

  let es: EventSource | null = null;
  let retries = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stableTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const clearStable = () => {
    if (stableTimer) {
      clearTimeout(stableTimer);
      stableTimer = null;
    }
  };

  const close = () => {
    closed = true;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    clearStable();
    es?.close();
    es = null;
  };

  const connect = () => {
    if (closed) return;
    es = makeES();
    es.onopen = () => {
      // 연결이 일정 시간 유지되면 안정적이라 보고 재연결 예산 회복.
      clearStable();
      stableTimer = setTimeout(() => {
        retries = 0;
      }, stabilityMs);
    };
    es.onmessage = (ev: MessageEvent) => {
      let data: unknown;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      onEvent(data);
      if (isTerminal?.(data)) close();
    };
    es.onerror = () => {
      clearStable();
      es?.close();
      es = null;
      if (closed) return;
      if (retries >= maxRetries) {
        console.log(`[${label}] reconnect gave up after ${retries} retries`);
        onGiveUp?.('스트림 연결이 끊겼어요. 잠시 후 다시 시도해주세요.');
        close();
        return;
      }
      const delay = Math.min(baseMs * 2 ** retries, capMs);
      retries += 1;
      console.log(
        `[${label}] disconnected — reconnect attempt ${retries} in ${delay}ms`
      );
      timer = setTimeout(connect, delay);
    };
  };

  connect();
  return close;
}

// 지수 backoff 지연 계산(테스트·재사용용).
export function backoffDelay(
  retry: number,
  baseMs = 1000,
  capMs = 15000
): number {
  return Math.min(baseMs * 2 ** retry, capMs);
}
