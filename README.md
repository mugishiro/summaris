# World News Digest
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
