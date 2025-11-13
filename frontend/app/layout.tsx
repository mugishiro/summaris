import type { Metadata } from 'next';
import { ReactNode } from 'react';

import { ThemeProvider } from '../components/theme-provider';
import { ThemeToggleButton } from '../components/theme-toggle';
import './globals.css';

export const metadata: Metadata = {
  title: 'World News Digest',
  description: '世界の主要ニュースサイトから最新記事を集め、ワンクリックで要約できるダッシュボード',
  icons: {
    icon: '/icon.svg',
    shortcut: '/icon.svg'
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja" className="overflow-x-hidden">
      <body className="min-h-screen overflow-x-hidden bg-slate-50 text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
        <ThemeProvider>
          <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-6 py-10 sm:px-10">
            <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 dark:border-slate-800">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="space-y-2">
                  <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                    World News Digest
                  </h1>
                  <p className="max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-400 sm:whitespace-nowrap">
                    世界の主要ニュースサイトから最新記事を集めています。気になる記事は「要約を生成」ボタンで日本語の要約をリクエストできます。
                  </p>
                </div>
                <div className="sm:self-start">
                  <ThemeToggleButton />
                </div>
              </div>
            </header>
            <main className="flex-1">{children}</main>
            <footer className="border-t border-slate-200 pt-6 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400" />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
