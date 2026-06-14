'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { authApi } from '@/lib/authApi';

type AccountType = 'company' | 'user';

const inputCls =
  'w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white dark:bg-[#252D3D]';

export default function SignUpPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [accountType, setAccountType] = useState<AccountType | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [organizationId, setOrganizationId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) { setError('비밀번호는 8자 이상이어야 합니다.'); return; }
    setLoading(true);
    try {
      let res;
      if (accountType === 'company') {
        res = await authApi.signupCompany({ name, email, password, company_name: companyName });
      } else {
        if (!organizationId.trim()) { setError('회사 ID를 입력해주세요.'); setLoading(false); return; }
        res = await authApi.signupUser({ name, email, password, organization_id: organizationId.trim() });
      }
      login(res.access_token, res.user);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : '회원가입에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex flex-col items-center justify-center p-4 transition-colors">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="text-[#3182F6] font-bold text-2xl tracking-tight">ClickMe</Link>
          <p className="mt-2 text-sm text-[#8B95A1] dark:text-[#6B7280]">처음이라면 30초면 충분해요</p>
        </div>

        <div className="bg-white dark:bg-[#1C2333] rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-8 shadow-sm transition-colors">

          {/* ── Step 1: 계정 유형 선택 ── */}
          {!accountType ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">어떤 계정으로 가입하시나요?</p>
              <button
                onClick={() => setAccountType('company')}
                className="w-full text-left px-5 py-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center text-[#3182F6] group-hover:bg-[#3182F6] group-hover:text-white transition-colors">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="7" width="20" height="14" rx="2" />
                      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">기업 계정</p>
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">회사/팀 전용 워크스페이스 생성</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setAccountType('user')}
                className="w-full text-left px-5 py-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center text-[#3182F6] group-hover:bg-[#3182F6] group-hover:text-white transition-colors">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">개인 계정</p>
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">회사 코드로 소속 팀에 합류</p>
                  </div>
                </div>
              </button>
            </div>
          ) : (
            /* ── Step 2: 정보 입력 ── */
            <form className="space-y-4" onSubmit={handleSubmit}>
              {/* 뒤로 */}
              <button type="button" onClick={() => { setAccountType(null); setError(''); }}
                className="flex items-center gap-1 text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6] transition-colors mb-1">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
                {accountType === 'company' ? '기업 계정' : '개인 계정'} 가입
              </button>

              <div>
                <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">이름</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} required
                  placeholder="홍길동" className={inputCls} />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">이메일</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                  placeholder="example@email.com" className={inputCls} />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">비밀번호</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                  placeholder="8자 이상" className={inputCls} />
              </div>

              {accountType === 'company' ? (
                <div>
                  <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">회사명</label>
                  <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} required
                    placeholder="(주)클릭미" className={inputCls} />
                  <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1.5">
                    가입 후 관리자 승인이 완료되면 서비스를 이용할 수 있습니다.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">회사 코드 (Organization ID)</label>
                  <input type="text" value={organizationId} onChange={(e) => setOrganizationId(e.target.value)} required
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" className={inputCls} />
                  <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1.5">
                    소속 회사 담당자에게 코드를 받아 입력하세요.
                  </p>
                </div>
              )}

              {error && (
                <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
              )}

              <button type="submit" disabled={loading}
                className="w-full py-3 bg-[#3182F6] text-white font-medium rounded-xl hover:bg-[#1B6EEB] disabled:opacity-60 transition-colors">
                {loading ? '가입 중...' : '가입하기'}
              </button>
            </form>
          )}

          <div className="mt-5 pt-5 border-t border-[#F2F4F6] dark:border-[#1E2A3A]">
            <p className="text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">
              이미 계정이 있으신가요?{' '}
              <Link href="/sign-in" className="text-[#3182F6] font-medium hover:underline">로그인</Link>
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-6">
          <Link href="/" className="hover:text-[#8B95A1] transition-colors">← 메인으로 돌아가기</Link>
        </p>
      </div>
    </div>
  );
}
