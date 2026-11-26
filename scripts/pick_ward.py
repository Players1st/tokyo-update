#!/usr/bin/env python3
"""毎朝の記事で扱う区の指定文を作る。標準ライブラリのみ。

重点エリア（hugo.toml の priorityWards）を、「最後に記事にした時期が古い順」に並べて出力する。
まだ記事のない区が最優先。時期は、data/published-topics.json の並び順（後ろほど新しい）で判断する。

使い方: python3 scripts/pick_ward.py   → 指定文を1行で出力
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def priority_wards(toml_text: str) -> list:
    m = re.search(r"^priorityWards\s*=\s*\[(.*?)\]", toml_text, flags=re.M)
    wards = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if not wards:
        raise ValueError("hugo.toml に priorityWards がありません")
    return wards


def ward_names(toml_text: str) -> dict:
    return {a or b: name for a, b, name in
            re.findall(r'^\s*(?:"([^"]+)"|([A-Za-z0-9_]+))\s*=\s*"([^"]*)"', toml_text, flags=re.M)}


def order_wards(wards: list, topics: list) -> list:
    last = {t.get("ward"): i for i, t in enumerate(topics)}
    return sorted(wards, key=lambda w: (last.get(w, -1), wards.index(w)))


def main() -> int:
    wards = priority_wards((ROOT / "hugo.toml").read_text(encoding="utf-8"))
    names = ward_names((ROOT / "data" / "wards.toml").read_text(encoding="utf-8"))
    topics = json.loads((ROOT / "data" / "published-topics.json").read_text(encoding="utf-8"))
    ordered = ["%s（%s）" % (names.get(w, w), w) for w in order_wards(wards, topics)]
    print("重点エリアのみ。優先順に %s。先の区に確認できる題材がなければ次の区へ。この%d区以外は選ばない"
          % ("、".join(ordered), len(ordered)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
