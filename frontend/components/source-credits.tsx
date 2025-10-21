'use client';

import { useId } from 'react';

import type { ClusterSummary } from '../lib/types';

type Props = {
  sources: ClusterSummary['sources'];
  heading?: string;
  primaryHeadline?: string;
};

export function SourceCredits({ sources, heading = '出典', primaryHeadline }: Props) {
  const headingId = useId();

  if (!sources.length) {
    return null;
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2 text-xs text-slate-400">
      <h4 id={headingId} className="font-medium text-slate-200">
        {heading}
      </h4>
      <ul className="space-y-1">
        {sources.map((source, index) => {
          const href = source.articleUrl?.trim() || source.url?.trim();
          const primaryLabelCandidates: Array<string | undefined> = [];
          if (index === 0) {
            primaryLabelCandidates.push(source.articleTitle?.trim());
            primaryLabelCandidates.push(primaryHeadline?.trim());
          } else {
            primaryLabelCandidates.push(source.articleTitle?.trim());
          }
          primaryLabelCandidates.push(source.name?.trim());
          const displayLabel = primaryLabelCandidates.find((value) => value && value.length > 0) || href;
          return (
            <li key={source.id} className="leading-relaxed">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-200">{source.name}</span>
              </div>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block max-w-full truncate text-sky-300 underline-offset-2 hover:underline"
                >
                  {displayLabel}
                </a>
              ) : (
                <span className="mt-1 block text-slate-500">URL 未設定</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
