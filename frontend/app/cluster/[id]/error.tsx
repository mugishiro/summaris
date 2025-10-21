'use client';

import Link from 'next/link';
import { useEffect } from 'react';

type RouteErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ClusterDetailError({ error, reset }: RouteErrorProps) {
  useEffect(() => {
    console.error('Cluster detail route error', error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
      <div className="space-y-3">
        <p className="text-xs uppercase tracking-widest text-slate-500">Cluster Detail</p>
        <h2 className="text-2xl font-semibold text-slate-100">クラスタの読み込みに失敗しました</h2>
        <p className="max-w-lg text-sm text-slate-400">
          ネットワークや API の応答に問題が発生しました。再試行するか、トップページに戻って別のクラスタを選択してください。
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-600 hover:text-sky-200"
        >
          再読み込み
        </button>
        <Link
          href="/"
          className="rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-600 hover:text-sky-200"
        >
          トップへ戻る
        </Link>
      </div>
    </div>
  );
}
