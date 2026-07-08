// 라이트/다크 토글 + data-theme(14종 컬러 프리셋) 관리 프로바이더 — localStorage 영속.
'use client';

import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

// 컬러 테마 11종(neutrals 공유, primary/point만 교체) + 에디터다크 3종(전체 팔레트, 항상 다크).
export const COLOR_THEMES = [
  'blue',
  'indigo',
  'cyan',
  'emerald',
  'orange',
  'mono',
  'wine',
  'violet',
  'rose',
  'amber',
  'teal',
] as const;
export const EDITOR_THEMES = ['monokai', 'monokai-black', 'dracula'] as const;

export type ColorTheme = (typeof COLOR_THEMES)[number];
export type EditorTheme = (typeof EDITOR_THEMES)[number];
export type DataTheme = ColorTheme | EditorTheme;

export const THEME_LABELS: Record<DataTheme, string> = {
  blue: '블루',
  indigo: '인디고',
  cyan: '시안',
  emerald: '에메랄드',
  orange: '오렌지',
  mono: '모노',
  wine: '와인',
  violet: '바이올렛',
  rose: '로즈',
  amber: '앰버',
  teal: '틸',
  monokai: 'Monokai',
  'monokai-black': 'Monokai Black',
  dracula: 'Dracula',
};

export function isEditorTheme(t: DataTheme): t is EditorTheme {
  return (EDITOR_THEMES as readonly string[]).includes(t);
}

interface ThemeContextValue {
  theme: Theme;
  toggle: () => void;
  dataTheme: DataTheme;
  setDataTheme: (t: DataTheme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  toggle: () => {},
  dataTheme: 'blue',
  setDataTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('light');
  const [dataTheme, setDataThemeState] = useState<DataTheme>('blue');

  useEffect(() => {
    const storedTheme = localStorage.getItem('theme') as Theme | null;
    const storedData = localStorage.getItem('data-theme') as DataTheme | null;
    const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
    const initialTheme = storedTheme ?? preferred;
    const initialData: DataTheme = storedData ?? 'blue';

    // 에디터 테마는 항상 다크로 취급.
    const resolvedTheme: Theme = isEditorTheme(initialData) ? 'dark' : initialTheme;

    setTheme(resolvedTheme);
    setDataThemeState(initialData);
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
    document.documentElement.setAttribute('data-theme', initialData);
  }, []);

  const toggle = () => {
    setTheme(prev => {
      // 에디터 테마 중에는 라이트로 못 감(전체 팔레트가 다크). 무시.
      if (isEditorTheme(dataTheme)) return prev;
      const next: Theme = prev === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme', next);
      document.documentElement.classList.toggle('dark', next === 'dark');
      return next;
    });
  };

  const setDataTheme = (t: DataTheme) => {
    localStorage.setItem('data-theme', t);
    document.documentElement.setAttribute('data-theme', t);
    setDataThemeState(t);
    if (isEditorTheme(t)) {
      // 에디터 테마 진입 시 다크 강제(dark: 유틸 변형도 활성).
      setTheme('dark');
      document.documentElement.classList.add('dark');
    } else {
      // 컬러 테마로 돌아오면 저장된 라이트/다크 선호 복원.
      const stored = (localStorage.getItem('theme') as Theme | null) ?? theme;
      const restored: Theme = stored === 'dark' ? 'dark' : 'light';
      setTheme(restored);
      document.documentElement.classList.toggle('dark', restored === 'dark');
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, toggle, dataTheme, setDataTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
