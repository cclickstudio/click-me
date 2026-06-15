import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import ThemeProvider from '@/components/ThemeProvider';
import { AuthProvider } from '@/components/AuthProvider';
import { ProjectProvider } from '@/components/ProjectContext';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ClickMe',
  description: '광고를 집행하기 전에, AI 가상 소비자에게 먼저 테스트하세요.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        {/* 다크 모드 깜빡임 방지: 하이드레이션 전에 클래스 적용 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;if(t==='dark'||(t===null&&d))document.documentElement.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body className={inter.className}>
        <ThemeProvider><AuthProvider><ProjectProvider>{children}</ProjectProvider></AuthProvider></ThemeProvider>
      </body>
    </html>
  );
}
