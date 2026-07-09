'use client';

// 조직 관리 — 전체 조직 목록(정렬·무한스크롤). ACTIVE는 메인 테이블, INACTIVE는 하단 패널(복원/영구삭제).

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';
import { useInfiniteList } from '@/components/admin/useInfiniteList';
import {
  OrgUserControls,
  ORG_SORT_OPTIONS,
  sortToParams,
  type SortValue,
} from '@/components/admin/OrgUserControls';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Organization = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  owner_login_id: string | null;
  owner_name: string | null;
};

const orgStatusStyle: Record<string, string> = {
  ACTIVE: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  INACTIVE: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const orgStatusLabel: Record<string, string> = { ACTIVE: '활성', INACTIVE: '비활성' };

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-surface-2 text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary transition-colors';

// ── 조직 생성 모달 — 회사명 + 담당(오너) 계정을 함께 만든다 ──────────────
function CreateOrgModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [companyName, setCompanyName] = useState('');
  const [name, setName] = useState('');
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError('');
    if (!companyName.trim()) {
      setError('회사명을 입력해주세요.');
      return;
    }
    if (!name.trim() || !loginId.trim() || password.length < 8) {
      setError('담당자 이름·아이디·비밀번호(8자 이상)를 확인해주세요.');
      return;
    }
    setSaving(true);
    const res = await authedFetch(`${API_BASE}/api/admin/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        login_id: loginId.trim(),
        password,
        role: 'COMPANY',
        company_name: companyName.trim(),
      }),
    });
    setSaving(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '생성 실패' }));
      setError(err.detail ?? '조직 생성에 실패했습니다.');
      return;
    }
    onCreated();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-ink mb-1">조직 생성</h2>
        <p className="text-xs text-ink-tertiary mb-4">회사와 담당(오너) 계정을 함께 만듭니다.</p>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">회사명</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="(주)클릭미" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">담당자 이름</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">아이디</label>
            <input value={loginId} onChange={(e) => setLoginId(e.target.value)} placeholder="로그인 아이디" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">비밀번호</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="8자 이상" className={inputCls} />
          </div>
          {error && (
            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-line rounded-xl text-ink-secondary hover:bg-accent transition-colors">
            취소
          </button>
          <button onClick={submit} disabled={saving}
            className="flex-1 py-2.5 text-sm font-medium bg-primary text-primary-foreground rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? '생성 중...' : '조직 생성'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminCompaniesPage() {
  const [sort, setSort] = useState<SortValue>('created_at:desc');
  const [refresh, setRefresh] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const { sort: sortCol, order } = sortToParams(sort);

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/admin/organizations?limit=${limit}&offset=${offset}&sort=${sortCol}&order=${order}`,
      )
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => (Array.isArray(d) ? (d as Organization[]) : [])),
    [sortCol, order],
  );

  // resetKey에 refresh를 섞어 삭제/복원/영구삭제 후 첫 페이지부터 재로드.
  const resetKey = `${sort}#${refresh}`;
  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Organization>(
    fetcher,
    resetKey,
  );

  // 무한스크롤로 받은 목록을 상태별로 분리 — 활성은 메인, 비활성은 하단 패널.
  const activeOrgs = items.filter((o) => o.status === 'ACTIVE');
  const inactiveOrgs = items.filter((o) => o.status === 'INACTIVE');

  const handleDelete = async (id: string, name: string) => {
    if (
      !confirm(
        `'${name}' 조직을 비활성화할까요?\n소속 계정 로그인이 차단됩니다. (데이터는 보존되며 복원할 수 있습니다.)`,
      )
    )
      return;
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('비활성화에 실패했습니다.');
      return;
    }
    setRefresh((n) => n + 1);
  };

  const handleRestore = async (id: string, name: string) => {
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}/restore`, {
      method: 'POST',
    });
    if (!res.ok) {
      alert(`'${name}' 복원에 실패했습니다.`);
      return;
    }
    setRefresh((n) => n + 1);
  };

  const handlePurge = async (id: string, name: string) => {
    if (
      !confirm(
        `'${name}' 조직을 영구 삭제할까요?\n\n소속 프로젝트/시뮬/제너/채팅까지 전부 삭제됩니다. 이 작업은 되돌릴 수 없습니다.`,
      )
    )
      return;
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}/purge`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      alert('영구 삭제에 실패했습니다.');
      return;
    }
    setRefresh((n) => n + 1);
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">조직 관리</h1>
          <p className="text-sm text-ink-tertiary mt-1">전체 조직을 조회·관리하세요</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="shrink-0 px-4 py-2.5 text-sm font-medium bg-primary text-primary-foreground rounded-xl hover:bg-primary-hover transition-colors">
          + 조직 생성
        </button>
      </div>

      <OrgUserControls sort={sort} onSort={setSort} sortOptions={ORG_SORT_OPTIONS} />

      {/* 활성 조직 */}
      <div className="bg-card border border-line rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-line">
          <p className="text-sm font-semibold text-ink">전체 조직</p>
        </div>
        {loading ? (
          <div className="py-16 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : activeOrgs.length === 0 ? (
          <div className="py-16 text-center text-sm text-ink-tertiary">활성 조직이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">회사명</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">담당 계정</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {activeOrgs.map((o) => (
                <tr key={o.id} className="border-b border-line last:border-0 hover:bg-accent transition-colors">
                  <td className="px-6 py-4 font-medium text-ink">{o.name}</td>
                  <td className="px-4 py-4 text-ink-secondary">
                    {o.owner_name ? `${o.owner_name} (${o.owner_login_id})` : '—'}
                  </td>
                  <td className="px-4 py-4">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[o.status] ?? ''}`}>
                      {orgStatusLabel[o.status] ?? o.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-ink-tertiary">{formatKSTDate(o.created_at)}</td>
                  <td className="px-4 py-4 text-right">
                    <button onClick={() => handleDelete(o.id, o.name)}
                      className="px-3 py-1.5 text-xs text-ink-tertiary rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors">삭제</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} className="h-1" />
        {loadingMore && <p className="text-center text-[12px] text-ink-tertiary py-3">더 불러오는 중…</p>}
        {!hasMore && !loading && items.length > 0 && (
          <p className="text-center text-[12px] text-ink-muted py-3">모두 불러왔어요</p>
        )}
      </div>

      {/* 비활성화된 조직 — 무한스크롤로 로드된 목록에서 INACTIVE만 모아 표시. */}
      {inactiveOrgs.length > 0 && (
        <div className="bg-card border border-red-100 dark:border-red-900/30 rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-line">
            <p className="text-sm font-semibold text-red-500">비활성화된 조직</p>
            <p className="text-xs text-ink-tertiary mt-0.5">복원하거나 영구 삭제할 수 있습니다</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">회사명</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">담당 계정</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {inactiveOrgs.map((o) => (
                <tr key={o.id} className="border-b border-line last:border-0 hover:bg-accent transition-colors">
                  <td className="px-6 py-4 font-medium text-ink">{o.name}</td>
                  <td className="px-4 py-4 text-ink-secondary">
                    {o.owner_name ? `${o.owner_name} (${o.owner_login_id})` : '—'}
                  </td>
                  <td className="px-4 py-4">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[o.status] ?? ''}`}>
                      {orgStatusLabel[o.status] ?? o.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-ink-tertiary">{formatKSTDate(o.created_at)}</td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => handleRestore(o.id, o.name)}
                        className="px-3 py-1.5 text-xs text-primary border border-primary/30 rounded-lg hover:bg-primary-subtle transition-colors">복원</button>
                      <button onClick={() => handlePurge(o.id, o.name)}
                        className="px-3 py-1.5 text-xs text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors">영구삭제</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateOrgModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); setRefresh((n) => n + 1); }}
        />
      )}
    </div>
  );
}
