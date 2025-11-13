# News Summary Pipeline

海外ニュースを自動収集し、日本語要約を配信する AWS サーバレス構成のリポジトリです。  
技術仕様・運用・ポリシーは下記 3 ファイルに統合しました。

- `docs/README.md` … アーキテクチャ概要・データフロー・API・フロント挙動
- `docs/OPERATIONS.md` … デプロイ／Terraform 手順、監視、Runbook
- `docs/POLICY.md` … 命名規則、コーディング方針、RSS／LLM 利用ポリシー

## ハイライト
- **構成**: EventBridge Scheduler → Collector → SQS Raw Queue → Queue Worker（collector→preprocessor→summarizer→postprocess）→ DynamoDB / S3。配信は Next.js (ISR) + Amplify/CloudFront + API Gateway + Lambda。
- **LLM**: Cloudflare Workers AI を優先し、失敗時は Bedrock Claude へフォールバック。Secrets Manager でプロンプトと API トークンを管理。
- **要約オンデマンド**: `POST /clusters/{id}/summaries` で detail を再生成し、`detail_status` と TTL を DynamoDB で管理。フロントはステータスに応じて自動ポーリング／失敗表示を切り替える。
- **用途**: 非商用・ポートフォリオ目的。RSS 利用規約を尊重し記事本文は保存せず、要約と参照リンクのみを提供。

## ディレクトリ構成（抜粋）

| パス | 説明 |
| --- | --- |
| `backend/lambdas/*` | Lambda ハンドラー（collector / dispatcher / preprocessor / summarizer / postprocess / content_api / queue_worker） |
| `build/` | Lambda バンドル用の展開済みディレクトリ（zip 化前） |
| `dist/` | Lambda の zip パッケージ。`infra/terraform/dist/*.zip` にコピーして Terraform から参照 |
| `infra/terraform` | パイプライン一式の IaC。ワークスペース: `dev`, `prod` |
| `frontend/` | Next.js (App Router)。Amplify から `amplify.yml` でビルド |

## デプロイ概要

1. コード変更 → `pytest backend/tests` / `npm run test -- tests/schemas.test.ts`
2. `build/<lambda>` にハンドラーを同期し `zip` → `dist/` → `infra/terraform/dist/`
3. `terraform -chdir=infra/terraform/stacks/pipeline plan/apply -var-file=<env>.tfvars`
4. `curl https://<stage>.execute-api.../clusters` で動作確認、CloudWatch Logs をチェック

詳細は `docs/OPERATIONS.md` を参照してください。

## コントリビューション / ライセンス

- コーディング規約やコミット方針は `docs/POLICY.md` を参照。
- このプロジェクトは個人学習用であり、商用利用は想定していません。RSS 配信元・LLM ベンダーの利用規約を遵守してください。
