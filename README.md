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

## 有料プランの記事（注文から公開まで）

有料プラン（スポット・月額）の記事は、次の流れで作る。無料の毎朝記事（`daily-article.yml`）とは別に、手動で動かす。

1. フォーム（Formspree）の申し込みメールを確認し、Stripe の支払いリンクを送って、入金を確認する。
2. GitHub で issue を作る（テンプレート「有料プランの注文」）。お名前・プラン・公開希望日・メモ・参考URL を貼り、入金確認にチェックする。**メールアドレスや電話番号は書かない**（このリポジトリは公開）。
3. Actions の「Paid article」を実行し、注文 issue の番号を入れる。
4. AI が記事（`sponsored: true`）とサムネを作り、プルリクエストを出す。注文 issue にも、PR のリンクがコメントされる。掲載基準に当たる場合は、記事を作らず、理由が issue にコメントされる。
5. 内容を確認してマージする。公開日時は、公開希望日の 7:00 JST。マージ後、その日時以降の自動ビルド（毎朝 7:05）で公開される。
6. PR 本文の X 投稿文を、公開後に手動で投稿する。

- 記事の指示文は `prompts/article.txt`（土台）と `prompts/sponsored.txt`（有料の追加分）。
- 月額プランの回数（月2回まで）は、注文 issue を見て、手動で数える。
- 公開後3日以内の修正（1回無料）は、現状は手動で対応する（記事を直接直して、PR にする）。
