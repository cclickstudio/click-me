'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { authApi } from '@/lib/authApi';

export default function SignInPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await authApi.login({ email, password });
      login(res.access_token, res.user);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex flex-col items-center justify-center p-4 transition-colors">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="text-[#3182F6] font-bold text-2xl tracking-tight">ClickMe</Link>
          <p className="mt-2 text-sm text-[#8B95A1] dark:text-[#6B7280]">다시 만나서 반가워요</p>
        </div>

        <div className="bg-white dark:bg-[#1C2333] rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-8 shadow-sm transition-colors">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">이메일</label>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                placeholder="example@email.com"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white dark:bg-[#252D3D]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">비밀번호</label>
              <input
                type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                placeholder="••••••••"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white dark:bg-[#252D3D]"
              />
            </div>

            {error && (
              <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full py-3 bg-[#3182F6] text-white font-medium rounded-xl hover:bg-[#1B6EEB] disabled:opacity-60 transition-colors mt-2"
            >
              {loading ? '로그인 중...' : '로그인'}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-[#F2F4F6] dark:border-[#1E2A3A]">
            <p className="text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">
              아직 계정이 없으신가요?{' '}
              <Link href="/sign-up" className="text-[#3182F6] font-medium hover:underline">회원가입</Link>
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
