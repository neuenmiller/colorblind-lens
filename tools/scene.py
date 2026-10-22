# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
"""Draw a made-up dashboard full of red-green distinctions, for the
README and extensions.gnome.org screenshots."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Regular.otf'
FONT_BOLD = '/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Bold.otf'

RED = (214, 39, 40)
GREEN = (44, 160, 44)
INK = (40, 40, 46)
FAINT = (225, 225, 230)
CARD = (252, 252, 252)


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT, size)
    except OSError:
        return ImageFont.load_default(size)


def diverging(t):
    """Red -> yellow -> green, like the common RdYlGn heatmap palette."""
    stops = [(215, 48, 39), (254, 224, 139), (26, 152, 80)]
    if t < 0.5:
        a, b, u = stops[0], stops[1], t * 2
    else:
        a, b, u = stops[1], stops[2], (t - 0.5) * 2
    return tuple(round(x + (y - x) * u) for x, y in zip(a, b))


def line_chart(draw, box):
    x0, y0, x1, y1 = box
    draw.text((x0, y0 - 34), 'Orders this year', font=font(22, True), fill=INK)
    for i in range(5):
        y = y0 + (y1 - y0) * i / 4
        draw.line([(x0, y), (x1, y)], fill=FAINT, width=1)
    months = 'J F M A M J J A S O N D'.split()
    for i, m in enumerate(months):
        x = x0 + (x1 - x0) * i / 11
        draw.text((x, y1 + 10), m, font=font(15), fill=(120, 120, 128), anchor='mt')
    plan = [50 + 2.5 * i for i in range(12)]
    actual = [44, 47, 55, 58, 54, 61, 69, 66, 63, 72, 78, 74]
    for series, colour in ((plan, GREEN), (actual, RED)):
        pts = [(x0 + (x1 - x0) * i / 11, y1 - (v - 35) / 50 * (y1 - y0))
               for i, v in enumerate(series)]
        draw.line(pts, fill=colour, width=4, joint='curve')
        for x, y in pts:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=colour)
    lx = x1 - 230
    for i, (name, colour) in enumerate((('Plan', GREEN), ('Actual', RED))):
        draw.rounded_rectangle((lx + i * 120, y0 - 30, lx + i * 120 + 22, y0 - 18),
                               3, fill=colour)
        draw.text((lx + i * 120 + 30, y0 - 24), name, font=font(16), fill=INK,
                  anchor='lm')


def heatmap(draw, box):
    x0, y0, x1, y1 = box
    draw.text((x0, y0 - 34), 'Stock by store', font=font(22, True), fill=INK)
    rows, cols = 7, 9
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    for r in range(rows):
        for c in range(cols):
            t = 0.5 + 0.5 * math.sin(0.9 * c + 1.7 * r) * math.cos(0.5 * r - 0.3 * c)
            draw.rectangle((x0 + c * cw + 2, y0 + r * ch + 2,
                            x0 + (c + 1) * cw - 2, y0 + (r + 1) * ch - 2),
                           fill=diverging(t))


def status_list(draw, origin):
    x, y = origin
    draw.text((x, y - 34), 'Nightly checks', font=font(22, True), fill=INK)
    rows = [('Payments', GREEN), ('Search', RED), ('Login', GREEN),
            ('Uploads', GREEN), ('Email', RED), ('Reports', GREEN)]
    for i, (name, colour) in enumerate(rows):
        yy = y + i * 38
        draw.ellipse((x, yy + 4, x + 18, yy + 22), fill=colour)
        draw.text((x + 32, yy + 13), name, font=font(18), fill=INK, anchor='lm')


def dashboard(plate_path, size=(1400, 840)):
    """The dashboard as an RGB image; the plate goes bottom right."""
    w, h = size
    img = Image.new('RGB', size, CARD)
    draw = ImageDraw.Draw(img)
    draw.text((40, 30), 'Weekly report', font=font(30, True), fill=INK)
    line_chart(draw, (40, 140, w - 40, 420))
    status_list(draw, (40, 540))
    heatmap(draw, (300, 540, 760, 800))
    plate = Image.open(plate_path).convert('RGB').resize((300, 300), Image.LANCZOS)
    img.paste(plate, (w - 360, 500))
    return img


if __name__ == '__main__':
    import sys
    dashboard(sys.argv[1]).save(sys.argv[2])
