#!/usr/bin/env python3
"""サムネ用 YAML から Gemini API で画像を作り、1200x630 に切り抜いて記事フォルダに保存する。

使い方:
  set -a; source .env.local; set +a          # 手元では環境変数を読み込む
  .venv/bin/python scripts/generate_thumbnail.py samples/thumbnails/<スラッグ>.yaml
  .venv/bin/python scripts/generate_thumbnail.py <yaml> --dry-run   # API を呼ばずに確認だけ

環境変数（GitHub では Secrets / Variables）:
  GEMINI_API_KEY      API キー（値はログ・出力に出さない）
  GEMINI_IMAGE_MODEL  画像生成モデル名（コードには書かない）

終了コード: 0 成功 / 1 入力の誤り / 2 API または画像処理の失敗（記事だけの PR を出す運用のため区別する）
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "content" / "posts"
THUMBNAIL_PROMPT = ROOT / "prompts" / "thumbnail.txt"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
FINAL_SIZE = (1200, 630)
REQUIRED_KEYS = ["filename", "aspect_ratio", "final_size", "prompt", "scene_ja", "intent_ja", "omitted_ja"]
RETRY_STATUS = {429, 500, 502, 503, 504}


class InputError(Exception):
    pass


class GenerationError(Exception):
    pass


# ---------- 入力 ----------

def parse_yaml(text: str) -> dict:
    """`key: "value"` だけの平らな YAML を読む（コードブロックの囲みは無視する）。"""
    data = {}
    for line in text.splitlines():
        if line.strip().startswith("```") or not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r'^([A-Za-z_]+):\s*(.*)$', line)
        if not m:
            raise InputError("YAML の行を解釈できません: " + line[:40])
        raw = m.group(2).strip()
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except ValueError:
                raise InputError("文字列の形式が不正です（%s）" % m.group(1))
        else:
            value = raw
        data[m.group(1)] = value
    return data


def load_fixed_blocks() -> tuple:
    """prompts/thumbnail.txt から STYLE BLOCK と NEGATIVE の文言を取り出す。"""
    text = THUMBNAIL_PROMPT.read_text(encoding="utf-8")
    blocks = []
    for label in ("STYLE BLOCK:", "NEGATIVE:"):
        m = re.search(re.escape(label) + r'\s*\n\s*"([^"]+)"', text)
        if not m:
            raise InputError("prompts/thumbnail.txt から %s を取り出せません" % label)
        blocks.append(m.group(1))
    return blocks[0], blocks[1]


def check_spec(spec: dict) -> Path:
    missing = [k for k in REQUIRED_KEYS if k not in spec]
    if missing:
        raise InputError("YAML に項目がありません: " + ", ".join(missing))
    if spec["aspect_ratio"] != "16:9":
        raise InputError("aspect_ratio は 16:9 にしてください（現在: %s）" % spec["aspect_ratio"])
    if spec["final_size"] != "%dx%d" % FINAL_SIZE:
        raise InputError("final_size は 1200x630 にしてください（現在: %s）" % spec["final_size"])

    style, negative = load_fixed_blocks()
    prompt = spec["prompt"].strip()
    if not prompt.startswith(style):
        raise InputError("prompt が STYLE BLOCK（prompts/thumbnail.txt）で始まっていません")
    if not prompt.endswith(negative):
        raise InputError("prompt が NEGATIVE（prompts/thumbnail.txt）で終わっていません")

    filename = spec["filename"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.png", filename):
        raise InputError("filename は「<スラッグ>.png」の形式にしてください: " + filename)
    return POSTS_DIR / filename[:-4] / filename


# ---------- Gemini API ----------

def request_image(model: str, api_key: str, prompt: str, retries: int = 3) -> bytes:
    url = "%s/%s:generateContent" % (API_BASE, model)
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,  # ヘッダーで渡す（URL やログにキーを残さない）
    })

    last = "不明なエラー"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return extract_image(payload)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")[:200]
            except Exception:
                pass
            last = "HTTP %d %s" % (e.code, detail)
            if e.code not in RETRY_STATUS:
                raise GenerationError(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = "通信エラー: %s" % type(e).__name__
        if attempt < retries:
            wait = 5 * attempt
            print("  再試行します（%d/%d、%d秒後）: %s" % (attempt, retries - 1, wait, last), file=sys.stderr)
            time.sleep(wait)
    raise GenerationError("リトライしても失敗しました: " + last)


def extract_image(payload: dict) -> bytes:
    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    reason = ""
    if payload.get("promptFeedback", {}).get("blockReason"):
        reason = "（プロンプトがブロックされました: %s）" % payload["promptFeedback"]["blockReason"]
    elif payload.get("candidates"):
        reason = "（finishReason: %s）" % payload["candidates"][0].get("finishReason", "不明")
    raise GenerationError("応答に画像が含まれていません" + reason)


# ---------- 画像処理 ----------

def crop_to_final(image_bytes: bytes):
    """中央を基準に 1200x630 に切り抜く（幅 1200 に縮小 → 上下を均等に削る）。"""
    from PIL import Image  # 遅延 import（--dry-run では不要）

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        raise GenerationError("返ってきたデータを画像として読めません")
    img = img.convert("RGB")
    w, h = img.size
    tw, th = FINAL_SIZE
    scale = max(tw / w, th / h)
    nw, nh = round(w * scale), round(h * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return img.crop((left, top, left + tw, top + th)), (w, h)


# ---------- 実行 ----------

def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="サムネ画像の生成（Gemini API）")
    ap.add_argument("yaml", help="thumbnail.txt の出力 YAML")
    ap.add_argument("--dry-run", action="store_true", help="API を呼ばず、読み取り内容と保存先を表示する")
    ap.add_argument("--force", action="store_true", help="保存先に画像があっても上書きする")
    ap.add_argument("--out", help="保存先のファイルを指定する（試し生成用。省略時は記事フォルダ）")
    args = ap.parse_args(argv)

    try:
        spec = parse_yaml(Path(args.yaml).read_text(encoding="utf-8"))
        dest = check_spec(spec)
    except (InputError, OSError) as e:
        print("入力エラー: %s" % e, file=sys.stderr)
        return 1

    if args.out:
        dest = Path(args.out).resolve()

    model = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    print("記事:   %s" % spec["filename"][:-4])
    print("保存先: %s" % rel(dest))
    print("モデル: %s" % (model or "（未設定）"))
    print("情景:   %s" % spec["scene_ja"])

    if args.dry_run:
        print("--dry-run: API は呼びません。YAML の確認は OK です。")
        return 0
    if not model or not api_key:
        print("入力エラー: 環境変数 GEMINI_IMAGE_MODEL と GEMINI_API_KEY を設定してください", file=sys.stderr)
        return 1
    if not dest.parent.is_dir():
        print("入力エラー: 保存先のフォルダがありません: %s" % rel(dest.parent), file=sys.stderr)
        return 1
    if dest.exists() and not args.force:
        print("入力エラー: 保存先に画像があります（上書きするには --force）", file=sys.stderr)
        return 1

    try:
        print("生成中…")
        raw = request_image(model, api_key, spec["prompt"].strip())
        img, original = crop_to_final(raw)
    except GenerationError as e:
        print("生成に失敗しました: %s" % e, file=sys.stderr)
        return 2

    img.save(dest, "PNG", optimize=True)
    print("保存しました: %s（元画像 %dx%d → %dx%d）" % (rel(dest), original[0], original[1], *FINAL_SIZE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
