"""生成「同一个字，两种画布」的横向双条柱状图。

数据全部来自论文 Table 2 的默认设置行（单位：像素）：
1024×768 小画布 vs 8000×6000 大画布上，模型能读对一半的最小字高。
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INK = "#1A1A1A"
SUB = "#6E6862"
MUTED = "#9A948B"
GRID = "#E8E3D9"
SMALL = "#C9C2B4"
LARGE = "#D97757"
BG = "#FFFFFF"

FONTS = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/Dengb.ttf"]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONTS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("找不到中文字体")


# 厂商, 型号, 小画布字号(px), 大画布字号(px，None 表示整张被拒收)
ROWS = [
    ("Claude", "Haiku 5.5", 4.7, 14.4),
    ("Claude", "Sonnet 5.5", 4.2, 12.0),
    ("Gemini", "Flash-Lite 3.5", 4.8, 13.7),
    ("Gemini", "Flash 3.8", 4.2, 13.2),
    ("OpenAI", "Luna (GPT-6)", 5.0, None),
    ("OpenAI", "Sol (GPT-6.1)", 4.3, None),
    ("Qwen", "3.8-27B", 5.4, 15.1),
]

W = 640
PAD_L = 176
PAD_R = 22
PAD_T = 22
TITLE_H = 44
LEGEND_H = 42
ROW_H = 56
BAR_H = 15
AXIS_MAX = 16.0
PLOT_W = W - PAD_L - PAD_R
PAD_B = 62

f_title = font(25)
f_vendor = font(12)
f_label = font(20)
f_val = font(19)
f_note = font(14)

height = PAD_T + TITLE_H + LEGEND_H + ROW_H * len(ROWS) + PAD_B
img = Image.new("RGB", (W, height), BG)
d = ImageDraw.Draw(img)

d.text((12, PAD_T - 4), "同一个字，两种画布", font=f_title, fill=INK)

y = PAD_T + TITLE_H
lx = PAD_L
for color, text in ((SMALL, "1024 小画布"), (LARGE, "8000 大画布")):
    d.rounded_rectangle([lx, y + 8, lx + 24, y + 22], radius=3, fill=color)
    d.text((lx + 30, y + 2), text, font=f_note, fill=SUB)
    lx += 168
y += LEGEND_H

x0 = PAD_L
for gx in range(0, 17, 4):
    px = x0 + PLOT_W * gx / AXIS_MAX
    d.line([px, y - 4, px, y + ROW_H * len(ROWS)], fill=GRID, width=1)
    d.text((px - 4, y + ROW_H * len(ROWS) + 6), str(gx), font=f_note, fill=MUTED)

for i, (vendor, name, small, large) in enumerate(ROWS):
    ry = y + i * ROW_H
    d.text((12, ry + 9), vendor, font=f_vendor, fill=MUTED)
    d.text((12, ry + 24), name, font=f_label, fill=INK)

    sw = PLOT_W * small / AXIS_MAX
    d.rounded_rectangle([x0, ry + 6, x0 + sw, ry + 6 + BAR_H], radius=2, fill=SMALL)
    d.text((x0 + sw + 7, ry + 4), f"{small:.1f}", font=f_val, fill=MUTED)

    if large is None:
        top = ry + 27
        box = [x0, top, x0 + 150, top + 20]
        for bx in range(int(box[0]), int(box[2]), 9):
            d.line([bx, box[1], min(bx + 4, box[2]), box[1]], fill=LARGE, width=1)
            d.line([bx, box[3], min(bx + 4, box[2]), box[3]], fill=LARGE, width=1)
        d.line([box[0], box[1], box[0], box[3]], fill=LARGE, width=1)
        d.line([box[2], box[1], box[2], box[3]], fill=LARGE, width=1)
        d.text((box[0] + 10, box[1] + 2), "整张拒收", font=f_val, fill=LARGE)
    else:
        lw = PLOT_W * large / AXIS_MAX
        d.rounded_rectangle([x0, ry + 27, x0 + lw, ry + 27 + BAR_H], radius=2, fill=LARGE)
        d.text((x0 + lw + 7, ry + 25), f"{large:.1f}", font=f_val, fill=LARGE)

d.text((12, height - 34), "横轴为字高（像素），越短看得越细。", font=f_note, fill=MUTED)
d.text((12, height - 18), "数据：论文 Table 2，均为各模型默认设置。", font=f_note, fill=MUTED)

out = Path("drafts/assets/diag-kz-bars.png")
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out, "PNG")
print(out, img.size)
