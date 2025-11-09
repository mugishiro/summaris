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
      className="inline-flex items-center gap-3 rounded-full border border-slate-300 bg-white/80 px-3 py-1 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:bg-slate-900"
      aria-label={`テーマを${nextTheme === 'dark' ? '夜モード' : '昼モード'}に切り替える`}
    >
      <span
        aria-hidden="true"
        className={`relative inline-flex h-6 w-12 items-center rounded-full transition ${
          theme === 'dark' ? 'bg-slate-800' : 'bg-amber-300'
        }`}
      >
        <span
          className={`absolute inline-block h-5 w-5 rounded-full bg-white shadow transition ${
            theme === 'dark' ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </span>
      <span className="hidden text-xs text-slate-500 dark:text-slate-400 sm:inline">
        {theme === 'dark' ? '夜' : '昼'}
      </span>
    </button>
  );
}
