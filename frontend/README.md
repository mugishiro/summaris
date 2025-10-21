# Frontend

Next.js 14 App Router をベースに、ISR で要約クラスタを配信する想定のフロントエンドです。Amplify Hosting / CloudFront へのデプロイをターゲットにしています。

## セットアップ

```bash
cd frontend
npm install
npm run dev
```

`npm run lint` で Next.js + ESLint のチェック、`npm run format` で Prettier 検証が実行できます。

### ISR 再検証エンドポイント

- `app/api/revalidate/route.ts` に ISR 再検証用 API を実装しています。
- 環境変数 `REVALIDATE_SECRET`（任意）を設定すると、`x-revalidate-token` ヘッダー / `secret` クエリ / JSON フィールドでのトークン照合が必須になります。
- リクエスト例:

```bash
curl -X POST "https://your-host/api/revalidate" \
  -H "Content-Type: application/json" \
  -H "x-revalidate-token: $REVALIDATE_SECRET" \
  -d '{"paths": ["/"], "tags": ["clusters"]}'
```

### API クライアント

- クラスタ一覧／詳細は `lib/api-client.ts` を経由して取得します。`NEWS_API_BASE_URL` を設定すると REST API (API Gateway 等) に自動で切り替わり、未設定時は DynamoDB 直読み → モックデータの順でフォールバックします。
- 環境変数:
  - `NEWS_API_BASE_URL` または `NEXT_PUBLIC_API_BASE_URL`: 公開 API のベース URL（例: `https://api.example.com/api/v1/`）。
  - `NEWS_API_CLUSTERS_ENDPOINT` (任意): クラスタ一覧/詳細の基底パス。デフォルト `/clusters`（詳細は `/clusters/{id}` を参照します）。
  - `REVALIDATE_SECRET` (任意): 再検証エンドポイントの共有シークレット。
  - Terraform スタックを適用して生成される `content_api_url` 出力値を指定すると、API Gateway + Lambda 経由で本番データに接続できます。

## ディレクトリ構成

- `app/`: App Router (ISR) 用ルーティング。`page.tsx` ではキーワード / 期間 / 出典フィルタをまとめたタイトル一覧と詳細パネルを提供します。詳細要約はタイトル選択時にオンデマンド生成され、完了後にモーダルへ表示されます。
- `components/`: UI コンポーネント（タイトルディレクトリ、出典表示など）。
- `lib/`: API クライアント、型定義、設定。
- `public/`: 静的アセット（ロゴなどを配置する場合は利用規約に従う）。
- `tests/`: Jest / Playwright テスト（フェーズ 5 以降に追加予定）。

アクセシビリティ要件や要約表示仕様は `docs/SPECIFICATION.md` を参照してください。
