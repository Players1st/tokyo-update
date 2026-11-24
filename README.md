# tokyo-update

東京23区在住者向けローカルWebメディア（Hugo）。全体の設計は [HANDOFF.md](HANDOFF.md)、作業ルールは [CLAUDE.md](CLAUDE.md) を参照。

## ローカル開発（Docker のみ。Hugo / Go のインストール不要）

```sh
docker compose up -d        # http://localhost:1313/ で確認（ファイル保存で自動リロード）
docker compose logs -f      # ログ
docker compose down         # 停止
docker compose run --rm build   # 本番ビルドの確認（public/ に出力）
```

Hugo のバージョンは `compose.yaml` の `HUGO_VERSION`（現在 v0.170.1）。`.github/workflows/deploy.yml` の `HUGO_VERSION` と必ず揃えること。

## 公開

`main` にマージすると、GitHub Actions（`.github/workflows/deploy.yml`）が Hugo をビルドして GitHub Pages に公開する。プルリクエストではビルド確認のみ行う。下書き（`draft: true`）は公開されない。

### 公開日時を指定する（未来の日時の記事）
記事の `date` を未来の日時にしておくと、その日時までは公開されない（Hugo は未来の日時の記事をビルドしない）。先にマージしておけば、毎朝 JST 7:05 の自動ビルド（`deploy.yml` の `schedule`）で、公開日時を過ぎた記事が公開される。

- 朝7:00に公開したい記事は、`date` を `YYYY-MM-DDT07:00:00+09:00` にする（公開は 7:05 ごろ）。
- 自動ビルドが抜けたときは、GitHub の Actions で「Build and deploy」を手動実行（Run workflow）する。
- 日時はすべて日本時間（`+09:00`）。

## 記事のチェック

```sh
python3 scripts/validate_post.py                 # draft: false の全記事（標準ライブラリのみ、Python 3.9 以上）
python3 scripts/validate_post.py content/posts/<スラッグ>   # 指定した記事だけ
python3 scripts/validate_post.py --help
```

エラーがあれば終了コード 1。フロントマター、`ward` / `categories` の許可値、`og_title`、サムネ（1200×630）、本文に「要確認」が残っていないか、などを確認する。

## サムネ画像の生成

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # 初回のみ
set -a; source .env.local; set +a    # GEMINI_API_KEY（.env.local は git に入れない）と GEMINI_IMAGE_MODEL を読み込む
.venv/bin/python scripts/generate_thumbnail.py samples/thumbnails/<スラッグ>.yaml --dry-run   # API を呼ばずに確認
.venv/bin/python scripts/generate_thumbnail.py samples/thumbnails/<スラッグ>.yaml             # 生成（1200×630 で記事フォルダに保存）
```

`GEMINI_IMAGE_MODEL` は GitHub の Variables、`GEMINI_API_KEY` は Secrets から読む（コードには書かない）。
