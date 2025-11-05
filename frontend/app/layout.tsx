import type { Metadata } from 'next';
import { ReactNode } from 'react';

import { ThemeProvider } from '../components/theme-provider';
import { ThemeToggleButton } from '../components/theme-toggle';
import './globals.css';

export const metadata: Metadata = {
  title: 'News Snapshot',
  description: '要約クラスタと原文リンクを一覧できるポータルのベース UI',
  metadataBase: new URL('https://example.com')
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja" className="overflow-x-hidden">
      <body className="min-h-screen overflow-x-hidden bg-slate-50 text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
        <ThemeProvider>
          <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-6 py-10 sm:px-10">
            <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 dark:border-slate-800">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    News Snapshot
                  </p>
                  <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
                    ニュース要約ビュー
                  </h1>
                </div>
                <ThemeToggleButton />
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
