"""把一篇 Markdown 稿件推进公众号草稿箱。

用法：
    python push.py drafts/2026-11-03.md --cover drafts/cover.png
    python push.py drafts/2026-11-03.md --dry-run      # 只生成 HTML，不调接口
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from wxpub import (
    MPClient,
    WeChatError,
    build_article,
    load_env,
    markdown_to_html,
)

ROOT = Path(__file__).resolve().parent
DRAFTS = ROOT / "drafts"


def upload_local_images(client: MPClient, html: str) -> tuple[str, int]:
    """正文里引用的本地图片先传到微信图床，换成永久 URL。"""
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        path = (DRAFTS / src) if not Path(src).is_absolute() else Path(src)
        if not path.exists():
            print(f"  ! 图片找不到，已保留原样：{src}")
            return match.group(0)
        url = client.upload_inline_image(path)
        count += 1
        print(f"  · 已上传插图 {path.name}")
        return match.group(0).replace(src, url)

    return re.sub(r'<img[^>]+src="([^"]+)"', repl, html), count


def main() -> int:
    parser = argparse.ArgumentParser(description="推送 Markdown 稿件到公众号草稿箱")
    parser.add_argument("md", help="稿件路径")
    parser.add_argument("--cover", help="封面图（推荐 900x383）")
    parser.add_argument("--author", default=os.getenv("WX_AUTHOR", ""), help="作者名，最多 8 字")
    parser.add_argument("--dry-run", action="store_true", help="只生成 HTML 预览，不调用接口")
    parser.add_argument("--no-disclosure", action="store_true", help="不追加 AI 辅助生成声明")
    parser.add_argument("--publish", action="store_true", help="尝试直接发布（仅认证号可用）")
    args = parser.parse_args()

    md_path = Path(args.md)
    if not md_path.is_absolute():
        md_path = (ROOT / md_path) if not md_path.exists() else md_path
    if not md_path.exists():
        print(f"稿件不存在：{md_path}")
        return 1

    html, meta = markdown_to_html(
        md_path.read_text(encoding="utf-8"),
        disclosure=not args.no_disclosure,
    )
    print(f"标题：{meta.get('title', '(未识别)')}")
    print(f"摘要：{meta.get('digest', '')[:60]}…")
    print(f"正文长度：{len(html)} 字符")

    if len(html) > 20000:
        print("  注意：正文接近接口上限，建议拆篇或压缩篇幅")

    if args.dry_run:
        out = md_path.with_suffix(".preview.html")
        preview = (
            '<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="margin:0;background:#f5f5f5">'
            '<div style="max-width:420px;margin:0 auto;background:#fff;padding:20px 18px;'
            'font-family:-apple-system,\'PingFang SC\',sans-serif">'
            + html
            + "</div></body>"
        )
        out.write_text(preview, encoding="utf-8")
        print(f"预览已生成：{out}")
        return 0

    load_env(ROOT / ".env")
    client = MPClient(os.getenv("WX_APPID", ""), os.getenv("WX_APPSECRET", ""), ROOT / ".cache")

    try:
        html, _ = upload_local_images(client, html)

        cover = Path(args.cover) if args.cover else None
        if cover and not cover.is_absolute():
            cover = ROOT / cover
        if not cover or not cover.exists():
            print("缺少封面图，用 --cover 指定一张（推荐 900x383）")
            return 1

        thumb_id, how = client.upload_cover(cover)
        print(f"封面上传成功（{how}）")

        article = build_article(html, meta, thumb_id, args.author)
        media_id = client.add_draft(article)
        print(f"\n已进草稿箱，media_id = {media_id}")
        print("下一步：手机「公众号助手」或后台「内容管理 - 草稿箱」预览后点群发")

        if args.publish:
            try:
                pid = client.submit_publish(media_id)
                print(f"已提交发布，publish_id = {pid}")
            except WeChatError as exc:
                print(f"自动发布失败（个人订阅号的预期行为）：{exc}")
                print("去后台手动点群发即可。")

    except WeChatError as exc:
        print(f"\n接口报错：{exc}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
