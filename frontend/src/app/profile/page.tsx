'use client';

// 내 정보 관리 — 본인 이름·전화번호·연락 이메일 수정 + 비밀번호 변경.

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { useAuth } from '@/components/AuthProvider';
import { authApi } from '@/lib/authApi';

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors';

// 숫자만 추출 후 000-0000-0000 형태로 포맷 (최대 11자리)
const formatPhone = (v: string) => {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">{label}</label>
      {children}
    </div>
  );
}

export default function ProfilePage() {
  const { user, token, login } = useAuth();

  const [name, setName] = useState(user?.name ?? '');
  const [phone, setPhone] = useState(formatPhone(user?.phone_num ?? ''));
  const [email, setEmail] = useState(user?.user_email ?? '');
  const [savingInfo, setSavingInfo] = useState(false);
  const [infoMsg, setInfoMsg] = useState('');

  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [savingPw, setSavingPw] = useState(false);
  const [pwMsg, setPwMsg] = useState('');

  const saveInfo = async () => {
    if (!token) return;
    setInfoMsg('');
    if (!name.trim()) { setInfoMsg('이름을 입력해주세요.'); return; }
    if (email.trim() && !EMAIL_RE.test(email.trim())) { setInfoMsg('올바른 이메일 형식이 아닙니다.'); return; }
    setSavingInfo(true);
    try {
      const updated = await authApi.updateProfile(token, {
        name: name.trim(),
        phone_num: phone.trim() || null,
        user_email: email.trim() || null,
      });
      login(token, updated);
      setInfoMsg('저장되었습니다.');
    } catch (err) {
      setInfoMsg(err instanceof Error ? err.message : '저장에 실패했습니다.');
    } finally {
      setSavingInfo(false);
    }
  };

  const savePw = async () => {
    if (!token) return;
    setPwMsg('');
    if (pw.length < 8) { setPwMsg('비밀번호는 8자 이상이어야 합니다.'); return; }
    if (pw !== confirm) { setPwMsg('비밀번호가 일치하지 않습니다.'); return; }
    setSavingPw(true);
    try {
      await authApi.changePassword(token, pw);
      const fresh = await authApi.me(token);
      login(token, fresh);
      setPw(''); setConfirm('');
      setPwMsg('비밀번호가 변경되었습니다.');
    } catch (err) {
      setPwMsg(err instanceof Error ? err.message : '변경에 실패했습니다.');
    } finally {
      setSavingPw(false);
    }
  };

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">내 정보 관리</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">이름·연락처를 수정하고 비밀번호를 변경할 수 있습니다</p>
        </div>

        {/* 기본 정보 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 space-y-4">
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">기본 정보</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="아이디">
              <p className="px-3 py-2.5 text-sm text-[#8B95A1] dark:text-[#6B7280] bg-[#F9FAFB] dark:bg-[#252D3D] rounded-xl">{user?.login_id ?? '-'}</p>
            </Field>
            <Field label="역할">
              <p className="px-3 py-2.5 text-sm text-[#8B95A1] dark:text-[#6B7280] bg-[#F9FAFB] dark:bg-[#252D3D] rounded-xl">{user?.role ?? '-'}</p>
            </Field>
          </div>
          <Field label="이름">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="이름" className={inputCls} />
          </Field>
          <Field label="전화번호">
            <input value={phone} onChange={(e) => setPhone(formatPhone(e.target.value))} inputMode="numeric" placeholder="010-0000-0000" className={inputCls} />
          </Field>
          <Field label="이메일">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="example@email.com" className={inputCls} />
          </Field>
          {infoMsg && (
            <p className={`text-xs px-3 py-2 rounded-lg ${infoMsg === '저장되었습니다.' ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20' : 'text-red-500 bg-red-50 dark:bg-red-900/20'}`}>{infoMsg}</p>
          )}
          <div className="flex justify-end">
            <button onClick={saveInfo} disabled={savingInfo}
              className="px-5 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              {savingInfo ? '저장 중...' : '저장'}
            </button>
          </div>
        </div>

        {/* 비밀번호 변경 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 space-y-4">
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">비밀번호 변경</p>
          <Field label="새 비밀번호">
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="8자 이상" className={inputCls} />
          </Field>
          <Field label="새 비밀번호 확인">
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="다시 입력" className={inputCls} />
          </Field>
          {pwMsg && (
            <p className={`text-xs px-3 py-2 rounded-lg ${pwMsg === '비밀번호가 변경되었습니다.' ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20' : 'text-red-500 bg-red-50 dark:bg-red-900/20'}`}>{pwMsg}</p>
          )}
          <div className="flex justify-end">
            <button onClick={savePw} disabled={savingPw}
              className="px-5 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              {savingPw ? '변경 중...' : '비밀번호 변경'}
            </button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
