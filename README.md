# News Summary Pipeline

海外ニュースを機械的に集めて、日本語の「ざっと読める」要約に変えるための個人プロジェクトです。AWS のサーバレス部品（EventBridge → Lambda → SQS → DynamoDB）と Next.js のフロントを繋いで動かしています。

## ざっくり仕組み
- EventBridge が各 RSS（BBC/NHK/Al Jazeera など）を定期チェック → Collector Lambda が新着を `raw-queue` へ
- Queue Worker Lambda が `collector → preprocessor → summarizer → postprocess` を直列実行  
  - Summarizer は Cloudflare Workers AI を優先、失敗したら Bedrock Claude にフォールバック  
  - Postprocess が要約や翻訳、`detail_status` 更新、S3 への監査用保存を担当
- DynamoDB `news-summary` に保存 → Content API (Lambda) が `GET /clusters` / `GET /clusters/{id}` / `POST /clusters/{id}/summaries` を提供
- Next.js (ISR) で一覧を出し、モーダルで「要約を生成」→ detail が `ready` になるまで 1.5 秒ごとにポーリング（失敗はローカルに 10 分キャッシュ）

## ストレージとモニタリング
| リソース | 用途 |
| --- | --- |
| DynamoDB `<env>-news-summary` | `pk=SOURCE#`, `sk=ITEM#` で要約・detail 状態を保存 (`detail_expires_at`=12h) |
| DynamoDB `<env>-news-source-status` | Collector の進捗管理 |
| S3 `<env>-news-raw-*` | 元記事テキストの短期保管（ライフサイクル 30〜90 日） |
| CloudWatch | Lambda Errors、SQS DLQ、Step Functions（アラームは `<env>-news-alerts` に通知） |

## デプロイの流れ
1. `pytest backend/tests` と `npm run test -- tests/schemas.test.ts`
2. `build/<lambda>` を更新 → `zip -qr ../../dist/<lambda>.zip .` → `cp dist/... infra/terraform/dist/...`
3. Terraform で dev → prod の順に `plan` / `apply`
4. `curl https://<stage>.execute-api.../clusters` と CloudWatch Logs で動作確認

## ディレクトリ
| パス | 役割 |
| --- | --- |
| `backend/lambdas/*` / `backend/tests` | Lambda 本体と PyTest |
| `build/` / `dist/` | Lambda パッケージの作業場と成果物 |
| `infra/terraform` / `infra/stepfunctions` | IaC と Step Functions 定義 |
| `frontend/` | Next.js 14 App Router（Amplify でビルド） |

## 開発メモ
- Lambda の共有処理は `backend/lambdas/shared/*` に寄せ、ZIP へ必ず同梱する
- フロントは App Router + ISR。`app/api/revalidate` にシークレットを仕込めば手動キャッシュ更新も可
- 命名や扱いはシンプルに：`<env>-news-<service>`、detail ステータスは `partial/pending/ready/stale/failed` のみ、記事本文は保存しない

## ライセンス
学習・ポートフォリオ目的で作っています。RSS 配信元と LLM ベンダーの規約を守り、商用利用は避けてください。バグやアイデアがあれば Issue/PR をどうぞ。
