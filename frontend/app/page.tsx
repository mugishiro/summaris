import { ClusterDirectory } from '../components/cluster-directory';
import { fetchClusterSummaries } from '../lib/api-client';

export const dynamic = 'force-dynamic';
export const fetchCache = 'force-no-store';

export default async function HomePage() {
  const clusters = await fetchClusterSummaries();

  return <ClusterDirectory clusters={clusters} />;
}
