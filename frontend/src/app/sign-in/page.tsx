import Link from 'next/link';

export default function Page() {
  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex flex-col items-center justify-center p-4 transition-colors">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="text-[#3182F6] font-bold text-2xl tracking-tight">
            ClickMe
          </Link>
          <p className="mt-2 text-sm text-[#8B95A1] dark:text-[#6B7280]">다시 만나서 반가워요</p>
        </div>

        {/* Card */}
        <div className="bg-white dark:bg-[#1C2333] rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-8 shadow-sm transition-colors">
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">
                이메일
              </label>
              <input
                type="email"
                placeholder="example@email.com"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white dark:bg-[#252D3D]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">
                비밀번호
              </label>
              <input
                type="password"
                placeholder="••••••••"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white dark:bg-[#252D3D]"
              />
            </div>
            <button
              type="submit"
              className="w-full py-3 bg-[#3182F6] text-white font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors mt-2"
            >
              로그인
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-[#F2F4F6] dark:border-[#1E2A3A]">
            <p className="text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">
              아직 계정이 없으신가요?{' '}
              <Link href="/sign-up" className="text-[#3182F6] font-medium hover:underline">
                회원가입
              </Link>
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-6">
          <Link href="/" className="hover:text-[#8B95A1] transition-colors">
            ← 메인으로 돌아가기
          </Link>
        </p>
      </div>
    </div>
  );
}
