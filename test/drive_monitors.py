#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
"""Multi-monitor checks, run by run-headless.sh with
DRIVER=test/drive_monitors.py MONITORS="1920x1080 2560x1440 1920x1080".

Arranges the virtual monitors like a real three-monitor desk: a small monitor on the
left and lower, the primary in the middle, a third monitor on the right
and a little lower. The stage is the bounding box of all three, so parts
of it are on no monitor. Checks that lenses and their toolbar stay on
real monitors and that the picture through a lens is right on each one.
"""
import importlib.util
import sys

import numpy as np
from gi.repository import GLib

spec = importlib.util.spec_from_file_location('drive', sys.argv[2])
d = importlib.util.module_from_spec(spec)
sys.argv = sys.argv[:2]
spec.loader.exec_module(d)

LAYOUT = [  # (x, y, primary) per virtual monitor, in connector order
    (0, 804, False),
    (1920, 0, True),
    (4480, 140, False),
]
RED = (220, 40, 40)


def arrange():
    dc = ('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
          'org.gnome.Mutter.DisplayConfig')
    serial, monitors, _, _ = d.bus.call_sync(*dc, 'GetCurrentState', None, None,
                                             0, 5000, None).unpack()
    logical = []
    for ((conn, *_), modes, _), (x, y, primary) in zip(monitors, LAYOUT):
        mode = next(m[0] for m in modes if m[6].get('is-current'))
        logical.append((x, y, 1.0, 0, primary, [(conn, mode, {})]))
    d.bus.call_sync(*dc, 'ApplyMonitorsConfig',
                    GLib.Variant('(uua(iiduba(ssa{sv}))a{sv})',
                                 (serial, 1, logical, {})),
                    None, 0, 5000, None)


def inside(box, m):
    x, y, w, h = box
    mx, my, mw, mh = m
    return x >= mx and y >= my and x + w <= mx + mw and y + h <= my + mh


def toolbar_box():
    return d.js('''const t = ext._lens._toolbar;
        const [x, y] = t.get_transformed_position();
        const [w, h] = t.get_transformed_size();
        return [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];''')


def lens_box():
    r = d.lens_rect()
    return [r['x'], r['y'], r['width'], r['height']]


def goto(x, y, monitors):
    """Move the virtual pointer via the target monitor's centre, so it
    never travels through the gaps between monitors."""
    mx, my, mw, mh = next(m for m in monitors if inside([x, y, 0, 0], m))
    d.pointer(mx + mw // 2, my + mh // 2)
    d.pointer(x, y)


def main():
    d.wait_for_shell()
    arrange()
    d.settle(1.5)
    monitors = d.js('return Main.layoutManager.monitors.map(m => [m.x, m.y, m.width, m.height]);')
    d.js('''
        Main.overview.hide();
        Main.messageTray.bannerBlocked = true;
        const seat = global.stage.context.get_backend().get_default_seat();
        global._ptr = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        global._kbd = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);''')
    d.settle(1.0)
    d.pointer(2500, 600)
    d.pointer(2500, 600)
    d.js(f'''
        const scene = new St.Widget({{x: 0, y: 0}});
        for (const m of Main.layoutManager.monitors)
            scene.add_child(new St.Widget({{x: m.x + 200, y: m.y + 100,
                width: 400, height: 300,
                style: 'background-color: rgb({RED[0]},{RED[1]},{RED[2]});'}}));
        Main.uiGroup.add_child(scene);''')
    d.settle(0.5)
    want = d.lens_formula(RED, 'strong', 1.0)

    # A lens against the top edge of each monitor: no room above it, so
    # the toolbar must go below it, still on the same monitor.
    for i, m in enumerate(monitors):
        mx, my, mw, mh = m
        d.shortcut()
        goto(mx + 150, my + 20, monitors)
        d.drag(mx + 150, my + 20, mx + 650, my + 420)
        d.settle(0.4)
        shot = d.screenshot(f'monitor-{i}')
        cx, cy = mx + 400, my + 250
        got = shot[cy - 3:cy + 4, cx - 3:cx + 4].reshape(-1, 3).mean(0)
        d.check(f'monitor {i}: lens recolours what is under it',
                float(np.abs(got - want).max()) <= 3, f'got {got.round()}, want {want}')
        d.check(f'monitor {i}: lens is on the monitor', inside(lens_box(), m),
                f'lens {lens_box()}, monitor {m}')
        d.check(f'monitor {i}: toolbar is on the same monitor',
                inside(toolbar_box(), m), f'toolbar {toolbar_box()}, monitor {m}')
        d.shortcut()

    # Drawing from the primary into the right monitor stops at the edge
    # of the primary.
    primary, right = monitors[1], monitors[2]
    edge = primary[0] + primary[2]
    d.shortcut()
    goto(edge - 300, 500, monitors)
    d.drag(edge - 300, 500, edge + 400, 900)
    d.check('a drawn lens stays on the monitor where the drag began',
            inside(lens_box(), primary), f'lens {lens_box()}')

    # Dragging the toolbar onto the right monitor moves the lens there.
    tx, ty, tw, th = toolbar_box()
    gx, gy = tx + 12, ty + th // 2
    goto(gx, gy, monitors)
    d.drag(gx, gy, right[0] + 600, right[1] + 300, steps=16)
    d.settle(0.3)
    d.check('dragging the toolbar carries the lens onto another monitor',
            inside(lens_box(), right), f'lens {lens_box()}, monitor {right}')
    d.check('its toolbar comes along onto that monitor',
            inside(toolbar_box(), right), f'toolbar {toolbar_box()}')
    d.shortcut()

    log = (d.ROOT / 'shell.log').read_text(errors='replace')
    bad = [line for line in log.splitlines() if 'JS ERROR' in line]
    d.check('no JS errors in the shell log', not bad, '; '.join(bad[:3]))

    print(f'\n{len(d.failures)} failure(s)' if d.failures else '\nall checks passed')
    sys.exit(1 if d.failures else 0)


main()
