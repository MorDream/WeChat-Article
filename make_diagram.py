"""用 JSON 描述画讲解性示意图（流程 / 对比），输出 PNG。

公众号正文里需要"自己画的图"来解释论文机制，这个脚本就是为了批量生产这种图。
一个 JSON 一行流程，比每次手绘省事。

用法：
    python make_diagram.py drafts/diagrams/pet.json -o drafts/assets/diag-pet.png

流程图的 JSON 结构（默认）：
{
  "title": "图的标题，可省略",
  "note": "底部小字说明，可省略",
  "width": 1040,
  "nodes": [
    {"title": "第一行大字", "sub": "第二行小字", "accent": false, "tag": "可选角标"}
  ],
  "arrow_labels": ["节点1→2 的标注", "..."]   // 可省略
}

左右对比的 JSON 结构（"type": "compare"）：
{
  "type": "compare",
  "title": "图的标题，可省略",
  "note": "底部小字说明，可省略",
  "left":  {"label": "旧做法", "title": "一句话结论", "points": ["要点", "..."], "accent": false},
  "right": {"label": "新做法", "title": "一句话结论", "points": ["要点", "..."], "accent": true}
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("缺少 pillow，先执行：pip install -r requirements.txt")

INK = "#1A1A1A"
SUB = "#6E6862"
MUTED = "#9A948B"
LINE = "#D9D3C7"
NODE_FILL = "#FAF8F3"
NODE_STROKE = "#DED8CB"
ACCENT_FILL = "#FDEEE8"
ACCENT_STROKE = "#D97757"
BG = "#FFFFFF"

FONTS = [
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("C:/Windows/Fonts/Dengb.ttf", 0),
    ("/System/Library/Fonts/PingFang.ttc", 0),
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path, idx in FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=idx)
            except OSError:
                continue
    return ImageFont.load_default()


def tokenize(text: str) -> list[str]:
    """按「词」切分：英文单词和数字整体保留，中文按字，避免把 0.5 或 VLA 拆开。"""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "._%+-/"):
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
    if buf:
        tokens.append(buf)

    # 把「0.5 秒」「15 步」这类数字 + 量词粘在一起
    merged: list[str] = []
    i = 0
    while i < len(tokens):
        cur = tokens[i]
        if (cur and cur[0].isascii() and cur[0].isalnum() and i + 2 < len(tokens)
                and tokens[i + 1] == " " and not tokens[i + 2].isascii()):
            merged.append(cur + " " + tokens[i + 2])
            i += 3
            continue
        merged.append(cur)
        i += 1
    return merged


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for tok in tokenize(text):
        trial = cur + tok
        if f.getlength(trial) > max_w and cur.strip():
            lines.append(cur.rstrip())
            cur = "" if tok == " " else tok
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.rstrip())

    # 避免最后一行只剩一个汉字（中文排版里的"孤字"）
    if len(lines) > 1 and len(lines[-1]) == 1 and not lines[-1][0].isascii():
        prev = lines[-2]
        if len(prev) > 2:
            moved = prev[-1] + lines[-1]
            if f.getlength(moved) <= max_w:
                lines[-2] = prev[:-1].rstrip()
                lines[-1] = moved
    return lines


def draw_arrow(d: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int) -> None:
    d.line([(x1, y1), (x2 - 7, y2)], fill=MUTED, width=2)
    d.polygon([(x2, y2), (x2 - 9, y2 - 5), (x2 - 9, y2 + 5)], fill=MUTED)


def render_flow(spec: dict, out: Path) -> Path:
    nodes = spec["nodes"]
    if len(nodes) > 5:
        raise SystemExit("一行最多 5 个节点，再多请拆成两张图")

    width = spec.get("width", 1120)
    S = float(spec.get("font_scale", 1.0))
    margin = 56
    gap = 44
    node_h = int(112 * S)
    title = spec.get("title", "")
    note = spec.get("note", "")
    labels = spec.get("arrow_labels", [])

    top = 0
    f_title = font(int(24 * S))
    title_block = 0
    if title:
        title_block = int(58 * S)
        top = 24

    node_y = top + title_block + 16
    note_block = 52 if note else 0
    height = node_y + node_h + 26 + note_block

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)

    if title:
        d.text((margin, 24), title, font=f_title, fill=INK)

    n = len(nodes)
    node_w = (width - margin * 2 - gap * (n - 1)) // n

    f_node = font(int(19 * S))
    f_sub = font(int(14 * S))

    for i, node in enumerate(nodes):
        x = margin + i * (node_w + gap)
        accent = node.get("accent", False)
        d.rounded_rectangle(
            [x, node_y, x + node_w, node_y + node_h],
            radius=10,
            fill=ACCENT_FILL if accent else NODE_FILL,
            outline=ACCENT_STROKE if accent else NODE_STROKE,
            width=1,
        )
        if node.get("tag"):
            tag_f = font(int(12 * S))
            tw = tag_f.getlength(node["tag"]) + 14
            d.rounded_rectangle([x + 10, node_y + 10, x + 10 + tw, node_y + 28],
                                radius=9, fill=ACCENT_STROKE)
            d.text((x + 17, node_y + 12), node["tag"], font=tag_f, fill="#FFFFFF")

        inner_w = node_w - 26
        t_lines = wrap(node.get("title", ""), f_node, inner_w)[:3]
        s_lines = wrap(node.get("sub", ""), f_sub, inner_w)[:3] if node.get("sub") else []

        lh_t, lh_s = int(27 * S), int(21 * S)
        block_h = len(t_lines) * lh_t + (len(s_lines) * lh_s + int(8 * S) if s_lines else 0)
        ty = node_y + (node_h - block_h) // 2 + 2
        for ln in t_lines:
            d.text((x + node_w // 2 - f_node.getlength(ln) / 2, ty), ln, font=f_node, fill=INK)
            ty += lh_t
        ty += int(8 * S)
        for ln in s_lines:
            d.text((x + node_w // 2 - f_sub.getlength(ln) / 2, ty), ln, font=f_sub, fill=SUB)
            ty += lh_s

        if i < n - 1:
            ax1 = x + node_w + 8
            ax2 = x + node_w + gap - 8
            ay = node_y + node_h // 2
            draw_arrow(d, ax1, ay, ax2, ay)
            if i < len(labels) and labels[i]:
                lf = font(13)
                d.text((ax1 + (ax2 - ax1) / 2 - lf.getlength(labels[i]) / 2, ay - 24),
                       labels[i], font=lf, fill=MUTED)

    if note:
        f_note = font(int(14 * S))
        d.text((margin, node_y + node_h + int(18 * S)), note, font=f_note, fill=MUTED)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


def render_compare(spec: dict, out: Path) -> Path:
    """左右两栏对比：左边旧做法，右边新做法。高度按文字量自适应。"""
    left, right = spec["left"], spec["right"]
    width = spec.get("width", 1120)
    S = float(spec.get("font_scale", 1.0))
    margin = 56
    gap = 32
    pad = int(26 * S)
    title = spec.get("title", "")
    note = spec.get("note", "")

    f_title = font(int(24 * S))
    f_label = font(int(13 * S))
    f_head = font(int(20 * S))
    f_point = font(int(15 * S))

    top = 24 if title else 0
    card_top = top + (58 if title else 0) + 16
    card_w = (width - margin * 2 - gap) // 2
    inner_w = card_w - pad * 2

    # 先排版，算出两栏各自需要多高
    layout = []
    for col in (left, right):
        head_lines = wrap(col.get("title", ""), f_head, inner_w)[:3]
        point_lines = [wrap(p, f_point, inner_w - 18) for p in col.get("points", [])]
        h = pad + int(26 * S) + len(head_lines) * int(30 * S) + int(12 * S)
        for lines in point_lines:
            h += len(lines) * int(23 * S) + int(7 * S)
        layout.append((head_lines, point_lines, h + pad - 7))

    card_h = max(h for _, _, h in layout)

    note_block = 46 if note else 0
    height = card_top + card_h + 24 + note_block

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)

    if title:
        d.text((margin, 24), title, font=f_title, fill=INK)

    for i, col in enumerate((left, right)):
        x = margin + i * (card_w + gap)
        accent = col.get("accent", False)
        d.rounded_rectangle(
            [x, card_top, x + card_w, card_top + card_h],
            radius=12,
            fill=ACCENT_FILL if accent else NODE_FILL,
            outline=ACCENT_STROKE if accent else NODE_STROKE,
            width=2 if accent else 1,
        )

        head_lines, point_lines, _ = layout[i]
        y = card_top + pad

        if col.get("label"):
            tw = f_label.getlength(col["label"]) + 16
            d.rounded_rectangle([x + pad, y, x + pad + tw, y + 22],
                                radius=11, fill=ACCENT_STROKE if accent else LINE)
            d.text((x + pad + 8, y + 4), col["label"], font=f_label,
                   fill="#FFFFFF" if accent else SUB)
        y += 26 + 6

        for ln in head_lines:
            d.text((x + pad, y), ln, font=f_head, fill=INK)
            y += int(30 * S)
        y += int(12 * S)

        for lines in point_lines:
            d.ellipse([x + pad, y + 8, x + pad + 5, y + 13],
                      fill=ACCENT_STROKE if accent else MUTED)
            for j, ln in enumerate(lines):
                d.text((x + pad + 18, y + j * int(23 * S)), ln, font=f_point, fill=SUB)
            y += len(lines) * int(23 * S) + int(7 * S)

    if note:
        f_note = font(int(14 * S))
        d.text((margin, card_top + card_h + int(16 * S)), note, font=f_note, fill=MUTED)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="根据 JSON 生成讲解示意图")
    parser.add_argument("spec", help="JSON 文件路径")
    parser.add_argument("-o", "--out", required=True, help="输出 PNG 路径")
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    renderer = render_compare if spec.get("type") == "compare" else render_flow
    path = renderer(spec, Path(args.out))
    print(f"示意图已生成：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
