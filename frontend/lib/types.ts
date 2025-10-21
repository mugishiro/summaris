export interface ClusterSummary {
  id: string;
  headline: string;
  headlineJa?: string;
  sources: Array<{
    id: string;
    name: string;
    url?: string;
    articleUrl?: string;
    articleTitle?: string;
    siteUrl?: string;
  }>;
  summaryLong?: string;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
  topics: string[];
  importance: 'high' | 'medium' | 'low';
  diffPoints: string[];
  factCheckStatus?: 'verified' | 'pending' | 'failed';
  languages?: string[];
  detailStatus?: 'partial' | 'pending' | 'ready' | 'stale' | 'failed';
  detailRequestedAt?: string;
  detailReadyAt?: string;
  detailExpiresAt?: string;
  detailFailedAt?: string;
  detailFailureReason?: string;
}
