'use client';

// 알림 센터 — management 이상감지 + center 제안을 병합해 아코디언으로 표시. 스펙 §5.
// 접힘=제목만·단일 오픈·열 때 읽음. 상세: 시뮬제안→시안3개 / 제너제안→시뮬요약 / management→기존 상세+액션.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, type CenterNotificationItem } from '@/lib/api';
import { useProjects } from '../ProjectContext';
import { useNotificationStream } from '../manage/notifications/useNotificationStream';
import type { CenterSegment } from './CenterFilterBar';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const ANOMALY_LABEL: Record<string, string> = {
  no_delivery: '노출 0 감지',
  quality_degraded: 'CTR 하락',
  budget_exhausted: '예산 조기 소진',
};

type SuggCandidate = {
  idx?: number;
  copy?: { headline?: string; body?: string; cta?: string };
  image_url?: string | null;
};

function imgSrc(u?: string | null): string | null {
  if (!u) return null;
  return u.startsWith('/') ? `${API_BASE}${u}` : u;
}

function pstr(p: Record<string, unknown> | undefined, key: string): string | undefined {
  const v = p?.[key];
  return typeof v === 'string' ? v : undefined;
}

// 접힘 상태 제목 — 종류별 간결 라벨(스펙 §5.3).
function titleOf(n: CenterNotificationItem): string {
  if (n.source === 'center_suggestion') {
    if (n.suggestion_type === 'sim_suggest') return '시뮬레이션 제안';
    if (n.suggestion_type === 'gen_suggest') return '제너레이터 제안';
    if (n.suggestion_type === 'launch_suggest') return '집행 제안';
    return '제안';
  }
  const p = n.payload;
  if (pstr(p, 'kind') === 'account') return pstr(p, 'title') || '계정 점검';
  const camp = pstr(p, 'campaign_name') || n.campaign_id || '';
  return `${camp} — ${ANOMALY_LABEL[pstr(p, 'anomaly_type') ?? ''] || '이상 감지'}`;
}

function pct(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '—';
}

export default function AlarmCenter({
  projectId,
  segment,
  role,
  orgKey,
  onOpenChat,
}: {
  projectId: string;
  segment: CenterSegment;
  role: string | undefined;
  orgKey?: string; // 변경 시 재조회 트리거(ADMIN 기업 전환 — projectId 불변이어도 스코프가 바뀜)
  onOpenChat?: (sessionId: string, projectId: string) => void; // 상담하기 → 센터 채팅 탭 열기
}) {
  const router = useRouter();
  const { selectProject } = useProjects();
  const [items, setItems] = useState<CenterNotificationItem[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  // gen_suggest 상세용 — 열 때 시뮬 요약을 lazy 로드(source_sim_id → result-summary 재사용).
  const [genSummary, setGenSummary] = useState<Record<string, unknown> | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.center.notifications(projectId || undefined);
      setItems(r.items || []);
    } catch {
      setItems([]);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load, orgKey]);

  // 운영 알림 SSE — 변경 신호 시 목록 재조회(management 스트림, center 제안은 폴링/열람으로 갱신).
  useNotificationStream(!!role, load);

  // 세그먼트 필터 — read_at 기준(스펙 §4).
  const visible = useMemo(
    () =>
      items.filter((n) => {
        if (segment === 'unread') return !n.read_at;
        if (segment === 'read') return !!n.read_at;
        return true;
      }),
    [items, segment],
  );

  // 아코디언 토글 — 열 때 읽음 처리(진입 일괄 아님). 단일 오픈.
  const toggle = async (n: CenterNotificationItem) => {
    if (openId === n.id) {
      setOpenId(null);
      return;
    }
    setOpenId(n.id);
    setGenSummary(null);
    if (!n.read_at) {
      try {
        if (n.source === 'center_suggestion') await api.center.readSuggestion(n.id);
        else await api.management.notifications.read([n.id]);
        setItems((prev) =>
          prev.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)),
        );
      } catch {
        /* best-effort */
      }
    }
    if (n.suggestion_type === 'gen_suggest' && n.source_sim_id) {
      setSummaryLoading(true);
      try {
        const s = await api.chat.resultSummary('sim', n.source_sim_id);
        setGenSummary(s);
      } catch {
        setGenSummary(null);
      } finally {
        setSummaryLoading(false);
      }
    }
  };

  // 지금 점검 — 수동 스캔(management). 보호장치 detail 그대로 안내.
  const onScan = async () => {
    setScanning(true);
    setNotice(null);
    try {
      const r = await api.management.notifications.notifyScan();
      if (r.delivered > 0) setNotice(`점검 완료 — 새 알림 ${r.delivered}건`);
      else {
        const reasons = r.skipped.map((s) => s.reason).join(', ');
        setNotice(`점검 완료 — 새 알림 없음${reasons ? ` (${reasons})` : ''}`);
      }
      load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '점검에 실패했어요.');
    } finally {
      setScanning(false);
    }
  };

  // 상담하기 — management 알림 → 세션 심기 후 센터 채팅 탭에서 열기.
  const onConsult = async (n: CenterNotificationItem) => {
    setBusyId(n.id);
    try {
      const r = await api.management.notifications.consult(n.id);
      if (r.status === 'consult') {
        if (n.project_id) selectProject(n.project_id);
        onOpenChat?.(r.session_id, n.project_id || '');
      } else if (r.status === 'normal') {
        setNotice(r.message || '다시 확인하니 지금은 정상이에요.');
      } else {
        setNotice('이미 처리된 알림이에요.');
      }
      load();
    } catch {
      setNotice('상담 준비에 실패했어요.');
    } finally {
      setBusyId(null);
    }
  };

  // 무시 — management resolve / center 제안 dismiss.
  const onIgnore = async (n: CenterNotificationItem, resolution: 'ignored' | 'actioned' = 'ignored') => {
    setBusyId(n.id);
    try {
      if (n.source === 'center_suggestion') await api.center.dismissSuggestion(n.id);
      else await api.management.notifications.resolve(n.id, resolution);
      setItems((prev) => prev.filter((x) => x.id !== n.id));
    } catch {
      setNotice('처리에 실패했어요.');
    } finally {
      setBusyId(null);
    }
  };

  // 제안 액션 프리필 이동 — 대상 프로젝트를 선택 컨텍스트로 잡고 해당 페이지로 이동(스펙 §5.3).
  const goPrefill = (n: CenterNotificationItem, path: string) => {
    if (n.project_id) selectProject(n.project_id);
    router.push(path);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280]">
          {visible.length}건
        </span>
        <button
          type="button"
          disabled={scanning}
          onClick={onScan}
          className="rounded-md border border-[#E5E8EB] px-2 py-1 text-xs text-[#4E5968] hover:border-[#3182F6] disabled:opacity-50 dark:border-[#2D3748] dark:text-[#9CA3AF]"
        >
          {scanning ? '점검 중…' : '지금 점검'}
        </button>
      </div>
      {notice && <div className="bg-[#3182F6]/5 px-3 py-2 text-xs text-[#3182F6]">{notice}</div>}
      <div className="flex-1 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="px-4 py-10 text-center text-xs text-[#8B95A1]">새 알림이 없어요.</p>
        ) : (
          visible.map((n) => {
            const open = openId === n.id;
            return (
              <div
                key={n.id}
                className="border-b border-[#F2F4F6] dark:border-[#2D3748]/60"
              >
                <button
                  type="button"
                  onClick={() => toggle(n)}
                  className="flex w-full items-center gap-2 px-3 py-3 text-left hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D]"
                >
                  {!n.read_at && <span className="h-2 w-2 shrink-0 rounded-full bg-[#F04452]" />}
                  <span
                    className={`flex-1 truncate text-sm ${
                      n.read_at
                        ? 'text-[#4E5968] dark:text-[#9CA3AF]'
                        : 'font-medium text-[#191F28] dark:text-white'
                    }`}
                  >
                    {titleOf(n)}
                  </span>
                  <svg
                    className={`h-4 w-4 shrink-0 text-[#8B95A1] transition-transform ${open ? 'rotate-90' : ''}`}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
                {open && (
                  <div className="px-3 pb-3 text-xs text-[#4E5968] dark:text-[#9CA3AF]">
                    {renderDetail(n)}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );

  // 종류별 상세 + 액션.
  function renderDetail(n: CenterNotificationItem) {
    const meta = (
      <p className="mb-2 text-[11px] text-[#8B95A1]">
        {n.project_name || '프로젝트'}
        {n.created_at ? ` · ${new Date(n.created_at).toLocaleString('ko-KR')}` : ''}
      </p>
    );

    if (n.source === 'center_suggestion') {
      if (n.suggestion_type === 'sim_suggest') {
        const cands = (n.payload?.candidates as SuggCandidate[] | undefined) ?? [];
        return (
          <div>
            {meta}
            <p className="mb-2">{pstr(n.payload, 'message') || '생성된 시안으로 반응을 예측해 볼까요?'}</p>
            <div className="mb-2 flex gap-1.5">
              {cands.map((c, i) => {
                const src = imgSrc(c.image_url);
                return (
                  <div key={i} className="flex-1 overflow-hidden rounded-lg border border-[#E5E8EB] dark:border-[#2D3748]">
                    {src ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={src} alt={`시안 ${i + 1}`} className="h-16 w-full object-cover" />
                    ) : (
                      <div className="flex h-16 items-center justify-center bg-[#F2F4F6] text-[10px] text-[#8B95A1] dark:bg-[#252D3D]">
                        시안 {i + 1}
                      </div>
                    )}
                    <p className="truncate px-1 py-0.5 text-[10px]">{c.copy?.headline || ''}</p>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => goPrefill(n, '/simulation')}
              className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-medium text-white"
            >
              시뮬레이션 돌리기
            </button>
          </div>
        );
      }
      if (n.suggestion_type === 'gen_suggest') {
        return (
          <div>
            {meta}
            <p className="mb-2">{pstr(n.payload, 'message') || '시뮬 결과에 맞춘 개선 시안을 생성해 보시겠어요?'}</p>
            {summaryLoading ? (
              <p className="mb-2 text-[11px] text-[#8B95A1]">시뮬 요약 불러오는 중…</p>
            ) : genSummary ? (
              <div className="mb-2 grid grid-cols-2 gap-1 rounded-lg bg-[#F9FAFB] p-2 dark:bg-[#252D3D]">
                <Kpi label="클릭 의향률" value={pct(genSummary.click_intent_rate)} />
                <Kpi label="거부율" value={pct(genSummary.rejection_rate)} />
                <Kpi label="구매의도" value={String(genSummary.purchase_intent ?? '—')} />
                <Kpi label="신뢰도" value={String(genSummary.trust_avg ?? '—')} />
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => goPrefill(n, '/generator')}
              className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-medium text-white"
            >
              생성해 보기
            </button>
          </div>
        );
      }
      // launch_suggest — 판정 기준 미확정(open-decisions §1). 상세·액션 최소만.
      return (
        <div>
          {meta}
          <p className="mb-2">{pstr(n.payload, 'message') || '결과가 좋아요. 집행을 검토해 보세요.'}</p>
          <button
            type="button"
            onClick={() => onIgnore(n)}
            disabled={busyId === n.id}
            className="rounded-lg border border-[#E5E8EB] px-3 py-1.5 text-xs text-[#4E5968] disabled:opacity-50 dark:border-[#2D3748] dark:text-[#9CA3AF]"
          >
            확인
          </button>
        </div>
      );
    }

    // management 이상감지 — 기존 상세 + 상담/무시(계정 알림은 [확인]만).
    const isAccount = pstr(n.payload, 'kind') === 'account';
    return (
      <div>
        {meta}
        {isAccount && pstr(n.payload, 'message') && <p className="mb-2">{pstr(n.payload, 'message')}</p>}
        {(n.followup_count ?? 0) > 0 && (
          <p className="mb-2 text-[11px] text-[#8B95A1]">{(n.followup_count ?? 0) + 1}회째 알림</p>
        )}
        <div className="flex gap-2">
          {!isAccount && (
            <button
              type="button"
              disabled={busyId === n.id}
              onClick={() => onConsult(n)}
              className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              상담하기
            </button>
          )}
          <button
            type="button"
            disabled={busyId === n.id}
            onClick={() => onIgnore(n, isAccount ? 'actioned' : 'ignored')}
            className="rounded-lg border border-[#E5E8EB] px-3 py-1.5 text-xs text-[#4E5968] disabled:opacity-50 dark:border-[#2D3748] dark:text-[#9CA3AF]"
          >
            {isAccount ? '확인' : '무시'}
          </button>
        </div>
      </div>
    );
  }
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-[#8B95A1]">{label}</p>
      <p className="text-xs font-medium text-[#191F28] dark:text-white">{value}</p>
    </div>
  );
}
