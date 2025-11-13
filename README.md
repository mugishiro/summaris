# World News Digest
世界の主要ニュースサイトから定期的に記事を集めて一覧表示します。気になる記事は「要約を生成」ボタンで日本語の要約をリクエストでき、生成済みの要約はそのまま再利用できます。

## コレクション対象
- BBC World News
- NHK News
- Al Jazeera English
- Deutsche Welle (DW)
- EL PAÍS
- The Straits Times
- The Times of India
- AllAfrica Latest

## 仕組み
- EventBridge がソースごとに Collector Lambda を起動し、RSS の差分をチェック
- 新着記事は Dispatcher Lambda 経由で SQS Raw Queue に投入
- Queue Worker Lambda が `collector → preprocessor → summarizer → postprocess` を順次呼び出し、DynamoDB `news-summary` に保存
  - Summarizer は Cloudflare Workers AI を優先し、失敗時は Bedrock Claude にフォールバック
  - Postprocess は翻訳・detail 状態更新・S3 への原文アーカイブを担当
- Content API Lambda が `GET /articles` / `GET /articles/{id}` / `POST /articles/{id}/summaries` を提供
- Next.js (ISR) が一覧とモーダルを描画し、detail が `ready` になるまで 1.5 秒おきにポーリング（失敗は 10 分間キャッシュ）

## ディレクトリ
| パス | 役割 |
| --- | --- |
| `backend/` | Lambda 群と PyTest |
| `infra/terraform/` | Terraform (dev/prod Workspace) |
| `frontend/` | Next.js 14 App Router（Amplify でホスト） |

## ライセンス
学習・ポートフォリオ目的で作っています。RSS 配信元と LLM ベンダーの規約を守り、商用利用は避けてください。バグやアイデアがあれば Issue/PR からお願いいたします。
