// SPDX-License-Identifier: GPL-2.0-or-later
// SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Signals from 'resource:///org/gnome/shell/misc/signals.js';

import {DEFAULT_MODE, MODES, createLensEffect} from './effect.js';

const BORDER = 2;        // outline drawn just outside the lens
const GRIP = 10;         // invisible resize zone outside each edge
const CORNER = 24;       // reach of the diagonal resize along each edge
const TOOLBAR_GAP = 4;
export const MIN_SIZE = 48;

const MODE_ORDER = Object.keys(MODES);

export function scaled(px) {
    return Math.round(px * St.ThemeContext.get_for_stage(global.stage).scaleFactor);
}

export function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(v, hi));
}

/**
 * The monitor holding a point, or the nearest one when the point falls
 * in a gap between monitors (the stage is the bounding box of all of
 * them, so with monitors of different sizes parts of it are never shown).
 */
export function monitorAt(px, py) {
    const monitors = Main.layoutManager.monitors.length
        ? Main.layoutManager.monitors
        : [{x: 0, y: 0, width: global.stage.width, height: global.stage.height}];

    let best = null;
    let bestDistance = Infinity;
    for (const {x, y, width, height} of monitors) {
        const dx = Math.max(x - px, 0, px - (x + width - 1));
        const dy = Math.max(y - py, 0, py - (y + height - 1));
        const distance = dx * dx + dy * dy;
        if (distance < bestDistance) {
            best = {x, y, width, height};
            bestDistance = distance;
        }
    }
    return best;
}

/**
 * A rectangle on the stage that shows Main.uiGroup through a color
 * correcting shader. It sits above uiGroup, so it never sees itself.
 * The inside is not reactive: clicks go through to whatever is below.
 * The frame around it moves and resizes it.
 */
export class Lens extends Signals.EventEmitter {
    constructor(settings) {
        super();

        this._settings = settings;
        this._rect = {x: 0, y: 0, width: MIN_SIZE, height: MIN_SIZE};
        this._drag = null;

        this._view = new Clutter.Actor({clip_to_allocation: true});
        this._clone = new Clutter.Clone({source: Main.uiGroup});
        this._view.add_child(this._clone);
        this._effect = createLensEffect();
        this._view.add_effect(this._effect);
        Shell.util_set_hidden_from_pick(this._view, true);

        this._outline = new St.Widget({style_class: 'colorblind-lens-outline'});
        Shell.util_set_hidden_from_pick(this._outline, true);

        this._edges = {};
        for (const side of ['top', 'bottom', 'left', 'right']) {
            const edge = new St.Widget({reactive: true});
            this._connectDrag(edge, (x, y) => this._zoneAt(side, x, y));
            this._edges[side] = edge;
        }

        this._toolbar = this._buildToolbar();
        this._connectDrag(this._toolbar, () => 'MOVE');

        this._actors = [
            this._view,
            this._outline,
            ...Object.values(this._edges),
            this._toolbar,
        ];
        for (const actor of this._actors)
            global.stage.add_child(actor);

        this._settings.connectObject(
            'changed::mode', () => this._syncSettings(),
            'changed::strength', () => this._syncSettings(),
            this);
        this._syncSettings();
        this.setChromeVisible(false);
    }

    get rect() {
        return {...this._rect};
    }

    /**
     * Places the lens, kept inside one monitor: by default the one under
     * the lens's center.
     */
    setRect(x, y, width, height,
        bounds = monitorAt(x + width / 2, y + height / 2)) {
        const min = scaled(MIN_SIZE);

        width = clamp(Math.round(width), min, bounds.width);
        height = clamp(Math.round(height), min, bounds.height);
        x = clamp(Math.round(x), bounds.x, bounds.x + bounds.width - width);
        y = clamp(Math.round(y), bounds.y, bounds.y + bounds.height - height);
        this._rect = {x, y, width, height};

        this._view.set_position(x, y);
        this._view.set_size(width, height);
        this._clone.set_position(-x, -y);

        const b = scaled(BORDER);
        this._outline.set_position(x - b, y - b);
        this._outline.set_size(width + 2 * b, height + 2 * b);

        const g = scaled(GRIP);
        this._edges.top.set_position(x - g, y - g);
        this._edges.top.set_size(width + 2 * g, g);
        this._edges.bottom.set_position(x - g, y + height);
        this._edges.bottom.set_size(width + 2 * g, g);
        this._edges.left.set_position(x - g, y);
        this._edges.left.set_size(g, height);
        this._edges.right.set_position(x + width, y);
        this._edges.right.set_size(g, height);

        this._placeToolbar();
    }

    saveArea() {
        const {x, y, width, height} = this._rect;
        this._settings.set_value('last-area',
            new GLib.Variant('ai', [x, y, width, height]));
    }

    setChromeVisible(visible) {
        for (const edge of Object.values(this._edges))
            edge.visible = visible;
        this._toolbar.visible = visible;
    }

    destroy() {
        this._endDrag();
        this._settings.disconnectObject(this);
        for (const actor of this._actors)
            actor.destroy();
        this._actors = [];
    }

    _buildToolbar() {
        const toolbar = new St.BoxLayout({
            style_class: 'colorblind-lens-toolbar',
            reactive: true,
        });

        toolbar.add_child(new St.Icon({
            style_class: 'colorblind-lens-grip',
            icon_name: 'list-drag-handle-symbolic',
        }));

        this._modeButton = new St.Button({
            style_class: 'colorblind-lens-button',
            label: '',
        });
        this._modeButton.connect('clicked', () => this._cycleMode());
        toolbar.add_child(this._modeButton);

        this._strengthLabel = new St.Label({
            style_class: 'colorblind-lens-strength',
            y_align: Clutter.ActorAlign.CENTER,
        });
        toolbar.add_child(this._strengthLabel);

        const closeButton = new St.Button({
            style_class: 'colorblind-lens-button colorblind-lens-close',
            child: new St.Icon({icon_name: 'window-close-symbolic'}),
        });
        closeButton.connect('clicked', () => this.emit('close-requested'));
        toolbar.add_child(closeButton);

        // Scroll anywhere on the toolbar to change strength in 10% steps.
        // Smooth scrolling also arrives as emulated discrete steps.
        toolbar.connect('scroll-event', (actor, event) => {
            const direction = event.get_scroll_direction();
            let step = 0;
            if (direction === Clutter.ScrollDirection.UP)
                step = 0.1;
            else if (direction === Clutter.ScrollDirection.DOWN)
                step = -0.1;
            if (step !== 0) {
                const strength = this._settings.get_double('strength');
                this._settings.set_double('strength',
                    clamp(Math.round((strength + step) * 10) / 10, 0, 2));
            }
            return Clutter.EVENT_STOP;
        });

        return toolbar;
    }

    _placeToolbar() {
        const [, width] = this._toolbar.get_preferred_width(-1);
        const [, height] = this._toolbar.get_preferred_height(width);
        const {x, y, width: w, height: h} = this._rect;
        const m = monitorAt(x + w / 2, y + h / 2);
        const b = scaled(BORDER);
        const gap = scaled(TOOLBAR_GAP);

        // Above the lens if that is still on its monitor, else below it,
        // else inside its top edge.
        let ty = y - b - gap - height;
        if (ty < m.y)
            ty = y + h + b + gap;
        if (ty + height > m.y + m.height)
            ty = y + gap;

        const tx = clamp(x - b, m.x, m.x + m.width - width);
        this._toolbar.set_position(tx, ty);
    }

    _syncSettings() {
        const mode = this._settings.get_string('mode');
        const strength = this._settings.get_double('strength');
        this._effect.configure(mode, strength);
        this._modeButton.label = (MODES[mode] ?? MODES[DEFAULT_MODE]).short;
        this._strengthLabel.text = `${Math.round(strength * 100)}%`;
        this._placeToolbar();
    }

    _cycleMode() {
        const current = MODE_ORDER.indexOf(this._settings.get_string('mode'));
        const next = MODE_ORDER[(current + 1) % MODE_ORDER.length];
        this._settings.set_string('mode', next);
    }

    _zoneAt(side, px, py) {
        const {x, y, width, height} = this._rect;
        const c = scaled(CORNER);

        let ns = '';
        let we = '';
        if (side === 'top')
            ns = 'N';
        else if (side === 'bottom')
            ns = 'S';
        else if (py < y + c)
            ns = 'N';
        else if (py >= y + height - c)
            ns = 'S';

        if (side === 'left')
            we = 'W';
        else if (side === 'right')
            we = 'E';
        else if (px < x + c)
            we = 'W';
        else if (px >= x + width - c)
            we = 'E';

        return `${ns}${we}`;
    }

    _cursorFor(zone) {
        return zone === 'MOVE'
            ? Clutter.CursorType.MOVE
            : Clutter.CursorType[`${zone}_RESIZE`];
    }

    _connectDrag(actor, zoneAt) {
        actor.connect('button-press-event', (a, event) => {
            if (this._drag || event.get_button() !== Clutter.BUTTON_PRIMARY)
                return Clutter.EVENT_PROPAGATE;

            // Buttons on the toolbar let presses bubble up; a grab here
            // would cancel their click.
            const target = global.stage.get_event_actor(event);
            for (let p = target; p && p !== a; p = p.get_parent()) {
                if (p instanceof St.Button)
                    return Clutter.EVENT_PROPAGATE;
            }

            const [x, y] = event.get_coords();
            const zone = zoneAt(x, y);
            const {x: rx, y: ry, width: rw, height: rh} = this._rect;
            this._drag = {
                actor: a,
                zone,
                startX: x,
                startY: y,
                rect: {...this._rect},
                bounds: monitorAt(rx + rw / 2, ry + rh / 2),
                grab: global.stage.grab(a),
            };
            a.set_cursor_type(this._cursorFor(zone));
            return Clutter.EVENT_STOP;
        });

        actor.connect('motion-event', (a, event) => {
            const [x, y] = event.get_coords();
            if (this._drag?.actor === a) {
                this._dragTo(x, y);
                return Clutter.EVENT_STOP;
            }
            if (!this._drag)
                a.set_cursor_type(this._cursorFor(zoneAt(x, y)));
            return Clutter.EVENT_PROPAGATE;
        });

        actor.connect('button-release-event', (a, event) => {
            if (this._drag?.actor !== a ||
                event.get_button() !== Clutter.BUTTON_PRIMARY)
                return Clutter.EVENT_PROPAGATE;

            this._endDrag();
            this.saveArea();
            return Clutter.EVENT_STOP;
        });

        actor.connect('leave-event', a => {
            if (!this._drag)
                a.set_cursor_type(Clutter.CursorType.INHERIT);
            return Clutter.EVENT_PROPAGATE;
        });
    }

    _dragTo(px, py) {
        const {zone, startX, startY, rect, bounds: b} = this._drag;
        const dx = px - startX;
        const dy = py - startY;
        const min = scaled(MIN_SIZE);

        // Moving follows the pointer onto whichever monitor it is on.
        if (zone === 'MOVE') {
            this.setRect(rect.x + dx, rect.y + dy, rect.width, rect.height,
                monitorAt(px, py));
            return;
        }

        let left = rect.x;
        let top = rect.y;
        let right = rect.x + rect.width;
        let bottom = rect.y + rect.height;

        if (zone.includes('N'))
            top = clamp(top + dy, b.y, bottom - min);
        if (zone.includes('S'))
            bottom = clamp(bottom + dy, top + min, b.y + b.height);
        if (zone.includes('W'))
            left = clamp(left + dx, b.x, right - min);
        if (zone.includes('E'))
            right = clamp(right + dx, left + min, b.x + b.width);

        this.setRect(left, top, right - left, bottom - top, b);
    }

    _endDrag() {
        if (!this._drag)
            return;
        this._drag.grab.dismiss();
        this._drag.actor.set_cursor_type(Clutter.CursorType.INHERIT);
        this._drag = null;
    }
}
