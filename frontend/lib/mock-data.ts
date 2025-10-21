import type { ClusterSummary } from './types';

const MINUTES = 60 * 1000;

const now = Date.now();

export const mockClusters: ClusterSummary[] = [
  {
    id: 'bbc-gaza-breakthrough',
    headline: 'ガザ停戦交渉で進展、主要メディアが一致して伝える',
    headlineJa: 'ガザ停戦交渉で進展、主要メディアが一致して伝える',
    summaryLong:
      'トランプ政権が仲介したガザ停戦合意について、主要各紙が報じた内容を統合した要約です。合意条件の詳細、人道支援回廊の設置状況、関係国の公式コメントが整理されており、停戦実現までの課題もあわせて記載しています。',
    createdAt: new Date(now - 45 * MINUTES).toISOString(),
    updatedAt: new Date(now - 15 * MINUTES).toISOString(),
    detailStatus: 'ready',
    importance: 'high',
    topics: ['中東', '外交', '停戦'],
    diffPoints: ['停戦条件の合意', '人道支援回廊の設置', '主要各国のコメント'],
    factCheckStatus: 'verified',
    languages: ['日本語', '英語'],
    sources: [
      {
        id: 'bbc-world',
        name: 'BBC World News',
        url: 'https://www.bbc.com/news/world'
      },
      {
        id: 'al-jazeera-english',
        name: 'Al Jazeera English',
        url: 'https://www.aljazeera.com/'
      },
      {
        id: 'dw-world',
        name: 'Deutsche Welle World',
        url: 'https://www.dw.com/en/world'
      }
    ]
  },
  {
    id: 'nhk-rice-price',
    headline: '日本のコメ価格高騰、政府の増産策と課題',
    headlineJa: '日本のコメ価格高騰、政府の増産策と課題',
    summaryLong:
      'NHK 等で報じられたコメ価格上昇の要因と政府の増産策を整理した要約です。地域別の輸送コストや中山間地支援策の課題、農家の収益改善に向けた政策提案などを包括的にまとめています。',
    createdAt: new Date(now - 90 * MINUTES).toISOString(),
    updatedAt: new Date(now - 60 * MINUTES).toISOString(),
    detailStatus: 'partial',
    importance: 'medium',
    topics: ['国内', '農業', '経済'],
    diffPoints: ['増産策の課題', '中山間地域の輸送コスト', '政府補助金の見直し案'],
    factCheckStatus: 'pending',
    languages: ['日本語'],
    sources: [
      {
        id: 'nhk-news',
        name: 'NHK News',
        url: 'https://www3.nhk.or.jp/news/'
      }
    ]
  },
  {
    id: 'tech-llm-safety',
    headline: 'LLM 安全性に関する最新レポートまとめ',
    headlineJa: 'LLM 安全性に関する最新レポートまとめ',
    summaryLong:
      '主要 AI ベンダーが発表した最新のセーフティガイドラインを比較し、専門家による評価や指摘を取りまとめた要約です。推奨されるリスク緩和策、残された課題、国際的な規制動向など、意思決定に必要な情報を広くカバーしています。',
    createdAt: new Date(now - 5 * 60 * MINUTES).toISOString(),
    updatedAt: new Date(now - 4 * 60 * MINUTES).toISOString(),
    detailStatus: 'ready',
    importance: 'low',
    topics: ['テクノロジー', 'AI'],
    diffPoints: ['セーフティガイドラインの更新', '専門家の評価ポイント', 'リスク評価指標の追加案'],
    factCheckStatus: 'failed',
    languages: ['英語'],
    sources: [
      {
        id: 'wired',
        name: 'WIRED',
        url: 'https://www.wired.com/'
      }
    ]
  }
];

export async function fetchMockClusters(): Promise<ClusterSummary[]> {
  return mockClusters;
}
