'use client';

import { useMemo } from 'react';

import { useTheme } from './theme-provider';

export function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = useMemo(() => (theme === 'dark' ? 'light' : 'dark'), [theme]);
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-300 bg-white/80 text-lg shadow-sm transition hover:border-slate-400 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:bg-slate-900"
      aria-label={`テーマを${nextTheme === 'dark' ? 'ダークモード' : 'ライトモード'}に切り替える`}
    >
      <span aria-hidden="true" role="img">
        {theme === 'dark' ? '🌙' : '☀️'}
      </span>
    </button>
  );
}
