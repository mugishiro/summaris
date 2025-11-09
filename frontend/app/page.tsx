import { ClusterDirectory } from '../components/cluster-directory';
import { fetchClusterSummaries } from '../lib/api-client';

export default async function HomePage() {
  const clusters = await fetchClusterSummaries();

  return <ClusterDirectory clusters={clusters} />;
}
