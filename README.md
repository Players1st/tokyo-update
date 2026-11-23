# tokyo-update

東京23区在住者向けローカルWebメディア（Hugo）。全体の設計は [HANDOFF.md](HANDOFF.md)、作業ルールは [CLAUDE.md](CLAUDE.md) を参照。

## ローカル開発（Docker のみ。Hugo / Go のインストール不要）

```sh
docker compose up -d        # http://localhost:1313/ で確認（ファイル保存で自動リロード）
docker compose logs -f      # ログ
docker compose down         # 停止
docker compose run --rm build   # 本番ビルドの確認（public/ に出力）
```

Hugo のバージョンは `compose.yaml` の `HUGO_VERSION`（現在 v0.170.1）。GitHub Actions のバージョンと揃えること。
