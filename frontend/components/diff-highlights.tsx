'use client';

import type { ClusterSummary } from '../lib/types';

type Props = {
  points: ClusterSummary['diffPoints'];
};

export function DiffHighlights({ points }: Props) {
  if (!points.length) {
    return (
      <p className="text-sm text-slate-400">
        差分情報はまだ生成されていません。必要に応じて再生成を実行してください。
      </p>
    );
  }

  return (
    <ul className="space-y-2 text-sm leading-relaxed text-slate-300">
      {points.map((point, index) => (
        <li
          key={`${point}-${index}`}
          className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3"
        >
          <span aria-hidden className="mt-0.5 text-sky-300">
            •
          </span>
          <span className="flex-1">{point}</span>
        </li>
      ))}
    </ul>
  );
}
