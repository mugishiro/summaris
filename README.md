# World News Digest
This web service periodically collects articles from major global news sites and displays them. For each article, you can trigger an on-demand summary, which is generated in Japanese.

## Sources (Polling Interval)
- BBC World News (every hour)
- NHK News (every 2 hours)
- Al Jazeera English (every 2 hours)
- Deutsche Welle (every 3 hours)
- EL PAIS (every 3 hours)
- The Straits Times (every 3 hours)
- The Times of India (every 2 hours)
- AllAfrica Latest (every 2 hours)

## Architecture
### backend
```
EventBridge Scheduler
        │
        ▼
Collector Lambda
        │
        ▼
Dispatcher Lambda
        │
        ▼
SQS Raw Queue
        │ (event source)
        ▼
Queue Worker Lambda
        │
        ├─ invokes Collector Lambda (refetch article body)
        │
        ├─ invokes Preprocessor Lambda (noise removal)
        │
        ├─ invokes Summarizer Lambda (LLM summary)
        │
        └─ invokes Postprocess Lambda (store + translate)
        │
        ▼
┌───────────────┴────────────────┐
▼                               ▼
DynamoDB summary table     S3 raw archive
        │
        ▼
Content API Lambda
        │
        ▼
API Gateway HTTP API
        │
        ▼
Next.js Frontend
```
- EventBridge triggers the Collector Lambda per source, compares RSS diffs, and decides whether the item is new
- Dispatcher Lambda enqueues new items to the SQS Raw Queue
- Queue Worker Lambda runs collector → preprocessor → summarizer → postprocess sequentially and writes to DynamoDB/S3
  - collector: fetches article body + metadata and returns a structured payload
  - preprocessor: removes unnecessary parts to reduce noise
  - summarizer: generates Japanese summaries with Cloudflare Workers AI
  - postprocess: stores summaries and translated titles in DynamoDB/S3
- API Gateway HTTP API (backed by Content API Lambda) provides list/detail/summary endpoints
### frontend
- Next.js 14 (Amplify Hosting) renders list and detail pages
- When the summary button is clicked, it requests summary generation via Content API Lambda → Queue Worker Lambda, then polls status every 1.5 seconds until the summarizer completes

## Directories
| Path | Role |
| --- | --- |
| `backend/` | Lambda functions |
| `frontend/` | Next.js 14 App Router |
| `infra/terraform/` | Terraform stack |

## License
For learning and portfolio use. Please follow the RSS provider and LLM vendor terms, and avoid commercial use. Issues/PRs are welcome.

---

# World News Digest (日本語)
世界の主要ニュースサイトから定期的に記事を収集し、表示する Webサービスです。各記事において要約生成ボタンを押すと日本語で要約を生成します。

## コレクション対象 (ポーリング間隔)
- BBC World News（1時間ごと）
- NHK News（2時間ごと）
- Al Jazeera English（2時間ごと）
- Deutsche Welle （3時間ごと）
- EL PAÍS（3時間ごと）
- The Straits Times（3時間ごと）
- The Times of India（2時間ごと）
- AllAfrica Latest（2時間ごと）

## 仕組み
### backend
```
EventBridge Scheduler
        │
        ▼
Collector Lambda
        │
        ▼
Dispatcher Lambda
        │
        ▼
SQS Raw Queue
        │ (event source)
        ▼
Queue Worker Lambda
        │
        ├─ invokes Collector Lambda（本文取得の再実行）
        │
        ├─ invokes Preprocessor Lambda（ノイズ除去）
        │
        ├─ invokes Summarizer Lambda（LLM要約）
        │
        └─ invokes Postprocess Lambda（保存・翻訳）
        │
        ▼
┌───────────────┴────────────────┐
▼                               ▼
DynamoDB summary table     S3 raw archive
        │
        ▼
Content API Lambda
        │
        ▼
API Gateway HTTP API
        │
        ▼
Next.js Frontend
```
- EventBridge がソース別に Collector Lambda を起動し RSS の差分を見て新着記事かどうか判定
- Dispatcher Lambda が新着記事を SQS Raw Queue へ投入
- SQS Raw Queue から Queue Worker Lambda が collector → preprocessor → summarizer → postprocess を直列実行し、DynamoDB/S3 に書き込む
  - collector: 記事 URL から本文・メタデータを取得し、構造化したペイロードを返す
  - preprocessor: 本文の不要部分を除去し、要約に不要なノイズを軽減
  - summarizer: Cloudflare Workers AIで日本語要約を生成
  - postprocess: 要約や翻訳済みタイトルを DynamoDB/S3 に保存
- API Gateway HTTP API（裏側は Content API Lambda）で一覧・詳細・要約生成エンドポイントを提供
### frontend
- Next.js 14（Amplify Hosting）が一覧・詳細画面を表示
- 要約ボタンを押すと Content API Lambda 経由で Queue Worker Lambda に要約生成を依頼し、summarizer Lambda が完了するまで 1.5 秒間隔で状態を取得

## ディレクトリ
| パス | 役割 |
| --- | --- |
| `backend/` | Lambda 群 |
| `frontend/` | Next.js 14 App Router |
| `infra/terraform/` | Terraform スタック |

## ライセンス
学習・ポートフォリオ目的です。RSS 配信元や LLM ベンダーの規約を順守し、商用利用は控えてください。改善点があれば Issue/PR で連絡いただけると助かります。
