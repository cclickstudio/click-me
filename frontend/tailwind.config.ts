import type { Config } from 'tailwindcss';

// RGB 채널 토큰을 rgb(var(--x) / <alpha-value>)로 감싸 alpha 모디파이어 지원.
const withOpacity = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'sans-serif'],
      },
      colors: {
        // shadcn 코어
        border: withOpacity('--border'),
        input: withOpacity('--input'),
        ring: withOpacity('--ring'),
        background: withOpacity('--background'),
        foreground: withOpacity('--foreground'),
        primary: {
          DEFAULT: withOpacity('--primary'),
          hover: withOpacity('--primary-hover'),
          subtle: withOpacity('--primary-subtle'),
          foreground: withOpacity('--primary-foreground'),
        },
        accent: {
          DEFAULT: withOpacity('--accent'),
          foreground: withOpacity('--accent-foreground'),
        },
        // 브랜드 포인트 바이올렛(화면당 1개) — shadcn accent(뉴트럴)와 분리
        point: {
          DEFAULT: withOpacity('--point'),
          hover: withOpacity('--point-hover'),
          subtle: withOpacity('--point-subtle'),
          foreground: withOpacity('--point-foreground'),
        },
        secondary: {
          DEFAULT: withOpacity('--secondary'),
          foreground: withOpacity('--secondary-foreground'),
        },
        muted: {
          DEFAULT: withOpacity('--muted'),
          foreground: withOpacity('--muted-foreground'),
        },
        destructive: {
          DEFAULT: withOpacity('--destructive'),
          foreground: withOpacity('--destructive-foreground'),
        },
        popover: {
          DEFAULT: withOpacity('--popover'),
          foreground: withOpacity('--popover-foreground'),
        },
        card: {
          DEFAULT: withOpacity('--card'),
          foreground: withOpacity('--card-foreground'),
        },
        // 확장 — surface 위계
        surface: {
          0: withOpacity('--surface-0'),
          1: withOpacity('--surface-1'),
          2: withOpacity('--surface-2'),
          3: withOpacity('--surface-3'),
        },
        // 확장 — text 위계(ink 스케일, text-primary 충돌 회피)
        ink: {
          DEFAULT: withOpacity('--text-primary'),
          secondary: withOpacity('--text-secondary'),
          tertiary: withOpacity('--text-tertiary'),
          muted: withOpacity('--text-muted'),
          disabled: withOpacity('--text-disabled'),
        },
        // 확장 — border 위계(line 스케일)
        line: {
          DEFAULT: withOpacity('--border'),
          strong: withOpacity('--border-strong'),
          stronger: withOpacity('--border-stronger'),
        },
        // 확장 — semantic 4종
        success: {
          DEFAULT: withOpacity('--success'),
          foreground: withOpacity('--success-foreground'),
          subtle: withOpacity('--success-subtle'),
          border: withOpacity('--success-border'),
        },
        warning: {
          DEFAULT: withOpacity('--warning'),
          foreground: withOpacity('--warning-foreground'),
          subtle: withOpacity('--warning-subtle'),
          border: withOpacity('--warning-border'),
        },
        danger: {
          DEFAULT: withOpacity('--danger'),
          foreground: withOpacity('--danger-foreground'),
          subtle: withOpacity('--danger-subtle'),
          border: withOpacity('--danger-border'),
        },
        info: {
          DEFAULT: withOpacity('--info'),
          foreground: withOpacity('--info-foreground'),
          subtle: withOpacity('--info-subtle'),
          border: withOpacity('--info-border'),
        },
      },
      borderRadius: {
        sm: 'calc(var(--radius) - 4px)',
        md: 'calc(var(--radius) - 2px)',
        lg: 'var(--radius)',
        xl: 'calc(var(--radius) + 4px)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};

export default config;
