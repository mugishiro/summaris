import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-start justify-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-8">
      <h2 className="text-xl font-semibold text-slate-100">ページが見つかりません</h2>
      <p className="text-sm text-slate-400">指定した記事またはページは存在しないか、削除されました。</p>
      <Link href="/" className="text-sky-300 underline">
        トップへ戻る
      </Link>
    </div>
  );
}
