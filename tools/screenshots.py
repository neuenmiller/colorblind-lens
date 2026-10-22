#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
"""Make docs/screenshot.png and docs/how-it-looks.png.

Runs as a driver of the headless test shell:

    DRIVER=tools/screenshots.py MONITORS=1600x1000 GPU=1 \\
        test/run-headless.sh WORKDIR
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

spec = importlib.util.spec_from_file_location('drive', sys.argv[2])
d = importlib.util.module_from_spec(spec)
sys.argv = sys.argv[:2]
spec.loader.exec_module(d)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import scene  # noqa: E402

DOCS = REPO / 'docs'
CARD = (100, 80, 1400, 840)               # x, y, width, height on screen
LENS = (CARD[0] + 560, CARD[1] + 90, CARD[0] + CARD[2] - 12, CARD[1] + CARD[3] - 12)


def caption(img, text):
    bar = Image.new('RGB', (img.width, 56), (36, 36, 40))
    ImageDraw.Draw(bar).text((24, 28), text, font=scene.font(26, True),
                             fill=(255, 255, 255), anchor='lm')
    return np.concatenate([np.asarray(bar), np.asarray(img)])


def main():
    d.wait_for_shell()
    d.js('''
        Main.overview.hide();
        Main.messageTray.bannerBlocked = true;
        const seat = global.stage.context.get_backend().get_default_seat();
        global._ptr = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        global._kbd = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);''')
    # GNOME opens the overview at startup; keep closing it until it stays
    # closed, so the screenshot shows a plain desktop.
    for _ in range(20):
        if not d.js('if (Main.overview.visible) Main.overview.hide(); return Main.overview.visible;'):
            break
        d.settle(0.5)
    d.settle(1.0)
    d.pointer(800, 500)
    d.pointer(800, 500)

    # A plain desktop: distribution wallpapers carry their own licences.
    d.js('''const Gio = (await import('gi://Gio')).default;
        const bg = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
        bg.set_string('picture-options', 'none');
        bg.set_string('color-shading-type', 'vertical');
        bg.set_string('primary-color', '#3a4a5c');
        bg.set_string('secondary-color', '#1f2833');''')
    d.settle(0.5)

    plate = d.ROOT / 'plate.png'
    d.make_plate(plate, 'deutan')
    board = d.ROOT / 'dashboard.png'
    scene.dashboard(plate, CARD[2:]).save(board)
    x, y, w, h = CARD
    d.js(f'''
        const card = new St.Widget({{x: {x}, y: {y}, width: {w}, height: {h},
            style: 'background-image: url("file://{board}");'
                 + 'box-shadow: 0 6px 24px rgba(0,0,0,0.35);'}});
        Main.uiGroup.add_child(card);''')
    d.settle(0.5)

    d.shortcut()
    d.drag(*LENS)
    d.pointer(60, 960)
    for _ in range(20):
        if not d.js('if (Main.overview.visible) Main.overview.hide(); return Main.overview.visible;'):
            break
        d.settle(0.5)
    d.settle(0.6)
    shot = d.screenshot('desktop')
    DOCS.mkdir(exist_ok=True)
    Image.fromarray(np.uint8(shot)).save(DOCS / 'screenshot.png')

    crop = np.uint8(shot[y - 50:y + h, x:x + w])
    rows = [caption(Image.fromarray(crop), 'As you see it')]
    for cvd, name in (('deutan', 'green-weak (deutan)'), ('protan', 'red-weak (protan)')):
        sim = np.uint8(np.round(d.simulate(crop / 255, cvd) * 255))
        rows.append(caption(Image.fromarray(sim), f'As a {name} eye sees it'))
    gap = np.full((16, w, 3), 255, np.uint8)
    out = np.concatenate([rows[0], gap, rows[1], gap, rows[2]])
    img = Image.fromarray(out)
    img = img.resize((1000, round(img.height * 1000 / img.width)), Image.LANCZOS)
    img.save(DOCS / 'how-it-looks.png', optimize=True)
    print('wrote', DOCS / 'screenshot.png', 'and', DOCS / 'how-it-looks.png')


main()
