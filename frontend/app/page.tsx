import { ClusterDirectory } from '../components/cluster-directory';
import { getCachedClusterSummaries } from '../lib/cached-clusters';

export default async function HomePage() {
  const clusters = await getCachedClusterSummaries();

  return <ClusterDirectory clusters={clusters} />;
}
