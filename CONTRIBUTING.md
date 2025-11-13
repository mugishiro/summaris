# Contributing

このプロジェクトは個人開発が中心ですが、将来的なコラボレーションを想定して最低限のルールをまとめています。

1. **チケット化**: 変更の背景・完了条件を Issue で共有してください。
2. **ブランチ運用**: `feature/<topic>` や `fix/<topic>` の枝で作業し、小さなコミットに分割します。
3. **検証**: 変更内容に応じて `pytest backend/tests`、`npm run test -- tests/schemas.test.ts`、`terraform plan` などを実行し、結果を PR に添付します。
4. **ドキュメント**: 仕様・運用・ポリシーに影響がある場合は `docs/README.md` / `docs/OPERATIONS.md` / `docs/POLICY.md` を更新してください。

スタイルや命名規則、RSS/LLM の扱いは `docs/POLICY.md` に集約しています。迷った場合はそちらを参照してください。
