#!/usr/bin/env python3
"""記事（ページバンドル）の機械チェック。標準ライブラリのみで動く（Python 3.9 以上）。

使い方:
  python3 scripts/validate_post.py                       # draft: false の全記事
  python3 scripts/validate_post.py --all                 # 下書きも含む全記事
  python3 scripts/validate_post.py content/posts/<スラッグ> ...   # 指定した記事のみ
  python3 scripts/validate_post.py --allow-missing-image <記事>    # 画像なしを警告扱いにする
  python3 scripts/validate_post.py --json <記事>          # 結果を JSON で出力

終了コード: エラーがあれば 1、なければ 0（警告は影響しない）。
チェック内容は HANDOFF.md 第4章ステップ4 と、Issue #16 を参照。
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "content" / "posts"

REQUIRED_KEYS = [
    "title", "date", "lastmod", "draft", "ward", "area", "categories",
    "tags", "og_title", "source_name", "source_url", "sponsored",
]
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")
SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$")
OG_TITLE_MAX = 24
THUMB_SIZE = (1200, 630)


# ---------- 読み込み ----------

def load_toml_keys(path: Path) -> set:
    """data/*.toml（`key = "value"` だけの平らなファイル）のキー一覧を返す。"""
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*(?:"([^"]+)"|([A-Za-z0-9_]+))\s*=', line)
        if m:
            keys.add(m.group(1) or m.group(2))
    return keys


def strip_comment(value: str) -> str:
    """引用符の外にある ` # コメント` を取り除く。"""
    in_quote = False
    for i, ch in enumerate(value):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip()
    return value.rstrip()


def parse_scalar(raw: str):
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith('"') or raw.startswith("["):
        try:
            return json.loads(raw)
        except ValueError:
            return raw  # 解釈できない値は文字列のまま返し、後続のチェックで落とす
    return raw


def parse_post(path: Path):
    """index.md を (フロントマター dict, 本文) に分ける。失敗時は ValueError。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("フロントマター（--- で囲まれた部分）が見つかりません")
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        km = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not km:
            raise ValueError("フロントマターの行を解釈できません: " + line[:40])
        fm[km.group(1)] = parse_scalar(strip_comment(km.group(2)))
    return fm, m.group(2)


def png_size(path: Path):
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def has_broken_bold(body: str) -> bool:
    """`**太字。**続き` のように、閉じの ** の直前が記号・直後が文字だと、Markdown で太字にならない。
    行ごとに ** を順に「開き・閉じ」と対にして、閉じ側だけを調べる。"""
    for line in body.splitlines():
        marks = [m.start() for m in re.finditer(r"\*\*", line)]
        for close in marks[1::2]:
            prev_ch = line[close - 1] if close > 0 else " "
            next_ch = line[close + 2] if close + 2 < len(line) else " "
            if unicodedata.category(prev_ch).startswith("P") and unicodedata.category(next_ch)[0] in "LN":
                return True
    return False


# ---------- チェック ----------

def validate(post_dir: Path, wards: set, categories: set, allow_missing_image: bool):
    errors, warnings = [], []
    slug = post_dir.name
    index = post_dir / "index.md"
    result = {"slug": slug, "errors": errors, "warnings": warnings, "needs_check": 0,
              "draft": None, "og_title": None, "ward": None}

    if not index.is_file():
        errors.append("index.md がありません")
        return result
    try:
        fm, body = parse_post(index)
    except ValueError as e:
        errors.append(str(e))
        return result

    result["draft"] = fm.get("draft")
    result["og_title"] = fm.get("og_title")
    result["ward"] = fm.get("ward")

    if not SLUG_RE.match(slug):
        errors.append("フォルダ名が「YYYY-MM-DD-英数字とハイフン」の形式ではありません: " + slug)

    # 必須項目
    missing = [k for k in REQUIRED_KEYS if k not in fm]
    if missing:
        errors.append("必須のフロントマター項目がありません: " + ", ".join(missing))

    # 日時
    for key in ("date", "lastmod"):
        if key in fm and not (isinstance(fm[key], str) and DATETIME_RE.match(fm[key])):
            errors.append("%s が YYYY-MM-DDTHH:MM:SS+09:00 の形式ではありません: %s" % (key, fm[key]))

    # ward / categories / tags
    if "ward" in fm and fm["ward"] not in wards:
        errors.append("ward が許可された値ではありません: %s" % fm["ward"])
    if "categories" in fm:
        cats = fm["categories"]
        if not isinstance(cats, list) or not cats:
            errors.append("categories は1つ以上の配列にしてください")
        else:
            bad = [c for c in cats if c not in categories]
            if bad:
                errors.append("categories が許可された値ではありません: " + ", ".join(map(str, bad)))
            if len(cats) != 1:
                warnings.append("categories は原則1つです（現在 %d 個）" % len(cats))
    if "tags" in fm:
        tags = fm["tags"]
        if not isinstance(tags, list) or not (3 <= len(tags) <= 5):
            warnings.append("tags は3〜5個が目安です（現在 %s）" % (len(tags) if isinstance(tags, list) else "配列でない"))

    # 型
    for key in ("draft", "sponsored"):
        if key in fm and not isinstance(fm[key], bool):
            errors.append("%s は true / false にしてください" % key)

    # 出典
    if "source_url" in fm:
        url = fm["source_url"]
        if not isinstance(url, str) or not url.strip():
            errors.append("source_url が空です")
        elif not url.startswith(("http://", "https://")):
            errors.append("source_url が http(s):// で始まっていません: %s" % url)
    if "source_name" in fm and not (isinstance(fm["source_name"], str) and fm["source_name"].strip()):
        errors.append("source_name が空です")

    # og_title
    if "og_title" in fm:
        og = fm["og_title"]
        if not isinstance(og, str) or not og.strip():
            errors.append("og_title が空です")
        else:
            if len(og) > OG_TITLE_MAX:
                errors.append("og_title が全角%d文字を超えています（%d文字）" % (OG_TITLE_MAX, len(og)))
            if "【" in og or "】" in og:
                errors.append("og_title に「【〇〇区】」を含めないでください（区名は画像側で表示します）")

    # title の注意
    title = fm.get("title", "")
    if isinstance(title, str) and "仮称" in title:
        warnings.append("title に「仮称」が含まれています（本文で補足する方針）")

    # 画像
    thumb = post_dir / (slug + ".png")
    if not thumb.is_file():
        msg = "サムネ画像 %s.png がありません" % slug
        (warnings if allow_missing_image else errors).append(msg)
    else:
        size = png_size(thumb)
        if size is None:
            errors.append("サムネ画像が PNG として読めません")
        elif size != THUMB_SIZE:
            errors.append("サムネ画像が %dx%d ではありません（%dx%d）" % (THUMB_SIZE + size))

    # 本文
    result["needs_check"] = body.count("要確認")
    if result["needs_check"]:
        warnings.append("本文に「要確認」が %d 箇所あります。確認できなかった点は本文に書かず、PR 本文で報告する方針です" % result["needs_check"])
    if "{{ARTICLE_URL}}" in body or "X投稿案" in body:
        warnings.append("本文に X 投稿案（または {{ARTICLE_URL}}）が残っています。記事には不要です")
    if has_broken_bold(body):
        warnings.append("閉じの ** の直前が句読点・括弧で、直後が文字の箇所があります。太字にならず ** が表示されます")
    if not body.strip():
        errors.append("本文が空です")

    return result


# ---------- 実行 ----------

def collect_targets(paths, include_drafts: bool):
    if paths:
        return [Path(p).resolve() for p in paths]
    targets = []
    for d in sorted(POSTS_DIR.iterdir()):
        if not (d / "index.md").is_file():
            continue
        if not include_drafts:
            try:
                fm, _ = parse_post(d / "index.md")
            except ValueError:
                fm = {}
            if fm.get("draft") is True:
                continue
        targets.append(d)
    return targets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="記事（ページバンドル）の機械チェック")
    ap.add_argument("paths", nargs="*", help="記事フォルダ（省略時は draft: false の全記事）")
    ap.add_argument("--all", action="store_true", help="下書きも含めて全記事をチェックする")
    ap.add_argument("--allow-missing-image", action="store_true", help="画像がない場合をエラーでなく警告にする")
    ap.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    args = ap.parse_args(argv)

    wards = load_toml_keys(ROOT / "data" / "wards.toml")
    categories = load_toml_keys(ROOT / "data" / "categories.toml")
    targets = collect_targets(args.paths, args.all)

    results = [validate(t, wards, categories, args.allow_missing_image) for t in targets]
    failed = any(r["errors"] for r in results)

    if args.json:
        print(json.dumps({"ok": not failed, "posts": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            status = "NG" if r["errors"] else "OK"
            print("[%s] %s" % (status, r["slug"]))
            for e in r["errors"]:
                print("   エラー: " + e)
            for w in r["warnings"]:
                print("   警告  : " + w)
        if not results:
            print("チェック対象の記事がありません")
        print("\n%d 本チェック、エラーのある記事 %d 本" % (len(results), sum(1 for r in results if r["errors"])))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
