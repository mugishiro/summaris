# ポリシー & リファレンス

## 1. コーディング / コミット規約

- **コミットメッセージ**: `feat:`, `fix:`, `chore:` など動詞ベースで書き、1 行目で内容を要約。本文は必須ではないが、デプロイ必須タスクや Terraform 変更時は追記。
- **ブランチ運用**: `main` がデプロイ対象。作業は `feature/<topic>` ブランチで行い、PR 作成時にテスト済みであることを示す。
- **Python**: 型ヒント必須、`pytest` でのユニットテストを更新。Lambda での依存は `backend/lambdas/shared/*` に集約し、ZIP には `shared` ディレクトリを含める。
- **TypeScript/React**: `use client` とサーバーコンポーネントの切り分け徹底。UI 状態は `hooks/use-cluster-details.ts` を通じて制御し、detail 状態の整合性を守る。

## 2. 命名 & 環境ルール

| 項目 | ルール |
| --- | --- |
| AWS リソース | `<env>-news-<service>`（例: `dev-news-summary`, `prod-news-queue-worker`） |
| Lambda 環境変数 | `UPPER_SNAKE_CASE`（例: `SUMMARY_TABLE_NAME`, `ALERT_TOPIC_ARN`） |
| DynamoDB PK/SK | `pk = "SOURCE#<id>"`, `sk = "ITEM#<uuid>"` |
| detail ステータス | `partial`（未生成）→ `pending` → `ready` / `stale` / `failed`。`stale` は TTL 超過を意味し再生成を促す。 |
| Terraform ワークスペース | `dev` / `prod` 固定。 |

## 3. RSS / 著作権ポリシー

- 記事本文は保存せず、メタデータ＋要約のみを永続化。
- 出典リンク（`sources[].articleUrl`）を必須表示し、引用は 1～2 行に留める。
- RSS 利用条件（BBC, NHK, Al Jazeera など）は四半期ごとに確認し、規約変更時は Collector でリトライ制限や User-Agent を調整。
- 商用利用は不可。ポートフォリオとして公開する場合も出典クレジットと免責文を表示する。

## 4. プロンプト / LLM 利用

- Secrets Manager で保持する JSON 形式:
  ```json
  {
    "system_prompt": "...",
    "user_template": "記事: {article_body}\n{guidance}"
  }
  ```
- Guardrail: 500 文字以内の日本語要約／JSON のみ出力／ソースにない情報の追加禁止。
- Cloudflare Workers AI を優先（無料枠活用）。失敗時に Bedrock Claude へ切り替え。いずれも API トークン・リージョンを Lambda 環境変数で指定。

## 5. 観測・命名

- CloudWatch Log Group: `/aws/lambda/<env>-news-<function>`、API Gateway ログは `/aws/apigateway/<env>-news-content`。
- メトリクス名: `<env>-news-<service>-errors`, `pipeline-failures` など環境プレフィックス付き。
- SNS: `<env>-news-alerts`（メール購読を登録しておく）。

## 6. セキュリティ & データ保持

- 秘密情報は Secrets Manager / SSM Parameter Store に保存し、IAM ロールで最小権限付与。
- DynamoDB の TTL (`expires_at`) で要約データを 2～3 日でローテーション。S3 raw アーカイブは 30～90 日で自動削除。
- CloudFront では ACM 証明書を適用し HTTPS を強制。Amplify への Basic 認証は不要。

## 7. ドキュメント運用

過去に分散していた文書（アーキテクチャ図、デプロイ手順、ライセンスまとめ等）は本ファイルと `docs/README.md` / `docs/OPERATIONS.md` に統合しました。  
追加情報が必要な場合はこれら 3 ファイルを更新してください。
