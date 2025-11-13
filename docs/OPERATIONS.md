# 運用・デプロイ手引き

このドキュメントは現状の運用手順をまとめたものです。Terraform・Lambda パッケージ・監視の扱いはここを参照してください。

## 1. 環境構成

| 環境 | Terraform Workspace | AWS Account | 備考 |
| --- | --- | --- | --- |
| 開発 | `dev` | 710146154969 | Amplify (dev) / `dev-news-*` リソース |
| 本番 | `prod` | 710146154969 | CloudFront 独自ドメイン `news-summaris.com` |

ファイル `infra/terraform/stacks/pipeline/dev.tfvars` / `prod.tfvars` で差分を管理します。  
`enable_lambda_deployment = true` のため `infra/terraform/dist/*.zip` を更新すると Lambda コードが deploy されます。

## 2. パッケージ更新フロー

1. **コード変更 & テスト**
   ```bash
   pytest backend/tests
   npm run test -- tests/schemas.test.ts
   ```
2. **ビルド済みディレクトリを同期**（現状は `build/<lambda>` をバンドルに使用）
   ```bash
   cp backend/lambdas/<name>/handler.py build/<name>/handler.py
   ```
3. **Zip 作成**
   ```bash
   cd build/<name> && zip -qr ../../dist/<name>.zip .
   ```
4. **Terraform 配布物にコピー**
   ```bash
   cp dist/<name>.zip infra/terraform/dist/<name>.zip
   ```
5. **Terraform plan → apply**
   ```bash
   terraform -chdir=infra/terraform/stacks/pipeline workspace select dev
   terraform -chdir=infra/terraform/stacks/pipeline plan -var-file=dev.tfvars
   terraform -chdir=infra/terraform/stacks/pipeline apply -var-file=dev.tfvars -auto-approve

   terraform -chdir=infra/terraform/stacks/pipeline workspace select prod
   terraform -chdir=infra/terraform/stacks/pipeline plan -var-file=prod.tfvars
   terraform -chdir=infra/terraform/stacks/pipeline apply -var-file=prod.tfvars -auto-approve
   ```
6. **動作確認**
   - `curl https://<stage>.execute-api.../clusters?limit=1`
   - `curl -X POST .../clusters/{id}/summaries`
   - CloudWatch Logs (`/aws/lambda/<env>-news-queue-worker`, `/summarizer`, `/store`)

## 3. Amplify / Frontend

- Amplify のモノレポ設定（`AMPLIFY_MONOREPO_APP_ROOT=frontend`）で `main` ブランチをデプロイ。必要に応じて `NEXT_PUBLIC_NEWS_API_BASE_URL` を dev/prod API Gateway URL に合わせる。
- ISR キャッシュは Amplify の Revalidate URL (`/api/revalidate?secret=...`) 経由で更新。

## 4. Secrets & 設定

| 用途 | 場所 | 備考 |
| --- | --- | --- |
| Summarizer prompt | `dev/news-summary/dev/summarizer-prompt`, `prod/.../summarizer-prompt` | `system_prompt`, `user_template` を JSON で保存 |
| Cloudflare API Token | `dev/news/cloudflare-api-token`, `prod/...` | 翻訳・要約どちらも同じトークン |
| Bedrock モデル ID | `var.bedrock_model_id`（tfvars） | 既定 `anthropic.claude-3-5-sonnet-20240620-v1:0` |

Secrets を変更した場合は Summarizer/Postprocess Lambda を再デプロイして環境変数を反映させる。

## 5. 監視・通知

| 項目 | 内容 |
| --- | --- |
| CloudWatch Metrics | Lambda Errors/Duration、SQS VisibleMessages、StepFunctions ExecutionFailed |
| CloudWatch Logs Insights | 定義済みクエリは `docs/CLOUDWATCH_LOGS_INSIGHTS_QUERIES.md` の内容を本ファイルへ統合済み（例: summarizer エラー抽出） |
| SNS トピック | `dev-news-alerts`, `prod-news-alerts` （detail failure, Lambda alarm で使用） |
| Amplify/CloudFront | アクセスログと WAF ログを S3 へ保存し 30 日ローテーション |

主要運用フロー:
1. Summarizer/Queue Worker/Postprocess で `FunctionError` が出た場合 SNS へ通知。
2. Content API が detail 失敗 (`detail_status=failed`) を返した場合、UI がローカルキャッシュで再実行までポーリングを止める。障害調査時は DynamoDB `detail_failure_reason` と CloudWatch ログを併用。

## 6. バックアップ & リカバリ

- DynamoDB: PITR 有効。日次で `aws dynamodb export-table-to-point-in-time` を `dev-news-ddb-export-*` / `prod-...` バケットへ出力。
- S3 raw archive: 監査目的のため 30～90 日にライフサイクル削除。要約の再生成が必要なときのみ参照。
- 重大障害時は `terraform state pull` → `terraform apply` でリソース再作成可能。Secrets Manager の値は別途バージョン管理しておく。

## 7. Runbook（代表例）

### detail が `pending` から進まない
1. Content API ログで `_start_detail_generation` が成功しているか確認。
2. Queue Worker ログで対象 item の `Executing summarizer step` 以降を追跡。
3. Summarizer が ImportError の場合は ZIP に `shared/*` が含まれているかを `backend/tests/test_lambda_packages.py` で確認し再デプロイ。
4. DynamoDB レコードを確認し、必要なら `detail_status` を手動で `failed` に更新して再実行を促す。

### Summarizer が Cloudflare/B edrock エラー
1. CloudWatch Logs で `CloudflareIntegrationError` または Bedrock のスロットリングコードを確認。
2. Secrets Manager のトークン有効期限と `SUMMARIZER_PROVIDER` 設定を確認。
3. 翻訳/要約 API が利用不可の場合は `ENABLE_SUMMARY_TRANSLATION=false` で一時的に回避可能。

### Collector の失敗
1. DLQ (`<env>-news-raw-queue-dlq`) を CloudWatch で確認し、必要なメッセージを `aws sqs receive-message` で取得して原因を調査。
2. RSS 側の仕様変更が疑われる場合は `scripts/rss_header_check.py`、`scripts/url_normalize.py` で再検証。

## 8. チェックリスト（抜粋）

- Lambda コードを更新したら **必ず** `dist/*.zip` → `infra/terraform/dist/*.zip` をコピーし直す。
- Terraform は dev → prod の順で `plan` と `apply` を実行し、ログを保存。
- デプロイ後に `curl` で API を叩き、CloudWatch Logs に新規ビルドの `START RequestId` が出現しているか確認。
- Amplify のビルド後にブラウザで detail 生成→失敗→再試行の動作確認をする。
