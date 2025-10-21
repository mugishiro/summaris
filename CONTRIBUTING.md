# Contributing Guide

このプロジェクトは個人開発を前提としていますが、将来の協業を見据えて基本方針を定義しています。

## 開発フロー
1. Issue を作成し、背景・目的・完了条件を整理します。既存のフェーズ／タスク番号があれば紐づけてください。
2. 作業ブランチ (`feature/xxx`, `fix/xxx`) を作成し、小さなコミットで進めます。
3. Lint / テスト / `terraform plan` など関連チェックをローカルまたは CI で実行します。
4. Pull Request を作成し、テンプレートに沿って変更点と検証結果を記述します。

## コーディング規約
- Python: Ruff + Black 互換スタイル（PEP8 ベース、ドキュメント文字列推奨）。
- TypeScript/React: ESLint + Prettier デフォルト。アクセシビリティ修正には `@testing-library` での回帰テストを追加してください。
- Terraform: `terraform fmt` を必須化。モジュール化ルールは `docs/DEVELOPMENT_PLAN.md` フェーズ 2 を参照。

## テストと検証
- Lambda: PyTest を最低限用意し、外部依存は moto / localstack 等でモック化。
- Frontend: Jest でユニット、Playwright で E2E（主要ユーザーフロー）。
- インフラ: `terraform plan` の出力を PR に添付し、差分が最小であることを確認します。

## ドキュメント更新
- 仕様や運用に影響する変更を加えたら `docs/SPECIFICATION.md`、`docs/RELEASE_RUNBOOK.md`、`docs/DEVELOPMENT_PLAN.md` を見直してください。
- 新規スクリプトや手順は `scripts/README.md` または専用ドキュメントに追記します。

## コミットメッセージ
コミットメッセージ規約は `docs/COMMIT_CONVENTION.md` を参照してください。
