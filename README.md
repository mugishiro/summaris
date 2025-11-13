# News Summary Pipeline

海外ニュースを拾い上げて日本語の要約を返すための、個人制作サーバレス・パイプラインです。  
ここでは仕組み・運用・ルールをすべて 1 ファイルで紹介します。ざっと読めば全体像がつかめますし、細部もリンクなしでたどれるようにしました。

---

## 1. 何をしているのか

- EventBridge Scheduler がソース（BBC / NHK / Al Jazeera など）の RSS を定期チェックし、Collector Lambda へ渡す
- Collector が新着記事を見つけると SQS Raw Queue に投入
- Queue Worker Lambda が 4 ステップ（collector → preprocessor → summarizer → postprocess）を同一コンテナ内で順番に実行
- Postprocess が DynamoDB `news-summary` テーブルへ upsert、必要なら監査用に S3 へ元記事テキストを置く
- API Gateway + Lambda (Content API) が要約を配信し、フロントの Next.js (ISR) が一覧とポップアップ詳細を表示
- ユーザーが「詳細要約」をリクエストすると `POST /clusters/{id}/summaries` が Queue Worker を再起動し、`detail_status` が `ready` になるまでポーリング

用途は「個人の学習・ポートフォリオ公開」なので、RSS 各社の規約と著作権ルールを守りつつ、本文は保存せず要約と出典リンクだけを提供しています。

---

## 2. アーキテクチャ一枚絵

```
ブラウザ
   │
   ▼
CloudFront / Amplify (Next.js ISR) ──> API Gateway ──> Lambda (Content API)
                                             │
                                             └── DynamoDB (summary/source tables)

EventBridge Scheduler ─> Collector Lambda ─> SQS Raw Queue ─> Queue Worker Lambda
                                                                │
                                                                ├─ collector
                                                                ├─ preprocessor
                                                                ├─ summarizer (Cloudflare AI → Bedrock fallback)
                                                                └─ postprocess (DynamoDB + S3 raw archive)
```

- **Summarizer** は Cloudflare Workers AI (`@cf/meta/llama-3-8b-instruct`) が第一候補。失敗したときだけ Bedrock Claude に切り替えます。Secrets Manager にプロンプトと API トークンを保存しておき、Lambda の環境変数から参照します。
- **Postprocess** は日本語タイトル補完、翻訳、detail TTL 更新、raw アーカイブなど “保存前の最終処理” を担います。
- **Content API** は `GET /clusters`, `GET /clusters/{id}`, `POST /clusters/{id}/summaries` を持ち、detail 状態 (`partial/pending/ready/stale/failed`) とタイムスタンプを返します。
- **Frontend** は 1 ページ構成。ポップアップで detail 要約を表示し、`pending` のあいだ 1.5 秒周期でポーリング。ローカルで “失敗” を 10 分間キャッシュし、ユーザーが再実行ボタンを押すまで自動ポーリングを止めます。

---

## 3. パイプラインの流れ（ざっくり）

1. **収集** – EventBridge Scheduler が 15〜60 分おきに Collector を起動し、RSS の `ETag/Last-Modified` で差分チェック。新規があれば Raw Queue へ。
2. **前処理** – Preprocessor が本文抽出・正規化、SimHash で重複除去、トピック推定、URL 正規化。
3. **要約** – Summarizer が Secrets Manager のプロンプトを使って LLM を叩き、500 文字以内の日本語要約 JSON を取得。Cloudflare → Bedrock → 翻訳（Cloudflare もしくは Amazon Translate）という順にフォールバック。
4. **保存** – Postprocess が DynamoDB に upsert。detail 要約はオンデマンド生成の時だけ `detail_status=ready` にし、通常は `partial`。
5. **配信** – Content API が DynamoDB から最新クラスタを返し、Next.js が ISR で静的化。detail ボタンは `POST /clusters/{id}/summaries` を叩いて Queue Worker を非同期起動し、`ready` になるまで `GET /clusters/{id}` をポーリングします。

`detail_status` の遷移は `partial → pending → ready/stale`（失敗時は `failed`）。`pending` が 15 分超過すると Content API が `failed` に倒し、ユーザー操作で再生成できます。

---

## 4. ストレージと TTL

| リソース | 役割 | TTL / 補足 |
| --- | --- | --- |
| DynamoDB `<env>-news-summary` | 要約 & メタデータ (`pk=SOURCE#...`, `sk=ITEM#...`) | `expires_at`：48h、`detail_expires_at`：12h |
| DynamoDB `<env>-news-source-status` | Collector の状態管理 | 次回ポーリングまでの間隔を記録 |
| S3 `<env>-news-raw-*` | 元記事テキストの監査用スナップショット | ライフサイクルで 30〜90 日で削除 |
| S3 `<env>-news-ddb-export-*` | DynamoDB Export (バックアップ) | `aws dynamodb export-table-to-point-in-time` の出力先 |

---

## 5. API & フロントの挙動

- `GET /clusters?limit=` … 最新クラスタ一覧
- `GET /clusters/{id}` … 単一クラスタ＋ detail 情報 (`detailStatus`, `detailReadyAt`, `detailFailureReason` など)
- `POST /clusters/{id}/summaries` … detail 生成開始（Queue Worker を非同期 invoke）

フロント（Next.js App Router）は ISR でリストを描画し、モーダルで detail を表示。  
detail 失敗時は localStorage に原因を保存して「要約失敗」のままにし、再実行ボタンで cache を削除 → `pending` に戻す仕組みです。

---

## 6. デプロイ & 運用メモ

1. 変更 → `pytest backend/tests` と `npm run test -- tests/schemas.test.ts`
2. 各 Lambda の `build/<name>` に `handler.py` などをコピーし、`zip -qr ../../dist/<name>.zip .`
3. `cp dist/<name>.zip infra/terraform/dist/<name>.zip`
4. Terraform を dev → prod の順で実行
   ```bash
   terraform -chdir=infra/terraform/stacks/pipeline workspace select dev
   terraform -chdir=infra/terraform/stacks/pipeline plan -var-file=dev.tfvars
   terraform -chdir=infra/terraform/stacks/pipeline apply -var-file=dev.tfvars -auto-approve
   # prod も同様
   ```
5. `curl https://<stage>.execute-api.../clusters` で疎通確認し、CloudWatch Logs (`/aws/lambda/<env>-news-queue-worker` など) をチェック

監視は CloudWatch アラーム（summarizer/postprocess errors、pipeline failures）と SNS (`<env>-news-alerts`) に集約。  
detail が `pending` のまま動かない場合は DynamoDB の `detail_status` と Queue Worker ログを追い、必要なら `detail_status=failed` に更新して再実行します。

---

## 7. コーディング方針とポリシー

- **命名**: AWS リソースは `<env>-news-<service>`、DynamoDB キーは `SOURCE#` / `ITEM#`、detail ステータスは `partial/pending/ready/stale/failed` のみ。
- **Python / Lambda**: 型ヒント必須。`backend/tests/test_lambda_packages.py` で ZIP に `shared/cloudflare.py` が入っているか検証。
- **TypeScript / Frontend**: App Router + Server Component。detail ステータスは `hooks/use-cluster-details.ts` 1 か所で扱い、UI 状態と同期。
- **コミット**: 小さめの単位でまとめ、`git push` 前にローカルテスト + `terraform plan`。メッセージは “動詞 + 目的語” で書きます。
- **ポリシー**: RSS から取得した本文は保存しない／出典リンク必須／LLM 出力は 500 文字以内で事実のみ。Cloudflare/B edrock の利用規約、各 RSS の Terms を守ること。

---

## 8. ディレクトリ早見表

| パス | 内容 |
| --- | --- |
| `backend/lambdas/*` | 各 Lambda ハンドラー |
| `backend/tests/` | PyTest ベースのテスト群 |
| `build/` | Lambda を zip 化する前のワークスペース |
| `dist/` | 完成した zip（Terraform が参照） |
| `infra/terraform/` | IaC。ワークスペース `dev` / `prod` |
| `frontend/` | Next.js アプリ（`amplify.yml` でビルド） |

---

## 9. ライセンスと利用範囲

個人の学習・ポートフォリオ用途を想定しています。商用利用は想定しておらず、RSS 配信元や LLM プロバイダの利用規約に従ってください。  
問題やバグを見つけたら Issue/PR 大歓迎です。
