import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  // prettier와 충돌하는 ESLint 규칙을 모두 끔 (반드시 마지막에 위치)
  ...compat.extends('prettier'),
  {
    rules: {
      // 미사용 변수는 _ 접두사로 허용
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // any 타입 경고 (에러 아님 — 개발 초기 유연성 확보)
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
];

export default eslintConfig;
