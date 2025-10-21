# Infra

AWS リソースをコード化した Terraform / SAM 設定を管理します。開発計画フェーズ 0.2 および 2.x のタスクに対応する領域です。

推奨ディレクトリ:
- `terraform/`:
  - `environments/`: `dev.tfvars`（単一環境運用）。
  - `modules/`: `stepfunctions`, `lambda`, `dynamodb`, `sqs` などの共通モジュール。
  - `stacks/`: dev 用のルートモジュール。
- `sam/` や `cdk/` を採用する場合は別サブディレクトリを用意。

Terraform バックエンドや命名規則は `docs/DEVELOPMENT_PLAN.md` のフェーズ 0.2、`docs/SPECIFICATION.md` の 10 章を参照して整備してください。
