#!/usr/bin/env python3
"""記事の date と lastmod を、いまの日本時間（記事を作成した日時）に書き換える。標準ライブラリのみ。

AI が書いた日時が未来になると、マージしても公開されないことがあるため、毎朝の記事では機械的に上書きする。
有料記事は、公開希望日の 7:00 を指定するので、このスクリプトは使わない。

使い方: python3 scripts/set_post_date.py content/posts/<スラッグ> ...
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def set_date(text: str, stamp: str) -> str:
    """フロントマター（先頭の --- と次の --- の間）の date と lastmod だけを書き換える。"""
    m = re.match(r"\A(---\n)(.*?)(\n---\n)", text, flags=re.S)
    if not m:
        raise ValueError("フロントマターがありません")
    head, n = re.subn(r"^(date|lastmod):.*$", lambda x: "%s: %s" % (x.group(1), stamp), m.group(2), flags=re.M)
    if n != 2:
        raise ValueError("date と lastmod が1つずつ必要です（%d 件）" % n)
    return m.group(1) + head + m.group(3) + text[m.end():]


def main(argv) -> int:
    stamp = datetime.now(JST).replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    failed = False
    for d in argv:
        p = Path(d) / "index.md"
        try:
            p.write_text(set_date(p.read_text(encoding="utf-8"), stamp), encoding="utf-8")
            print("%s: %s" % (d, stamp))
        except (OSError, ValueError) as e:
            print("::warning::日時を書き換えられませんでした: %s (%s)" % (d, e))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
