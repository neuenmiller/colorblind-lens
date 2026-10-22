// SPDX-License-Identifier: GPL-2.0-or-later
// SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {MIN_SIZE, clamp, monitorAt, scaled} from './lens.js';

// Size of the lens made by a click without a drag.
const CLICK_WIDTH = 480;
const CLICK_HEIGHT = 320;

/**
 * Full-screen modal layer for drawing a lens, like the area mode of the
 * screenshot UI. It dims the screen and reports the rectangle as the
 * pointer drags; the lens itself is drawn above it by the caller.
 *
 * 'finished' carries 'drawn', 'reuse' (Enter: bring back the last lens)
 * or 'cancel' (Escape or right click).
 */
export const LensSelector = GObject.registerClass({
    Signals: {
        'area-changed': {
            param_types: [GObject.TYPE_INT, GObject.TYPE_INT,
                GObject.TYPE_INT, GObject.TYPE_INT],
        },
        'finished': {param_types: [GObject.TYPE_STRING]},
    },
}, class LensSelector extends St.Widget {
    _init() {
        super._init({
            style_class: 'colorblind-lens-selector',
            reactive: true,
            can_focus: true,
        });
        this.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.SIZE,
        }));

        this._hint = new St.Label({
            style_class: 'colorblind-lens-hint',
            text: 'Drag to draw a lens  ·  Enter brings back the last one  ·  Esc cancels',
        });
        this.add_child(this._hint);

        this._start = null;
        this._grab = null;
    }

    open() {
        global.stage.add_child(this);
        this._grab = Main.pushModal(this, {actionMode: Shell.ActionMode.POPUP});
        this.grab_key_focus();
        this.set_cursor_type(Clutter.CursorType.CROSSHAIR);

        const [pointerX, pointerY] = global.get_pointer();
        const monitor = monitorAt(pointerX, pointerY);
        const [, width] = this._hint.get_preferred_width(-1);
        const [, height] = this._hint.get_preferred_height(width);
        this._hint.set_position(
            Math.round(monitor.x + (monitor.width - width) / 2),
            Math.round(monitor.y + (monitor.height - height) / 2));
    }

    close() {
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        this.destroy();
    }

    // The rectangle from the press to (px, py), kept on the monitor where
    // the drag started.
    _area(px, py) {
        const [sx, sy] = this._start;
        const m = this._startMonitor;
        px = clamp(px, m.x, m.x + m.width);
        py = clamp(py, m.y, m.y + m.height);
        return [
            Math.min(sx, px), Math.min(sy, py),
            Math.abs(px - sx), Math.abs(py - sy),
        ];
    }

    vfunc_button_press_event(event) {
        const button = event.get_button();
        if (button === Clutter.BUTTON_SECONDARY) {
            this.emit('finished', 'cancel');
            return Clutter.EVENT_STOP;
        }
        if (button !== Clutter.BUTTON_PRIMARY || this._start)
            return Clutter.EVENT_PROPAGATE;

        this._start = event.get_coords().map(Math.round);
        this._startMonitor = monitorAt(...this._start);
        this._hint.hide();
        return Clutter.EVENT_STOP;
    }

    vfunc_motion_event(event) {
        if (!this._start)
            return Clutter.EVENT_PROPAGATE;

        const [px, py] = event.get_coords().map(Math.round);
        this.emit('area-changed', ...this._area(px, py));
        return Clutter.EVENT_STOP;
    }

    vfunc_button_release_event(event) {
        if (!this._start || event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;

        const [px, py] = event.get_coords().map(Math.round);
        let [x, y, width, height] = this._area(px, py);

        // A click, or a scribble too small to look through: make a
        // comfortable lens centered on the click instead.
        const min = scaled(MIN_SIZE);
        if (width < min || height < min) {
            width = scaled(CLICK_WIDTH);
            height = scaled(CLICK_HEIGHT);
            x = px - width / 2;
            y = py - height / 2;
        }

        this.emit('area-changed', x, y, width, height);
        this.emit('finished', 'drawn');
        return Clutter.EVENT_STOP;
    }

    vfunc_key_press_event(event) {
        const key = event.get_key_symbol();
        if (key === Clutter.KEY_Escape) {
            this.emit('finished', 'cancel');
            return Clutter.EVENT_STOP;
        }
        if (!this._start && (key === Clutter.KEY_Return ||
            key === Clutter.KEY_KP_Enter || key === Clutter.KEY_space)) {
            this.emit('finished', 'reuse');
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }
});
