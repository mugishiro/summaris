import { revalidateTag } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

import { fetchClusterByIdFresh } from '../../../../../lib/api-client';
import { CACHE_TAG } from '../../../../../lib/cached-clusters';

const API_BASE_URL =
  process.env.NEWS_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

async function callContentApi(path: string, init: RequestInit) {
  if (!API_BASE_URL) {
    return { status: 500, body: { message: 'Content API is not configured.' } };
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(init.headers ?? {}),
    },
  });

  const text = await response.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: text };
    }
  }

  return { status: response.status, body };
}

export async function POST(_request: NextRequest, { params }: { params: { id: string } }) {
  const path = `/clusters/${encodeURIComponent(params.id)}/summaries`;
  const result = await callContentApi(path, { method: 'POST' });
  if (result.status < 400) {
    revalidateTag(CACHE_TAG);
  }
  return NextResponse.json(result.body, { status: result.status });
}

export async function GET(_request: NextRequest, { params }: { params: { id: string } }) {
  const cluster = await fetchClusterByIdFresh(params.id);
  if (!cluster) {
    return NextResponse.json({ message: 'Cluster not found' }, { status: 404 });
  }
  const hasSummary =
    typeof cluster.summaryLong === 'string' && cluster.summaryLong.trim().length > 0;
  if (
    hasSummary &&
    (cluster.detailStatus === 'ready' || cluster.detailStatus === 'stale')
  ) {
    revalidateTag(CACHE_TAG);
  }
  return NextResponse.json(cluster, { status: 200 });
}
