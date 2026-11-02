"""根据标题生成公众号封面图（900×383，微信推荐 2.35:1）。

用法：
    python make_cover.py "文章标题" --sub "一句话副标题" -o drafts/cover.png

不依赖 AI，纯本地渲染，字体用系统自带的微软雅黑，保证每天出图稳定。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("缺少 pillow，先执行：pip install -r requirements.txt")

SIZE = (900, 383)
BG = "#F7F5F0"
INK = "#1A1A1A"
MUTED = "#8A8A8A"
ACCENT = "#D97757"

FONT_CANDIDATES = [
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("C:/Windows/Fonts/Dengb.ttf", 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    print("没找到中文字体，回退到默认字体（中文可能显示成方块）", file=sys.stderr)
    return ImageFont.load_default()


PUNCT = "，。、；：！？,.;:!?"


def split_at_punct(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str] | None:
    """优先在标点处断成两行，读起来比在词中间断开自然。"""
    best = None
    for i, ch in enumerate(text[:-1]):
        if ch not in PUNCT:
            continue
        head, tail = text[:i + 1], text[i + 1:]
        if font.getlength(head) <= max_w and font.getlength(tail) <= max_w:
            diff = abs(font.getlength(head) - font.getlength(tail))
            if best is None or diff < best[0]:
                best = (diff, [head, tail])
    return best[1] if best else None


def split_balanced(text: str, font: ImageFont.FreeTypeFont, k: int) -> list[str]:
    """把标题均分成 k 行，避免出现「最后一行只剩两三个字」的难看断法。"""
    total = font.getlength(text)
    target = total / k
    lines: list[str] = []
    cur = ""
    for ch in text:
        cur += ch
        if font.getlength(cur) >= target and len(lines) < k - 1:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if font.getlength(trial) > max_width and current:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines[:4]


def render(title: str, sub: str = "", brand: str = "", accent: str = ACCENT,
           out: str = "cover.png") -> Path:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    margin_x = 84
    max_text_width = SIZE[0] - margin_x - 72

    # 标题：从 44px 起逐级缩小，优先用尽量少的行数，且每行宽度均衡
    size, lines, title_font = 28, wrap(title, load_font(28, bold=True), max_text_width), load_font(28, bold=True)
    for candidate in (44, 40, 36, 32, 28):
        f = load_font(candidate, bold=True)
        picked = None
        if f.getlength(title) <= max_text_width:
            picked = [title]
        else:
            picked = split_at_punct(title, f, max_text_width)
            for k in (2, 3):
                if picked:
                    break
                trial = split_balanced(title, f, k)
                if len(trial) == k and all(f.getlength(ln) <= max_text_width for ln in trial):
                    picked = trial
        if picked:
            size, lines, title_font = candidate, picked, f
            break

    line_height = int(size * 1.42)
    block_h = len(lines) * line_height
    sub_font = load_font(20)
    sub_h = 40 if sub else 0
    total_h = block_h + sub_h
    start_y = (SIZE[1] - total_h) // 2 - 4

    # 左侧竖条
    bar_top = start_y + 6
    bar_h = block_h - 12
    draw.rounded_rectangle(
        [margin_x - 28, bar_top, margin_x - 23, bar_top + bar_h],
        radius=2.5, fill=accent,
    )

    y = start_y
    for line in lines:
        draw.text((margin_x, y), line, font=title_font, fill=INK)
        y += line_height

    if sub:
        draw.text((margin_x, y + 10), sub, font=sub_font, fill=MUTED)

    if brand:
        brand_font = load_font(17)
        w = brand_font.getlength(brand)
        draw.text((SIZE[0] - 44 - w, SIZE[1] - 46), brand, font=brand_font, fill="#B5B2AB")
        draw.line([(SIZE[0] - 44 - w - 34, SIZE[1] - 38), (SIZE[0] - 44 - w - 12, SIZE[1] - 38)],
                  fill="#D8D4CB", width=1)

    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成公众号封面图")
    parser.add_argument("title", help="封面上显示的大标题")
    parser.add_argument("--sub", default="", help="副标题，一行小字")
    parser.add_argument("--brand", default="", help="右下角品牌名")
    parser.add_argument("--accent", default=ACCENT, help="强调色，默认 #D97757")
    parser.add_argument("-o", "--out", default="drafts/cover.png")
    args = parser.parse_args()

    path = render(args.title, args.sub, args.brand, args.accent, args.out)
    print(f"封面已生成：{path}  ({SIZE[0]}×{SIZE[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
