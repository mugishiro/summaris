'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  detailStatusPriority,
  normaliseClusterSummary,
  toTimestamp,
} from '../lib/cluster-helpers';
import type { ClusterSummary } from '../lib/types';

const DETAIL_POLL_INTERVAL_MS = 1500;
const DETAIL_POLL_TIMEOUT_MS = 60_000;
const DETAIL_POLL_MAX_ATTEMPTS = 40;
const LOCAL_FAILURE_TTL_MS = 10 * 60 * 1000;

type LocalFailureRecord = {
  reason: string;
  timestamp: number;
};

function getLocalFailure(clusterId: string): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(`detail_failure:${clusterId}`);
    if (!raw) {
      return null;
    }
    const record = JSON.parse(raw) as LocalFailureRecord;
    if (!record || typeof record.timestamp !== 'number' || typeof record.reason !== 'string') {
      window.localStorage.removeItem(`detail_failure:${clusterId}`);
      return null;
    }
    if (Date.now() - record.timestamp > LOCAL_FAILURE_TTL_MS) {
      window.localStorage.removeItem(`detail_failure:${clusterId}`);
      return null;
    }
    return record.reason;
  } catch (error) {
    console.warn('Failed to read local failure cache', error);
    return null;
  }
}

function rememberLocalFailure(clusterId: string, reason: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  const payload: LocalFailureRecord = {
    reason,
    timestamp: Date.now(),
  };
  window.localStorage.setItem(`detail_failure:${clusterId}`, JSON.stringify(payload));
}

function clearLocalFailure(clusterId: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(`detail_failure:${clusterId}`);
}

export type ClusterDetailState = {
  summary: string;
  detailStatus: ClusterSummary['detailStatus'];
  hasSummary: boolean;
  isReady: boolean;
  isError: boolean;
  isGenerating: boolean;
  failureReason?: string;
};

export function useClusterDetails(clusters: ClusterSummary[]) {
  const normalisedClusters = useMemo(
    () => clusters.map((cluster) => normaliseClusterSummary(cluster)),
    [clusters]
  );

  const [clusterDetails, setClusterDetails] = useState<Record<string, ClusterSummary>>({});
  const clusterDetailsRef = useRef(clusterDetails);
  const pollersRef = useRef<Map<string, number>>(new Map());
  const pollMetadataRef = useRef<Map<string, { attempts: number; startedAt: number }>>(new Map());

  useEffect(() => {
    clusterDetailsRef.current = clusterDetails;
  }, [clusterDetails]);

  const stopPolling = useCallback((clusterId: string) => {
    const timeoutId = pollersRef.current.get(clusterId);
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
      pollersRef.current.delete(clusterId);
    }
    pollMetadataRef.current.delete(clusterId);
  }, []);

  useEffect(() => {
    const pollers = pollersRef.current;
    return () => {
      pollers.forEach((timeoutId) => window.clearTimeout(timeoutId));
      pollers.clear();
    };
  }, []);

  const handleDetailResponse = useCallback(
    async (clusterId: string, response: Response): Promise<boolean> => {
      if (response.status === 404) {
        stopPolling(clusterId);
        return true;
      }

      if (!response.ok) {
        return false;
      }

      const textBody = await response.text();
      if (!textBody.trim()) {
        return false;
      }

      try {
        const payload = JSON.parse(textBody) as {
          cluster?: ClusterSummary | null;
          data?: ClusterSummary | null;
        } & Partial<ClusterSummary>;

        let candidate = payload?.cluster ?? payload?.data ?? null;
        if (!candidate && payload && typeof payload.id === 'string') {
          candidate = payload as ClusterSummary;
        }

        if (candidate) {
          const normalised = normaliseClusterSummary(candidate);
          setClusterDetails((prev) => ({
            ...prev,
            [clusterId]: normalised,
          }));
          const status = (normalised.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
          if (status === 'ready' || status === 'stale' || status === 'failed') {
            stopPolling(clusterId);
            if (status === 'ready' || status === 'stale') {
              clearLocalFailure(clusterId);
            } else if (status === 'failed') {
              const reason = normalised.detailFailureReason ?? 'failed';
              rememberLocalFailure(clusterId, reason);
            }
            return true;
          }
        }
      } catch (error) {
        console.error('Failed to parse cluster detail payload', error);
      }

      return false;
    },
    [stopPolling]
  );

  const startPolling = useCallback(
    (clusterId: string) => {
      if (pollersRef.current.has(clusterId)) {
        return;
      }

      pollMetadataRef.current.set(clusterId, { attempts: 0, startedAt: Date.now() });

      const poll = async () => {
        try {
          const response = await fetch(`/api/cluster/${clusterId}/detail`, {
            method: 'GET',
            cache: 'no-store',
          });

          if (response.status === 404) {
            stopPolling(clusterId);
            return;
          }

          const done = await handleDetailResponse(clusterId, response);
          if (done) {
            return;
          }
        } catch (error) {
          console.error('Failed to poll cluster detail', error);
        }

        const meta = pollMetadataRef.current.get(clusterId);
        if (!pollersRef.current.has(clusterId) || !meta) {
          return;
        }

        meta.attempts += 1;
        const exceededAttempts = meta.attempts >= DETAIL_POLL_MAX_ATTEMPTS;
        const exceededTimeout = Date.now() - meta.startedAt >= DETAIL_POLL_TIMEOUT_MS;
        if (exceededAttempts || exceededTimeout) {
          stopPolling(clusterId);
          const base = clusterDetailsRef.current[clusterId];
          if (base) {
            const failureReason = base.detailFailureReason ?? 'timeout';
            rememberLocalFailure(clusterId, failureReason);
            setClusterDetails((prev) => ({
              ...prev,
              [clusterId]: normaliseClusterSummary({
                ...base,
                detailStatus: 'failed',
                detailFailureReason: failureReason,
              }),
            }));
          }
          return;
        }

        const timeoutId = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
        pollersRef.current.set(clusterId, timeoutId);
      };

      const timeoutId = window.setTimeout(poll, 0);
      pollersRef.current.set(clusterId, timeoutId);
    },
    [handleDetailResponse, stopPolling]
  );

  useEffect(() => {
    normalisedClusters.forEach((cluster) => {
      const resolved = clusterDetailsRef.current[cluster.id] ?? cluster;
      const status = (resolved.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
      const localFailureReason = getLocalFailure(cluster.id);
      if (localFailureReason) {
        stopPolling(cluster.id);
        setClusterDetails((prev) => ({
          ...prev,
          [cluster.id]: normaliseClusterSummary({
            ...resolved,
            detailStatus: 'failed',
            detailFailureReason: localFailureReason,
          }),
        }));
        return;
      }
      if (status === 'pending') {
        startPolling(cluster.id);
      }
    });
  }, [normalisedClusters, startPolling]);

  useEffect(() => {
    setClusterDetails((prev) => {
      let changed = false;
      const next = { ...prev };
      normalisedClusters.forEach((cluster) => {
        const existing = next[cluster.id];
        if (!existing) {
          next[cluster.id] = cluster;
          changed = true;
          return;
        }
        const existingPriority = detailStatusPriority(existing.detailStatus);
        const incomingPriority = detailStatusPriority(cluster.detailStatus);
        const existingUpdatedAt = toTimestamp(existing.updatedAt);
        const incomingUpdatedAt = toTimestamp(cluster.updatedAt);
        if (incomingPriority > existingPriority || incomingUpdatedAt > existingUpdatedAt) {
          next[cluster.id] = cluster;
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [normalisedClusters]);

  const ensureDetailSummary = useCallback(
    async (cluster: ClusterSummary) => {
      const baseCluster =
        clusterDetailsRef.current[cluster.id] ?? normaliseClusterSummary(cluster);
      const currentStatus = (baseCluster.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
      const isComplete = currentStatus === 'ready' || currentStatus === 'stale';
      if (pollersRef.current.has(cluster.id) || currentStatus === 'pending' || isComplete) {
        return;
      }

      setClusterDetails((prev) => ({
        ...prev,
        [cluster.id]: normaliseClusterSummary({
          ...baseCluster,
          detailStatus: 'pending',
          summaryLong: '',
          detailFailureReason: undefined,
        }),
      }));
      clearLocalFailure(cluster.id);

      try {
        const ensureResponse = await fetch(`/api/cluster/${cluster.id}/detail`, {
          method: 'POST',
          cache: 'no-store',
        });

        if (!ensureResponse.ok && ensureResponse.status !== 202) {
          throw new Error(`Failed to initiate summary generation (${ensureResponse.status})`);
        }

        const completed = await handleDetailResponse(cluster.id, ensureResponse);
        if (!completed) {
          startPolling(cluster.id);
        }
      } catch (error) {
        console.error('Failed to initiate summary generation', error);
        stopPolling(cluster.id);
        const failureReason = 'request_failed';
        rememberLocalFailure(cluster.id, failureReason);
        setClusterDetails((prev) => ({
          ...prev,
          [cluster.id]: normaliseClusterSummary({
            ...baseCluster,
            detailStatus: 'failed',
            summaryLong: baseCluster.summaryLong,
            detailFailureReason: failureReason,
          }),
        }));
      }
    },
    [handleDetailResponse, startPolling, stopPolling]
  );

  const getDetailState = useCallback(
    (cluster: ClusterSummary): ClusterDetailState => {
      const resolved = clusterDetails[cluster.id] ?? cluster;
      const summary = (resolved.summaryLong ?? '').trim();
      const detailStatus = (resolved.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
      const isReadyStatus = detailStatus === 'ready' || detailStatus === 'stale';
      const hasSummary = summary.length > 0 && isReadyStatus;
      const isError = detailStatus === 'failed';
      const isGenerating = pollersRef.current.has(cluster.id) || detailStatus === 'pending';
      const failureReason = resolved.detailFailureReason?.trim() || undefined;

      return {
        summary,
        detailStatus,
        hasSummary,
        isReady: hasSummary,
        isError,
        isGenerating,
        failureReason,
      };
    },
    [clusterDetails]
  );

  return {
    normalisedClusters,
    clusterDetails,
    ensureDetailSummary,
    getDetailState,
  };
}
