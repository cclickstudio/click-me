import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import ThemeProvider from '@/components/ThemeProvider';
import { AuthProvider } from '@/components/AuthProvider';
import { ProjectProvider } from '@/components/ProjectContext';
import { ChatControllerProvider } from '@/components/chat/ChatController';

// 로컬 NotoSansKR(self-host) — Tailwind sans(var(--font-sans))에 연결해 전역 한글 폰트로 사용.
const notoSansKR = localFont({
  src: [
    { path: './fonts/NotoSansKR-Thin.otf', weight: '100', style: 'normal' },
    { path: './fonts/NotoSansKR-Regular.otf', weight: '400', style: 'normal' },
    { path: './fonts/NotoSansKR-Medium.otf', weight: '500', style: 'normal' },
    { path: './fonts/NotoSansKR-Bold.otf', weight: '700', style: 'normal' },
    { path: './fonts/NotoSansKR-Black.otf', weight: '900', style: 'normal' },
  ],
  variable: '--font-sans',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Click Me — 광고 관리 올인원 플랫폼',
  description: '광고를 집행하기 전에, AI 가상 소비자에게 먼저 테스트하세요.',
  icons: {
    icon: '/logo/logo-mark.svg',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning className={notoSansKR.variable}>
      <head>
        {/* 다크 모드 깜빡임 방지: 하이드레이션 전에 클래스 적용 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;if(t==='dark'||(t===null&&d))document.documentElement.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body className="font-sans">
        <ThemeProvider><AuthProvider><ProjectProvider><ChatControllerProvider>{children}</ChatControllerProvider></ProjectProvider></AuthProvider></ThemeProvider>
      </body>
    </html>
  );
}
