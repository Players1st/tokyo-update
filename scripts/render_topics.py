#!/usr/bin/env python3
"""ネタ探しの結果（.work/topics.json）を、読みやすい Markdown にして出力する。標準ライブラリのみ。

使い方: python3 scripts/render_topics.py > .work/topics.md
集計（ジャンル別の件数、確認できた件数、個人経営と判断した件数）も、先頭に出す。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENRES = ["gourmet", "beauty_fitness", "food_event", "music_event"]
GENRE_JA = {"gourmet": "グルメ（個人店）", "beauty_fitness": "美容・フィットネス（個人店）",
            "food_event": "飲食イベント", "music_event": "音楽イベント"}


def cell(s) -> str:
    return str(s if s is not None else "").replace("|", "／").replace("\n", " ")


def main() -> int:
    data = json.loads((ROOT / ".work" / "topics.json").read_text(encoding="utf-8"))
    topics = data.get("topics", [])
    out = ["# ネタ探しの結果", ""]

    out += ["## 集計", "", "| ジャンル | 候補 | 確認できた | 個人経営 | 記事にできそう（yes） |", "|---|---|---|---|---|"]
    for g in GENRES:
        ts = [t for t in topics if t.get("genre") == g]
        out.append("| %s | %d | %d | %d | %d |" % (
            GENRE_JA[g], len(ts),
            sum(1 for t in ts if t.get("verified") is True),
            sum(1 for t in ts if t.get("chain_check") == "independent"),
            sum(1 for t in ts if t.get("usable") == "yes")))
    st = Counter(t.get("source_type", "other") for t in topics)
    out += ["", "情報源の種類: " + "、".join("%s %d件" % (k, v) for k, v in st.most_common()) if st else "情報源の種類: なし", ""]

    for g in GENRES:
        ts = [t for t in topics if t.get("genre") == g]
        out += ["## %s（%d件）" % (GENRE_JA[g], len(ts)), ""]
        if not ts:
            out += ["見つかりませんでした。", ""]
            continue
        out += ["| 区 | 名前 | 日付（記事化の目安） | 場所 | 情報源 | 確認 | チェーン | 記事化 |", "|---|---|---|---|---|---|---|---|"]
        for t in ts:
            out.append("| %s | %s<br>%s | %s | %s | [%s](%s) | %s | %s（%s） | %s（%s） |" % (
                cell(t.get("ward")), cell(t.get("name")), cell(t.get("summary")),
                cell(t.get("date")) + ("<br>目安: " + cell(t.get("publish_hint")) if t.get("publish_hint") else ""),
                cell(t.get("place")), cell(t.get("source_type")), cell(t.get("source_url")),
                "○" if t.get("verified") is True else "×",
                cell(t.get("chain_check")), cell(t.get("chain_reason")),
                cell(t.get("usable")), cell(t.get("usable_reason"))))
        out.append("")

    out += ["## 試した検索", ""] + ["- " + cell(q) for q in data.get("queries", [])] + [""]
    out += ["## 情報源ごとのメモ", ""] + ["- " + cell(n) for n in data.get("source_notes", [])] + [""]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
