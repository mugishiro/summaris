'use client';

import { useMemo } from 'react';

import { useTheme } from './theme-provider';

const ICONS: Record<'light' | 'dark', string> = {
  light: '🌞',
  dark: '🌙',
};

export function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = useMemo(() => (theme === 'dark' ? 'light' : 'dark'), [theme]);
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white/80 px-3 py-1 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:bg-slate-900"
      aria-label={`テーマを${nextTheme === 'dark' ? 'ダーク' : 'ライト'}に切り替える`}
    >
      <span aria-hidden="true">{ICONS[theme]}</span>
      <span className="hidden sm:inline">{theme === 'dark' ? 'ダーク' : 'ライト'}</span>
    </button>
  );
}
