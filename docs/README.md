# プロジェクト概要

海外ニュースを自動収集し、日本語の要約を Web で提供するサーバレス・パイプラインです。  
運用中の仕様をこの 1 ファイルで参照できるようにしました（詳細な手順や運用ノウハウは `docs/OPERATIONS.md`、ポリシー類は `docs/POLICY.md` を参照してください）。

## 1. サービスサマリ

| 項目 | 内容 |
| --- | --- |
| 目的 | 海外主要メディアの記事を収集し、LLM と翻訳で日本語要約を生成して配信する |
| 利用チャネル | Next.js（ISR）+ CloudFront / Amplify Hosting |
| 対象ソース | BBC, NHK, Al Jazeera, Times of India, DW, EL PAÍS, AllAfrica など（RSS） |
| 想定利用者 | 国際情勢を追う個人／法人の情報収集担当（非商用・研究利用を想定） |
| 主要制約 | 記事本文の保存禁止、出典リンク必須、RSS 利用規約遵守、AI 要約の品質監視 |

## 2. アーキテクチャ

```
ユーザー ──> CloudFront / Amplify (Next.js) ──> API Gateway ──> Lambda (Content API)
                                                           │
                                                           └─> DynamoDB (summary/source tables)

EventBridge Scheduler ─> Collector Lambda ─> SQS Raw Queue ─> Queue Worker Lambda
                                                           │
                                                           └─> collector → preprocessor → summarizer → postprocess
                                                                 (Bedrock / Cloudflare AI / DynamoDB 連携)

Postprocess Lambda ─> DynamoDB への upsert + S3 raw archive
```

- **Collector**: ソースごとの Scheduler から起動され RSS を取得。差分がない場合は `should_fetch=false` で終了。
- **Queue Worker**: SQS イベントやオンデマンド detail リクエストから起動され、`collector → preprocessor → summarizer → postprocess` を直列で呼び出す。
- **Summarizer**: 既定では Cloudflare Workers AI (`@cf/meta/llama-3-8b-instruct`) を利用し、失敗時のみ Bedrock Claude へフォールバック。Secrets Manager からプロンプトと API トークンを読み込む。
- **Postprocess**: 要約を DynamoDB (`{ pk: SOURCE#..., sk: ITEM#... }`) に書き込み、必要に応じて元記事テキストを暗号化 S3 バケットに保存。要約が生成できなかった場合は `SUMMARY_FALLBACK_MESSAGE` をセット。
- **Content API**: `GET /clusters`, `GET /clusters/{id}`, `POST /clusters/{id}/summaries` を提供。詳細要約はオンデマンドで `queue-worker` を非同期起動し `detail_status`（partial/pending/ready/stale/failed）を管理する。
- **Frontend**: クラスタ一覧→モーダル詳細の 1 ページ構成。detail ボタン押下で API を叩き、`detail_status` が `ready` になるまで 1.5 秒間隔でポーリング。失敗した場合は再実行ボタンのみ表示。

## 3. データフロー詳細

1. **収集**: EventBridge Scheduler がソース別の Cron（15～60 分）で Collector を起動。`ETag/Last-Modified` で差分チェック。新規記事は RawQueue へ投入。
2. **前処理**: Preprocessor が `article_body` を抽出・正規化、SimHash による重複除去、トピック推定、URL 正規化（UTM/パラメータ削除）を実施。
3. **要約**: Summarizer が Secrets Manager のプロンプトを用いて LLM を呼び、500 文字以内の日本語要約 JSON を受け取る。Cloudflare → Bedrock → 翻訳の順でフォールバックする設計。
4. **保存/後処理**: Postprocess が翻訳・headline 生成・detail TTL 付与・S3 への raw 保存を行って DynamoDB に upsert。`detail_status` は detail 呼び出し時のみ `ready` になる。
5. **配信**: Content API が DynamoDB から件数制限付きでクラスタを返す。Next.js は ISR で静的生成しつつ、detail ポップアップはクライアント側で API を叩く。
6. **オンデマンド detail**: `POST /clusters/{id}/summaries` → DynamoDB の `detail_status` を `pending` に更新 → Queue Worker（Lambda Invoke Event）で collector から再実行 → `detail_status` が `ready` になったら API が `detailReadyAt` を返す。

## 4. ストレージ & TTL

| コンポーネント | 用途 | 主要フィールド / TTL |
| --- | --- | --- |
| DynamoDB `<env>-news-summary` | 要約＋メタデータ | `pk=SOURCE#`, `sk=ITEM#`, `summaries.summary_long`, `detail_status`, `detail_ready_at`, `detail_expires_at`（12 時間） |
| DynamoDB `<env>-news-source-status` | Collector のポーリング状態 | `pk=SOURCE#...`, `sk=status` |
| S3 `<env>-news-raw-*` | 監査用に元記事テキストを保存 | `raw/{source}/{item}.txt`、ライフサイクルで自動削除可 |
| S3 `<env>-news-ddb-export-*` | バックアップ用 | DynamoDB エクスポートを集約 |

## 5. API ハイライト

| メソッド | パス | 説明 |
| --- | --- | --- |
| `GET /clusters?limit=` | クラスタ一覧（最新順） |
| `GET /clusters/{id}` | 単一クラスタ＋ detail 情報 (`detailStatus`, timestamps, sources) |
| `POST /clusters/{id}/summaries` | detail 要約をオンデマンド生成。レスポンスは `status: started/pending/refreshing` と `workerRequestId` |

`detailStatus` の遷移:
```
partial → (ユーザーが detail 生成) → pending → ready/stale
pending → timeout 15 分 → failed
failed → ユーザーが再生成 → pending
```

## 6. フロントエンド挙動

- Next.js 13 App Router + ISR。`/` でクラスタ一覧、クライアント側状態管理でポップアップ detail。
- API が失敗した場合は DynamoDB スキャンのフォールバックを行わず、UI に明示的なエラーを表示する。
- Detail 失敗は localStorage に保持（10 分）。ページを更新しても自動ポーリングは再開されず、再実行ボタンを押したタイミングで local cache を破棄して `pending` に戻す。
- 主要なスタイル/コピーのガイド: 日本語タイトルを優先し、出典ラベルと「参照記事」セクションでリンクを明示する。

## 7. 監視ポイント

- CloudWatch Logs (Lambda 各種) とメトリクス（Errors、Duration）。特に Summarizer/Queue Worker/Postprocess の `Errors` にアラーム (`sns:dev-news-alerts`, `sns:prod-news-alerts`) を設定済み。
- DynamoDB テーブルの容量・TTL、SQS DLQ の未処理件数、Step Functions manual runs。
- detail 生成失敗 (`detail_status=failed`) が一定回数を超えた場合は Slack/メールで通知。

## 8. 将来の拡張ポイント

- OpenSearch / CloudWatch Logs Insights へのインデックス移行で全文検索・トレンド分析に対応。
- RSS 以外の API ソース追加、または有料ニュース API との連携。
- UI カスタマイズ: トピック別表示、ユーザーの既読管理、Slack/メール配信など。

---

- 運用・デプロイ方法 → `docs/OPERATIONS.md`
- コーディング規約／命名／ライセンス順守 → `docs/POLICY.md`
