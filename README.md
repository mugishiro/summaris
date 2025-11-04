# AWS Todo News Summary (PoC)

このリポジトリは海外ニュースを自動要約する個人プロジェクトの PoC/MVP 用コードとドキュメントを収集したものです。

## 概要
- AWS (EventBridge, Lambda, Step Functions, DynamoDB, Bedrock, Amplify) を用いたサーバレス構成。
- RSS から取得した記事のメタデータのみを保存し、LLM（Bedrock Claude）で要約と差分を生成。
- 要約・翻訳は Cloudflare Workers AI を優先し、失敗時のみ Bedrock / Amazon Translate にフォールバックする構成へ移行中。
- Web フロントエンドは Next.js (ISR) で構築予定。

## 利用ポリシー
- **非商用・ポートフォリオ目的**での利用のみを想定しています。
- RSS 配信元の利用規約を尊重し、本文の保存・再配布を行いません。
- 出典リンクとクレジット表示を徹底し、注意書きテンプレートを `docs/RSS_LICENSE_OVERVIEW.md` にまとめています。

## ドキュメント
- 仕様書: `docs/SPECIFICATION.md`
- 開発計画・タスク: `docs/DEVELOPMENT_PLAN.md`
- 要約プロンプト仕様: `docs/LLM_PROMPT_SPEC.md`
- ポートフォリオ公開ガイド: `docs/PORTFOLIO_GUIDE.md`
- RSS 利用規約まとめ: `docs/RSS_LICENSE_OVERVIEW.md`
- コミットメッセージ規約: `docs/COMMIT_CONVENTION.md`
- 環境タグ・命名規約: `docs/ENVIRONMENT_NAMING.md`
- Terraform バックエンド手順: `docs/TERRAFORM_BACKEND_SETUP.md`
- RSS ソース調査レポート: `docs/RSS_SOURCE_AUDIT.md`
- 要約パイプライン PoC 設計: `docs/PIPELINE_POC.md`
- 品質・コスト評価手順: `docs/QUALITY_COST_EVALUATION.md`
- CloudWatch Logs Insights クエリ集: `docs/CLOUDWATCH_LOGS_INSIGHTS_QUERIES.md`
- PoC 要約評価ログ: `docs/POC_FEEDBACK.md`

## Cloudflare Workers AI 設定概要
- 要約 Lambda は `SUMMARIZER_PROVIDER=cloudflare`（既定値）で Cloudflare Workers AI を呼び出し、`CLOUDFLARE_ACCOUNT_ID` と Secrets Manager 上のトークン（`CLOUDFLARE_API_TOKEN_SECRET_NAME`）を設定すれば無料枠で運用できる。失敗時は自動的に Bedrock にフォールバック。
- 見出し翻訳は Cloudflare Workers AI (`ENABLE_TITLE_TRANSLATION=true`) で `@cf/meta/m2m100-1.2b` を使用し、同じシークレットを参照して翻訳モデルを呼び出す。必要に応じて `CLOUDFLARE_TRANSLATE_MODEL_ID` や `CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS` を調整できる。
- 要約本文が英語で返ってきた場合でも `ENABLE_SUMMARY_TRANSLATION=true` を設定しておくと Cloudflare Workers AI で日本語化を試行し、成功時は DynamoDB へ保存する要約を差し替える。
- Cloudflare を未設定の場合は翻訳フォールバックが無効になり、そのままの要約が保存される点に注意する。

## ライセンス
このプロジェクトは個人学習・ポートフォリオ用途のためライセンスを設定していません。商用利用を希望する場合は必ず各 RSS 配信元と AWS の利用規約をご確認ください。
