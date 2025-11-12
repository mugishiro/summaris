import Link from 'next/link';
import { notFound } from 'next/navigation';

import { fetchClusterById } from '../../../lib/api-client';
import { SourceCredits } from '../../../components/source-credits';

export const dynamic = 'force-dynamic';
export const dynamicParams = true;

function formatIso(dateIso: string) {
  return new Date(dateIso).toLocaleString('ja-JP', { hour12: false });
}

export default async function ClusterDetailPage({ params }: { params: { id: string } }) {
  const cluster = await fetchClusterById(params.id);

  if (!cluster) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-6">
      <nav className="text-sm text-slate-400">
        <Link href="/" className="underline hover:text-sky-300">
          ← 一覧へ戻る
        </Link>
      </nav>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-slate-100">{cluster.headline}</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
          <p>最終更新: {formatIso(cluster.updatedAt)}</p>
        </div>
      </header>
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm leading-relaxed text-slate-300">
        <h2 className="mb-2 text-lg font-semibold text-slate-100">要約</h2>
        <p>{cluster.summaryLong && cluster.summaryLong.trim().length > 0 ? cluster.summaryLong : '要約はまだ生成されていません。'}</p>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-300">
        <h3 className="mb-3 text-base font-semibold text-slate-100">参照ソース</h3>
        <SourceCredits sources={cluster.sources} primaryHeadline={cluster.headline} />
      </section>
    </div>
  );
}
