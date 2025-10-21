import { fetchClusterSummaries } from '../lib/api-client';
import { ClusterDirectory } from '../components/cluster-directory';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const clusters = await fetchClusterSummaries();

  return <ClusterDirectory clusters={clusters} />;
}
