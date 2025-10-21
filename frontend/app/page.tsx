import { fetchClusterSummaries } from '../lib/api-client';
import nextDynamic from 'next/dynamic';

export const dynamic = 'force-dynamic';

const ClusterDirectory = nextDynamic(
  () =>
    import('../components/cluster-directory').then(
      (module) => module.ClusterDirectory
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-10 text-slate-400">
        ローディング中...
      </div>
    ),
  }
);

export default async function HomePage() {
  const clusters = await fetchClusterSummaries();

  return <ClusterDirectory clusters={clusters} />;
}
