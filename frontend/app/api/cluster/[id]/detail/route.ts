import { NextRequest, NextResponse } from 'next/server';

import { fetchClusterByIdFresh } from '../../../../../lib/api-client';

const API_BASE_URL =
  process.env.NEWS_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

async function callContentApi(path: string, init: RequestInit) {
  if (!API_BASE_URL) {
    return NextResponse.json({ message: 'Content API is not configured.' }, { status: 500 });
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

  return NextResponse.json(body, { status: response.status });
}

export async function POST(_request: NextRequest, { params }: { params: { id: string } }) {
  const path = `/clusters/${encodeURIComponent(params.id)}/summaries`;
  return callContentApi(path, { method: 'POST' });
}

export async function GET(_request: NextRequest, { params }: { params: { id: string } }) {
  const cluster = await fetchClusterByIdFresh(params.id);
  if (!cluster) {
    return NextResponse.json({ message: 'Cluster not found' }, { status: 404 });
  }
  return NextResponse.json(cluster, { status: 200 });
}
