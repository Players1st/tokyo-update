#!/usr/bin/env python3
"""有料プランの注文 issue を読み、記事生成の入力（.work/order.json）を作る。標準ライブラリのみ。

入力: .work/issue.json（`gh api repos/<repo>/issues/<番号>` の出力）
出力: .work/order.json
注文として使えないとき（ラベルなし、入金未確認、公開日の形が不正など）は、理由を表示して終了コード 1 にする。
issue の本文は、お客様のメモを含むので、あとの工程では「データ」として扱う（指示には従わない）。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"
ALLOWED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
JST = timezone(timedelta(hours=9))
FIELDS = {
    "お名前（店舗名・団体名）": "name",
    "プラン": "plan",
    "公開希望日": "publish_date",
    "掲載したい内容のメモ・参考URL": "content",
    "入金確認": "paid",
    "備考": "notes",
}


def parse_sections(body: str) -> dict:
    sections = {}
    parts = re.split(r"^### +(.+?)\s*$", body or "", flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        value = parts[i + 1].strip()
        sections[parts[i].strip()] = "" if value == "_No response_" else value
    return sections


def build_order(issue: dict, today: date) -> tuple:
    errors = []
    labels = [l.get("name") if isinstance(l, dict) else l for l in issue.get("labels", [])]
    if "paid-order" not in labels:
        errors.append("issue に paid-order ラベルがありません")
    if issue.get("author_association") not in ALLOWED_ASSOCIATIONS:
        errors.append("issue の作成者が、リポジトリの関係者ではありません（%s）" % issue.get("author_association"))
    if issue.get("pull_request"):
        errors.append("プルリクエストは注文として使えません")
    if issue.get("state") != "open":
        errors.append("issue が open ではありません")

    sec = parse_sections(issue.get("body", ""))
    order = {"issue_number": issue.get("number"), "issue_title": issue.get("title", "")}
    for label, key in FIELDS.items():
        order[key] = sec.get(label, "")
    for key, label in (("name", "お名前"), ("plan", "プラン"), ("publish_date", "公開希望日"), ("content", "メモ・参考URL")):
        if not order[key]:
            errors.append("%s が空です" % label)
    if not re.search(r"^- \[[xX]\]", order["paid"], flags=re.M):
        errors.append("入金確認にチェックがありません")
    try:
        d = datetime.strptime(order["publish_date"], "%Y-%m-%d").date()
        if d < today:
            errors.append("公開希望日が過去です: %s" % order["publish_date"])
        order["publish_datetime"] = d.strftime("%Y-%m-%dT07:00:00+09:00")
    except ValueError:
        errors.append("公開希望日が YYYY-MM-DD の形ではありません: %r" % order["publish_date"])
    order.pop("paid", None)
    return order, errors


def main() -> int:
    issue = json.loads((WORK / "issue.json").read_text(encoding="utf-8"))
    order, errors = build_order(issue, datetime.now(JST).date())
    if errors:
        for e in errors:
            print("::error::" + e)
        return 1
    (WORK / "order.json").write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    print("注文 #%s を読みました（公開日時 %s）" % (order["issue_number"], order["publish_datetime"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
