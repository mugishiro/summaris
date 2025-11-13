'use client';

import { useEffect } from 'react';

type Failure = {
  source?: string;
  message?: string;
};

type ErrorComponentProps = {
  error: Error & {
    digest?: string;
    failures?: Failure[];
  };
  reset: () => void;
};

export default function GlobalError({ error, reset }: ErrorComponentProps) {
  useEffect(() => {
    console.error('Unhandled application error', error);
  }, [error]);

  const isDataError = error.name === 'ClusterDataError';
  const maybeFailures = (error as { failures?: Failure[] }).failures;
  const failures = Array.isArray(maybeFailures) ? maybeFailures : [];

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
      <div className="space-y-3">
        <p className="text-xs uppercase tracking-widest text-slate-500">Error</p>
        <h2 className="text-2xl font-semibold text-slate-100">
          {isDataError ? '記事データの取得に失敗しました' : 'アプリケーションでエラーが発生しました'}
        </h2>
        <p className="max-w-lg text-sm text-slate-400">
          {isDataError
            ? 'データソースへの接続に問題が発生しました。設定を確認するか、後でもう一度お試しください。'
            : '予期せぬエラーが発生しました。操作を再試行するか、詳細はログをご確認ください。'}
        </p>
      </div>
      {failures.length > 0 && (
        <div className="w-full max-w-xl rounded-xl border border-slate-800 bg-slate-900/60 p-5 text-left text-sm text-slate-300">
          <h3 className="mb-3 text-base font-semibold text-slate-100">失敗したデータソース</h3>
          <ul className="space-y-2 text-xs text-slate-400">
            {failures.map((failure, index) => (
              <li key={`${failure.source ?? 'unknown'}-${index}`}>
                <span className="font-medium text-slate-200">{failure.source ?? 'unknown'}:</span>{' '}
                {failure.message ?? '原因不明のエラーが発生しました。'}
              </li>
            ))}
          </ul>
        </div>
      )}
      <button
        type="button"
        onClick={() => reset()}
        className="rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-600 hover:text-sky-200"
      >
        再試行
      </button>
    </div>
  );
}
