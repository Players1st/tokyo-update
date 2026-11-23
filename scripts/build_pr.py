#!/usr/bin/env python3
"""毎朝のパイプラインのプルリクエスト本文（と題名）を作る。標準ライブラリのみ。

入力（.work/ 以下）:
  result.json              記事のスラッグと、確認できなかった項目 unverified（記事生成の工程が書く）
  validate.json            validate_post.py --json の出力
  thumbnails/<スラッグ>.yaml  サムネ用 YAML（intent_ja / omitted_ja を読む）
出力:
  .work/pr-title.txt, .work/pr-body.md, .work/pr-has-errors（エラーがあるときだけ作る）

Hiro はスマホで確認するので、短く読みやすくする。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_thumbnail as gt  # noqa: E402  YAML の読み込みを再利用
import validate_post as vp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"
MAX_CHECK_LINES = 10


def ward_name(slug: str) -> str:
    wards = {}
    for line in (ROOT / "data" / "wards.toml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*(?:"([^"]+)"|([A-Za-z0-9_]+))\s*=\s*"([^"]*)"', line)
        if m:
            wards[m.group(1) or m.group(2)] = m.group(3)
    return wards.get(slug, slug)


def load_thumb_yaml(slug: str) -> dict:
    p = WORK / "thumbnails" / (slug + ".yaml")
    if not p.is_file():
        return {}
    try:
        return gt.parse_yaml(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    result = json.loads((WORK / "result.json").read_text(encoding="utf-8"))
    slugs = [a["slug"] for a in result.get("articles", [])]
    unverified_by_slug = {a["slug"]: a.get("unverified", []) for a in result.get("articles", [])}
    validate = {}
    vpath = WORK / "validate.json"
    if vpath.is_file():
        validate = {p["slug"]: p for p in json.loads(vpath.read_text(encoding="utf-8")).get("posts", [])}

    sections, titles, has_errors = [], [], False
    for slug in slugs:
        post_dir = ROOT / "content" / "posts" / slug
        try:
            fm, body = vp.parse_post(post_dir / "index.md")
        except (ValueError, OSError):
            fm, body = {}, ""
        title = fm.get("title", slug)
        ward = ward_name(fm.get("ward", ""))
        titles.append(title)
        v = validate.get(slug, {"errors": ["機械チェックの結果がありません"], "warnings": []})
        has_errors = has_errors or bool(v["errors"])
        has_image = (post_dir / (slug + ".png")).is_file()
        spec = load_thumb_yaml(slug)

        lines = ["## %s" % title, "- 対象の区: %s" % ward, ""]
        checks = unverified_by_slug.get(slug, [])
        lines.append("### 要確認（%d 件。記事の本文には載せていません）" % len(checks))
        if checks:
            lines += ["- " + c for c in checks[:MAX_CHECK_LINES]]
            if len(checks) > MAX_CHECK_LINES:
                lines.append("- …ほか %d 件" % (len(checks) - MAX_CHECK_LINES))
        else:
            lines.append("- なし")
        lines.append("")
        lines.append("### サムネ")
        if has_image:
            lines.append("- 情景: %s" % spec.get("scene_ja", "（記載なし）"))
            lines.append("- なぜこの絵か: %s" % spec.get("intent_ja", "（記載なし）"))
            lines.append("- あえて描かなかったもの: %s" % spec.get("omitted_ja", "（記載なし）"))
            lines.append("- 画像の内容が記事と食い違っていないか、目で確認してください")
        else:
            lines.append("- **画像なし**（生成に失敗しました。記事だけの PR です。Actions のログを確認してください）")
        lines.append("")
        lines.append("### 機械チェック: %s" % ("**NG**" if v["errors"] else "OK"))
        lines += ["- エラー: " + e for e in v["errors"]]
        lines += ["- 警告: " + w for w in v["warnings"]]
        sections.append("\n".join(lines))

    if len(slugs) == 1:
        title = "%s（自動生成）" % titles[0]
    else:
        title = "毎朝の記事 %d 本（自動生成）" % len(slugs)
    footer = ["---", "公開してよいと判断したら、マージしてください（マージで自動公開されます）。"]
    if has_errors:
        footer.insert(1, "⚠ 機械チェックでエラーがあるため、ドラフトの PR にしています。")
    body_md = "\n\n".join(sections + ["\n".join(footer)]) + "\n"

    (WORK / "pr-title.txt").write_text(title, encoding="utf-8")
    (WORK / "pr-body.md").write_text(body_md, encoding="utf-8")
    flag = WORK / "pr-has-errors"
    if has_errors:
        flag.write_text("1", encoding="utf-8")
    elif flag.exists():
        flag.unlink()
    print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
