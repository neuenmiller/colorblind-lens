#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
"""Drive Colorblind Lens in a headless GNOME Shell and check what it shows.

Started by run-headless.sh inside a private D-Bus session. Puts colour
blocks and two pseudo-Ishihara plates on screen, draws a lens over half
of them with a virtual mouse, and checks:
  - pixels inside the lens match the shader formula, pixels outside are
    untouched;
  - under simulated deutan vision the plate's number is invisible
    outside the lens and visible inside it;
  - click-through, move, resize, mode cycling, close, the keyboard
    shortcut, Enter-to-reuse, Escape-to-cancel, and disable/enable.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from gi.repository import Gio, GLib
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(sys.argv[1])
SHOTS = ROOT / 'shots'
UUID = 'colorblind-lens@thamk.me'
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
failures = []


# ---------------------------------------------------------------- shell io

PRELUDE = """
const Clutter = (await import('gi://Clutter')).default;
const GLib = (await import('gi://GLib')).default;
const St = (await import('gi://St')).default;
const Main = await import('resource:///org/gnome/shell/ui/main.js');
const ext = Main.extensionManager.lookup('%s')?.stateObj;
""" % UUID


def js(body, timeout=10000):
    code = '(async () => {' + PRELUDE + body + '\n})()'
    res = bus.call_sync('org.gnome.Shell', '/org/gnome/Shell',
                        'org.gnome.Shell', 'Eval',
                        GLib.Variant('(s)', (code,)),
                        GLib.VariantType('(bs)'), 0, timeout, None)
    ok, out = res.unpack()
    if not ok:
        raise RuntimeError(f'JS failed: {out}\n--- code:\n{body}')
    return json.loads(out) if out else None


def settle(seconds=0.15):
    time.sleep(seconds)


def wait_for_shell():
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if js('return !Main.layoutManager._startingUp && !!ext;'):
                return
        except Exception:
            pass
        time.sleep(0.5)
    sys.exit('shell did not come up; see shell.log')


def screenshot(name):
    path = str(SHOTS / f'{name}.png')
    bus.call_sync('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                  'org.gnome.Shell.Screenshot', 'Screenshot',
                  GLib.Variant('(bbs)', (False, False, path)),
                  GLib.VariantType('(bs)'), 0, 10000, None)
    return np.asarray(Image.open(path).convert('RGB')).astype(float)


def pointer(x, y):
    js(f'global._ptr.notify_absolute_motion(GLib.get_monotonic_time(), {x}, {y});')
    settle(0.03)


def button(pressed, which='PRIMARY'):
    state = 'PRESSED' if pressed else 'RELEASED'
    js(f'global._ptr.notify_button(GLib.get_monotonic_time(), '
       f'Clutter.BUTTON_{which}, Clutter.ButtonState.{state});')
    settle(0.05)


def drag(x0, y0, x1, y1, steps=8):
    pointer(x0, y0)
    button(True)
    for i in range(1, steps + 1):
        pointer(round(x0 + (x1 - x0) * i / steps),
                round(y0 + (y1 - y0) * i / steps))
    button(False)
    settle()


def click(x, y):
    pointer(x, y)
    button(True)
    button(False)
    settle()


def keys(*names):
    """Press names in order, release in reverse: keys('Super_L', 'c')."""
    for n in names:
        js(f'global._kbd.notify_keyval(GLib.get_monotonic_time(), '
           f'Clutter.KEY_{n}, Clutter.KeyState.PRESSED);')
    for n in reversed(names):
        js(f'global._kbd.notify_keyval(GLib.get_monotonic_time(), '
           f'Clutter.KEY_{n}, Clutter.KeyState.RELEASED);')
    settle(0.3)


def shortcut():
    keys('Super_L', 'Shift_L', 'c')


def lens_rect():
    return js('return ext._lens ? ext._lens.rect : null;')


def widget_center(path):
    return js(f'''
        const a = {path};
        const [x, y] = a.get_transformed_position();
        const [w, h] = a.get_transformed_size();
        return [Math.round(x + w / 2), Math.round(y + h / 2)];''')


def check(name, ok, detail=''):
    print(f'{"PASS" if ok else "FAIL"}  {name}' + (f'  ({detail})' if detail else ''))
    if not ok:
        failures.append(name)


# ------------------------------------------------------- colour reference

SIM = {
    'protan': np.array([[0.11238, 0.88762, 0.0],
                        [0.11238, 0.88762, 0.0],
                        [0.00401, -0.00401, 1.0]]),
    'deutan': np.array([[0.29275, 0.70725, 0.0],
                        [0.29275, 0.70725, 0.0],
                        [-0.02234, 0.02234, 1.0]]),
}
SHIFT = np.array([[0.0, 0.0, 0.0], [0.7, 1.0, 0.0], [0.7, 0.0, 1.0]])


def to_linear(c):
    return np.where(c < 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c < 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def simulate(img01, cvd):
    """Viénot dichromat simulation of an (..., 3) sRGB array in 0..1."""
    return to_srgb(np.clip(to_linear(img01) @ SIM[cvd].T, 0, 1))


def lens_formula(rgb8, mode, strength):
    c = np.asarray(rgb8, float) / 255
    if mode == 'strong':
        r, g, b = c
        d = strength * (r - g)
        pos, neg = max(d, 0), max(-d, 0)
        b2 = (1 - (1 - b) * np.exp(-3 * pos)) * np.exp(-neg)
        g2 = g * np.exp(-1.5 * pos * b)
        dark = 0.3 + 0.7 * np.exp(-1.5 * neg / 0.7)
        return np.round(np.clip([r * dark, g2 * dark, b2], 0, 1) * 255)
    seen = simulate(c, mode.split('-')[0])
    if mode.endswith('-sim'):
        out = c + (seen - c) * min(strength, 1)
    else:
        out = c + strength * (SHIFT @ (c - seen))
    return np.round(np.clip(out, 0, 1) * 255)


def to_lab(srgb01):
    lin = to_linear(srgb01)
    xyz = lin @ np.array([[0.4124, 0.3576, 0.1805],
                          [0.2126, 0.7152, 0.0722],
                          [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


# ------------------------------------------------------------ test scene

PLATE = 400
PLATE_A = (150, 200)   # stays outside the lens
PLATE_B = (730, 200)   # goes under the lens
BLOCK_Y, BLOCK_H, BLOCK_W = 650, 100, 150
BLOCKS = [  # (sRGB, inside lens?)
    ((40, 90, 220), False), ((200, 60, 200), False),
    ((128, 128, 128), False), ((150, 30, 30), False),
    ((220, 40, 40), True), ((40, 180, 60), True),
    ((128, 140, 50), True), ((250, 250, 250), True),
]
LENS_DRAG = (700, 170, 1265, 785)


def block_center(i):
    return 10 + 160 * i + BLOCK_W // 2, BLOCK_Y + BLOCK_H // 2


def make_plate(path, cvd):
    """Pseudo-isochromatic plate: a '5' whose dots differ from the
    background only along the confusion line of `cvd`, so simulating
    that eye erases it. The dot layout does not depend on `cvd`.
    Returns a label map: 1 = background dot, 2 = figure dot, 0 = paper."""
    rng = np.random.default_rng(7)
    font_file = subprocess.run(['fc-match', '-f', '%{file}', 'sans:bold'],
                               capture_output=True, text=True).stdout
    mask = Image.new('L', (PLATE, PLATE), 0)
    ImageDraw.Draw(mask).text((PLATE / 2, PLATE / 2), '5', fill=255,
                              font=ImageFont.truetype(font_file, 300),
                              anchor='mm')
    mask = np.asarray(mask) > 127

    # Null vector of the simulation matrix: moving along it changes
    # nothing that eye sees.
    null = np.linalg.svd(SIM[cvd])[2][-1]
    null = null / null[0]
    base = np.array([0.22, 0.27, 0.07])

    img = Image.new('RGB', (PLATE, PLATE), (245, 242, 235))
    labels = Image.new('L', (PLATE, PLATE), 0)
    draw, ldraw = ImageDraw.Draw(img), ImageDraw.Draw(labels)
    placed = []
    cx = cy = PLATE / 2
    for _ in range(20000):
        r = rng.uniform(4, 11)
        x, y = rng.uniform(0, PLATE, 2)
        if (x - cx) ** 2 + (y - cy) ** 2 > (PLATE / 2 - r - 2) ** 2:
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < (r + pr + 1.5) ** 2
               for px, py, pr in placed):
            continue
        placed.append((x, y, r))
        figure = mask[int(y), int(x)]
        lin = base + (0.22 * null if figure else 0)
        lin = lin * rng.uniform(0.7, 1.25)
        rgb = tuple(int(v) for v in np.round(to_srgb(lin) * 255))
        box = (x - r, y - r, x + r, y + r)
        draw.ellipse(box, fill=rgb)
        ldraw.ellipse(box, fill=2 if figure else 1)
    img.save(path)
    return np.asarray(labels)


def show_plate(path):
    js(f'''for (const p of global._plates)
        p.style = 'background-image: url("file://{path}");';''')
    settle(0.3)


def plate_delta_e(sim01, origin, labels):
    x, y = origin
    region = sim01[y:y + PLATE, x:x + PLATE]
    lab = to_lab(region)
    fig = lab[labels == 2].mean(0)
    bg = lab[labels == 1].mean(0)
    return float(np.linalg.norm(fig - bg))


def check_blocks(shot, mode, strength, label):
    worst = 0
    for i, (rgb, inside) in enumerate(BLOCKS):
        x, y = block_center(i)
        got = shot[y - 4:y + 5, x - 4:x + 5].reshape(-1, 3).mean(0)
        want = lens_formula(rgb, mode, strength) if inside else np.array(rgb)
        worst = max(worst, float(np.abs(got - want).max()))
    check(f'{label}: blocks match the shader formula', worst <= 3,
          f'worst channel error {worst:.1f}/255')


# ------------------------------------------------------------------ tests

def main():
    wait_for_shell()
    js('''
        Main.overview.hide();
        const seat = global.stage.context.get_backend().get_default_seat();
        global._ptr = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        global._kbd = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        Main.messageTray.bannerBlocked = true;''')
    settle(1.0)
    # A new virtual pointer sits at (0, 0); its first move gets caught on
    # the hot-corner barrier. Park it mid-screen before anything else.
    pointer(640, 400)
    pointer(640, 400)

    plates = {cvd: ROOT / f'plate-{cvd}.png' for cvd in SIM}
    labels = make_plate(plates['deutan'], 'deutan')
    make_plate(plates['protan'], 'protan')
    plate_png = plates['deutan']
    blocks_js = ','.join(f'[{i}, {r}, {g}, {b}]'
                         for i, ((r, g, b), _) in enumerate(BLOCKS))
    js(f'''
        const scene = new St.Widget({{x: 0, y: 0}});
        scene.add_child(new St.Widget({{style: 'background-color: rgb(245,242,235);',
            x: 0, y: 150, width: 1280, height: 650}}));
        global._plates = [];
        for (const [x, y] of [[{PLATE_A[0]}, {PLATE_A[1]}], [{PLATE_B[0]}, {PLATE_B[1]}]]) {{
            const plate = new St.Widget({{x, y, width: {PLATE}, height: {PLATE},
                style: 'background-image: url("file://{plate_png}");'}});
            global._plates.push(plate);
            scene.add_child(plate);
        }}
        for (const [i, r, g, b] of [{blocks_js}])
            scene.add_child(new St.Widget({{x: 10 + 160 * i, y: {BLOCK_Y},
                width: {BLOCK_W}, height: {BLOCK_H},
                style: `background-color: rgb(${{r}},${{g}},${{b}});`}}));
        global._probeClicks = 0;
        const probe = new St.Button({{x: 1150, y: 560, width: 80, height: 60, reactive: true,
            style: 'background-color: rgb(250,250,250);'}});
        probe.connect('clicked', () => global._probeClicks++);
        scene.add_child(probe);
        Main.uiGroup.add_child(scene);
        global._scene = scene;''')
    settle(0.5)
    baseline = js('return global.stage.get_n_children();')

    # 1. Shortcut opens the selector; dragging draws the lens.
    shortcut()
    check('Super+Shift+C opens the selector',
          js('return !!ext._selector;'))
    dim = screenshot('01-selecting')
    x, y = block_center(2)
    check('selector dims the screen',
          dim[y, x].max() < 0.7 * 128, f'grey 128 block now {dim[y, x]}')

    drag(*LENS_DRAG)
    rect = lens_rect()
    want = {'x': LENS_DRAG[0], 'y': LENS_DRAG[1],
            'width': LENS_DRAG[2] - LENS_DRAG[0],
            'height': LENS_DRAG[3] - LENS_DRAG[1]}
    check('drag draws a lens of the dragged size', rect == want, f'{rect}')
    check('selector closes after the drag', js('return ext._selector === null;'))
    check('quick settings toggle shows the lens as on',
          js('return ext._indicator.toggle.checked;'))
    settle(0.3)

    # 2. Pixels: the default strong fix, checked on a deutan plate and a
    # protan plate.
    check('the default mode is the strong fix',
          js('return ext.settings.get_string("mode");') == 'strong')
    for cvd in ('deutan', 'protan'):
        show_plate(plates[cvd])
        shot = screenshot(f'02-strong-{cvd}-plate')
        if cvd == 'deutan':
            check_blocks(shot, 'strong', 1.0, 'strong 100%')
        sim = simulate(shot / 255, cvd)
        de_a = plate_delta_e(sim, PLATE_A, labels)
        de_b = plate_delta_e(sim, PLATE_B, labels)
        check(f'{cvd} eyes cannot see the {cvd} plate number outside the lens',
              de_a < 3, f'ΔE figure vs background {de_a:.1f}')
        check(f'{cvd} eyes see it clearly through the strong lens', de_b > 20,
              f'ΔE figure vs background {de_b:.1f}')
    de_normal = plate_delta_e(shot / 255, PLATE_A, labels)
    print(f'      (for scale: normal eyes see ΔE {de_normal:.1f} on the plain plate)')
    show_plate(plates['deutan'])

    # 3. Clicks inside the lens reach what is underneath.
    click(1190, 590)
    check('clicks pass through the lens', js('return global._probeClicks;') == 1)

    # 4. Mode button cycles strong -> deutan (the gentle fix).
    click(*widget_center('ext._lens._modeButton'))
    check('mode button switches to the deutan fix',
          js('return ext.settings.get_string("mode");') == 'deutan')
    settle(0.2)
    shot = screenshot('03-deutan')
    check_blocks(shot, 'deutan', 1.0, 'deutan 100%')
    de_b = plate_delta_e(simulate(shot / 255, 'deutan'), PLATE_B, labels)
    check('deutan eyes see the number through the gentle deutan lens',
          de_b > 10, f'ΔE figure vs background {de_b:.1f}')

    js('ext.settings.set_string("mode", "protan");')
    settle(0.2)
    check_blocks(screenshot('03-protan'), 'protan', 1.0, 'protan 100%')

    # 5. Strength and preview modes.
    js('ext.settings.set_double("strength", 2.0);')
    settle(0.2)
    check_blocks(screenshot('04-protan-200'), 'protan', 2.0, 'protan 200%')
    js('ext.settings.set_double("strength", 1.0); ext.settings.set_string("mode", "deutan-sim");')
    settle(0.2)
    check_blocks(screenshot('05-deutan-preview'), 'deutan-sim', 1.0, 'deutan preview')
    js('ext.settings.set_string("mode", "strong");')

    # 6. Scrolling on the toolbar changes strength.
    tx, ty = widget_center('ext._lens._strengthLabel')
    pointer(tx, ty)
    js('global._ptr.notify_discrete_scroll(GLib.get_monotonic_time(), '
       'Clutter.ScrollDirection.DOWN, Clutter.ScrollSource.WHEEL);')
    settle(0.2)
    strength = js('return ext.settings.get_double("strength");')
    check('scroll down on the toolbar lowers strength', abs(strength - 0.9) < 1e-6,
          f'{strength}')
    js('ext.settings.set_double("strength", 1.0);')

    # 7. Move by dragging the toolbar grip.
    before = lens_rect()
    gx, gy = widget_center('ext._lens._toolbar.get_first_child()')
    drag(gx, gy, gx - 60, gy - 30)
    after = lens_rect()
    check('dragging the toolbar moves the lens',
          (after['x'], after['y']) == (before['x'] - 60, before['y'] - 30)
          and after['width'] == before['width'],
          f'{before} -> {after}')

    # 8. Resize from the bottom-right corner and the left edge.
    r = lens_rect()
    drag(r['x'] + r['width'] + 5, r['y'] + r['height'] + 5,
         r['x'] + r['width'] - 95, r['y'] + r['height'] - 45)
    r2 = lens_rect()
    check('corner drag resizes both ways',
          (r2['width'], r2['height']) == (r['width'] - 100, r['height'] - 50)
          and (r2['x'], r2['y']) == (r['x'], r['y']), f'{r} -> {r2}')
    drag(r2['x'] - 5, r2['y'] + r2['height'] // 2, r2['x'] + 40, r2['y'] + r2['height'] // 2)
    r3 = lens_rect()
    check('left edge drag moves only the left side',
          r3['x'] == r2['x'] + 45 and r3['width'] == r2['width'] - 45
          and r3['height'] == r2['height'], f'{r2} -> {r3}')
    saved = js('return ext.settings.get_value("last-area").deepUnpack();')
    check('last lens area is saved',
          saved == [r3['x'], r3['y'], r3['width'], r3['height']], f'{saved}')

    # 9. Close button.
    click(*widget_center('ext._lens._toolbar.get_last_child()'))
    check('close button removes the lens',
          js('return ext._lens === null && !ext._indicator.toggle.checked;'))
    clean = screenshot('07-closed')
    x, y = block_center(4)
    check('screen is back to normal after closing',
          np.abs(clean[y, x] - np.array(BLOCKS[4][0])).max() <= 2, f'{clean[y, x]}')

    # 10. Enter brings back the last lens; the shortcut closes it.
    shortcut()
    keys('Return')
    check('Enter reopens the last lens', lens_rect() == r3, f'{lens_rect()}')
    shortcut()
    check('shortcut closes an open lens', js('return ext._lens === null;'))

    # 11. Escape cancels a selection; so does a right click.
    shortcut()
    keys('Escape')
    check('Escape cancels drawing',
          js('return ext._lens === null && ext._selector === null;'))
    shortcut()
    pointer(400, 400)
    button(True, 'SECONDARY')
    button(False, 'SECONDARY')
    check('right click cancels drawing',
          js('return ext._lens === null && ext._selector === null;'))

    # 12. A plain click makes a default-sized lens around the click.
    shortcut()
    click(640, 400)
    r = lens_rect()
    check('a click makes a 480x320 lens centred on it',
          r == {'x': 400, 'y': 240, 'width': 480, 'height': 320}, f'{r}')

    # 12b. Locking the screen disables extensions; unlocking brings the
    # lens back where it was.
    js('Main.sessionMode.pushMode("unlock-dialog");')
    settle(0.3)
    check('locking the screen removes the lens', js('return ext._lens === null;'))
    js('Main.sessionMode.popMode("unlock-dialog");')
    settle(0.3)
    check('unlocking brings the same lens back', lens_rect() == r, f'{lens_rect()}')

    # 13. Disable with a lens open, then enable again.
    js(f'Main.extensionManager.disableExtension("{UUID}");')
    settle(0.3)
    leftovers = js('return global.stage.get_n_children();') - baseline
    check('disabling removes every lens actor', leftovers == 0, f'{leftovers} left')
    js(f'Main.extensionManager.enableExtension("{UUID}");')
    settle(0.3)
    shortcut()
    check('works again after re-enabling', js(
        f'return !!Main.extensionManager.lookup("{UUID}").stateObj._selector;'))
    keys('Escape')

    # 14. Demo picture: normal view next to deutan view, plates only.
    js('ext.settings.set_string("mode", "strong");')
    shortcut()
    drag(*LENS_DRAG)
    settle(0.3)
    shot = screenshot('08-demo-source')
    sim = np.uint8(np.round(simulate(shot / 255, 'deutan') * 255))
    crop = (slice(140, 640), slice(120, 1280))
    top = np.uint8(shot)[crop]
    bottom = sim[crop]
    Image.fromarray(np.concatenate([top, np.full((12, top.shape[1], 3), 255, np.uint8),
                                    bottom])).save(SHOTS / 'demo.png')

    log = (ROOT / 'shell.log').read_text(errors='replace')
    bad = [line for line in log.splitlines()
           if 'JS ERROR' in line or ('colorblind-lens' in line and 'WARNING' in line)]
    check('no JS errors in the shell log', not bad, '; '.join(bad[:3]))

    print(f'\n{len(failures)} failure(s)' if failures else '\nall checks passed')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
