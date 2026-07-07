'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { authApi } from '@/lib/authApi';

export default function SignInPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await authApi.signIn(loginId, password);
      login(res.access_token, res.user);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-1 flex flex-col items-center justify-center p-4 transition-colors">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="text-primary font-bold text-2xl tracking-tight">ClickMe</Link>
          <p className="mt-2 text-sm text-ink-tertiary">다시 만나서 반가워요</p>
        </div>

        <div className="bg-card rounded-2xl border border-line p-8 shadow-sm transition-colors">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">아이디</label>
              <input
                type="text" value={loginId} onChange={(e) => setLoginId(e.target.value)} required
                placeholder="아이디를 입력하세요"
                className="w-full px-4 py-3 rounded-xl border border-line text-sm text-ink placeholder:text-ink-muted dark:placeholder-[#4B5563] focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors bg-surface-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">비밀번호</label>
              <input
                type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                placeholder="••••••••"
                className="w-full px-4 py-3 rounded-xl border border-line text-sm text-ink placeholder:text-ink-muted dark:placeholder-[#4B5563] focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors bg-surface-2"
              />
            </div>

            {error && (
              <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full py-3 bg-primary text-primary-foreground font-medium rounded-xl hover:bg-primary-hover disabled:opacity-60 transition-colors mt-2"
            >
              {loading ? '로그인 중...' : '로그인'}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-line">
            <p className="text-center text-xs text-ink-tertiary">
              계정은 관리자가 직접 발급합니다. 필요하면 담당자에게 문의하세요.
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-ink-muted mt-6">
          <Link href="/" className="hover:text-ink-tertiary transition-colors">← 메인으로 돌아가기</Link>
        </p>
      </div>
    </div>
  );
}
