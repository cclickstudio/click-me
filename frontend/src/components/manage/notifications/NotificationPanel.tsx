// 알림 패널 — 카드 목록·프로젝트 필터·[상담하기][무시] (이상 감지 C안)
'use client';

import { useEffect, useMemo, useState } from 'react';
import { api, type ManagementNotification } from '@/lib/api';
import { useProjects } from '../../ProjectContext';
import { useChatController } from '../../chat/ChatController';

const ANOMALY_LABEL: Record<string, string> = {
  no_delivery: '노출 0 감지',
  quality_degraded: 'CTR 하락',
  budget_exhausted: '예산 조기 소진',
};

export default function NotificationPanel({
  items,
  onRefetch,
  onClose,
  onReadVisible,
}: {
  items: ManagementNotification[];
  onRefetch: () => void;
  onClose: () => void;
  onReadVisible: (ids: string[]) => void;
}) {
  const { projects, selectedProject, selectProject } = useProjects();
  const { setActiveSessionId, setFloatingOpen } = useChatController();
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const visible = useMemo(
    () => (projectFilter ? items.filter(n => n.project_id === projectFilter) : items),
    [items, projectFilter],
  );

  // 패널 열람 = 필터로 보이는 카드만 bulk read(스펙 §2) — 읽음 반영 후엔 미읽음이 없어 재호출 안 됨.
  useEffect(() => {
    const unreadIds = visible.filter(n => !n.read_at).map(n => n.id);
    if (unreadIds.length) onReadVisible(unreadIds);
  }, [visible, onReadVisible]);

  const onConsult = async (n: ManagementNotification) => {
    setBusyId(n.id);
    try {
      const r = await api.management.notifications.consult(n.id);
      if (r.status === 'consult') {
        if (selectedProject?.id !== n.project_id) selectProject(n.project_id); // org 전체 패널 — 타 프로젝트 알림
        setActiveSessionId(r.session_id);
        setFloatingOpen(true);
        onClose();
      } else if (r.status === 'normal') {
        setNotice(r.message || '다시 확인하니 지금은 정상이에요.');
      } else {
        setNotice('이미 처리된 알림이에요.');
      }
      onRefetch();
    } catch {
      setNotice('상담 준비에 실패했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusyId(null);
    }
  };

  const onIgnore = async (n: ManagementNotification) => {
    setBusyId(n.id);
    try {
      await api.management.notifications.resolve(n.id, 'ignored');
      onRefetch();
    } catch {
      setNotice('무시 처리에 실패했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="absolute right-0 top-11 z-50 w-96 max-w-[92vw] rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748]">
        <span className="text-sm font-semibold text-[#191F28] dark:text-white">운영 알림</span>
        <select
          value={projectFilter}
          onChange={e => setProjectFilter(e.target.value)}
          className="text-xs rounded-md border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2 py-1 text-[#4E5968] dark:text-[#9CA3AF]"
        >
          <option value="">전체 프로젝트</option>
          {projects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>
      {notice && (
        <div className="px-4 py-2 text-xs text-[#3182F6] bg-[#3182F6]/5">{notice}</div>
      )}
      <div className="max-h-96 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-[#8B95A1]">새 알림이 없어요.</p>
        ) : (
          visible.map(n => (
            <div key={n.id} className="px-4 py-3 border-b border-[#F2F4F6] dark:border-[#2D3748]/60">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-[#191F28] dark:text-white">
                    ⚠ {n.payload.campaign_name || n.campaign_id} —{' '}
                    {ANOMALY_LABEL[n.payload.anomaly_type ?? ''] || '이상 감지'}
                  </p>
                  <p className="mt-0.5 text-xs text-[#8B95A1]">
                    {n.project_name}
                    {n.followup_count > 0 && ` · ${n.followup_count + 1}회째 알림`}
                    {' · '}
                    {new Date(n.last_notified_at).toLocaleString('ko-KR')}
                  </p>
                </div>
                {!n.read_at && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#EF4444]" />}
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busyId === n.id}
                  onClick={() => onConsult(n)}
                  className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                >
                  상담하기
                </button>
                <button
                  type="button"
                  disabled={busyId === n.id}
                  onClick={() => onIgnore(n)}
                  className="rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-1.5 text-xs text-[#4E5968] dark:text-[#9CA3AF] disabled:opacity-50"
                >
                  무시
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
