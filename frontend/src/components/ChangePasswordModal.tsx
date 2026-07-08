'use client';

// 발급 계정 최초 로그인 시 비밀번호 변경 유도 모달.

import { useState } from 'react';
import { useAuth } from './AuthProvider';
import { authApi } from '@/lib/authApi';

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-white dark:bg-[#252D3D] text-ink placeholder-[#B0B8C1] focus:outline-none focus:border-[#2563EB] transition-colors';

export default function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const { token, login, user } = useAuth();
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError('');
    if (pw.length < 8) { setError('비밀번호는 8자 이상이어야 합니다.'); return; }
    if (pw !== confirm) { setError('비밀번호가 일치하지 않습니다.'); return; }
    if (!token) return;
    setSaving(true);
    try {
      await authApi.changePassword(token, pw);
      const fresh = await authApi.me(token); // must_change_password 갱신 반영
      login(token, fresh);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '변경에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-ink mb-1">비밀번호를 변경해주세요</h2>
        <p className="text-xs text-ink-tertiary mb-4">
          {user?.name}님은 발급된 임시 비밀번호로 로그인했습니다. 보안을 위해 새 비밀번호로 변경하세요.
        </p>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">새 비밀번호</label>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
              placeholder="8자 이상" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">새 비밀번호 확인</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
              placeholder="다시 입력" className={inputCls} />
          </div>
          {error && (
            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-line rounded-xl text-ink-secondary hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">
            나중에
          </button>
          <button onClick={submit} disabled={saving}
            className="flex-1 py-2.5 text-sm font-medium bg-[#2563EB] text-white rounded-xl hover:bg-[#1D4ED8] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? '변경 중...' : '변경하기'}
          </button>
        </div>
      </div>
    </div>
  );
}
