# Backend

Lambda 関数や Step Functions のステートマシンなど、サーバレス要約パイプラインのコードを配置します。

想定ディレクトリ構成:
- `lambdas/collector/`: RSS 取得・整形までを担当する Lambda。
- `lambdas/summarizer/`: Bedrock への要約リクエストと結果整形を行う Lambda。
- `lambdas/postprocess/`: 差分抽出や DynamoDB への保存処理を担当する Lambda。
- `shared/`: 共通ライブラリ、型定義、設定ファイル。
- `tests/`: PyTest などの単体テストコード。

詳細は `docs/SPECIFICATION.md` と `docs/DEVELOPMENT_PLAN.md` のフェーズ 1, 2 を参照してください。
