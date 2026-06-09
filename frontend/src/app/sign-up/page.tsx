import Link from 'next/link';

export default function Page() {
  return (
    <div className="min-h-screen bg-[#F9FAFB] flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="text-[#3182F6] font-bold text-2xl tracking-tight">
            ClickMe
          </Link>
          <p className="mt-2 text-sm text-[#8B95A1]">처음이라면 30초면 충분해요</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl border border-[#E5E8EB] p-8 shadow-sm">
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#4E5968] mb-1.5">
                이름
              </label>
              <input
                type="text"
                placeholder="홍길동"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] text-sm text-[#191F28] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#4E5968] mb-1.5">
                이메일
              </label>
              <input
                type="email"
                placeholder="example@email.com"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] text-sm text-[#191F28] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#4E5968] mb-1.5">
                비밀번호
              </label>
              <input
                type="password"
                placeholder="8자 이상"
                className="w-full px-4 py-3 rounded-xl border border-[#E5E8EB] text-sm text-[#191F28] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors bg-white"
              />
            </div>
            <button
              type="submit"
              className="w-full py-3 bg-[#3182F6] text-white font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors mt-2"
            >
              가입하기
            </button>
          </form>

          <p className="text-center text-xs text-[#B0B8C1] mt-4 leading-relaxed">
            가입하면 서비스 이용약관 및 개인정보처리방침에 동의하게 됩니다
          </p>

          <div className="mt-4 pt-4 border-t border-[#F2F4F6]">
            <p className="text-center text-sm text-[#8B95A1]">
              이미 계정이 있으신가요?{' '}
              <Link href="/sign-in" className="text-[#3182F6] font-medium hover:underline">
                로그인
              </Link>
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-[#B0B8C1] mt-6">
          <Link href="/" className="hover:text-[#8B95A1] transition-colors">
            ← 메인으로 돌아가기
          </Link>
        </p>
      </div>
    </div>
  );
}
