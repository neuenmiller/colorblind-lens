// SPDX-License-Identifier: GPL-2.0-or-later
// SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon

import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {QuickMenuToggle, SystemIndicator} from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Slider} from 'resource:///org/gnome/shell/ui/slider.js';

import {DEFAULT_MODE, MODES} from './effect.js';
import {Lens} from './lens.js';
import {LensSelector} from './selector.js';

const ICON = 'view-reveal-symbolic';

const LensToggle = GObject.registerClass(
class LensToggle extends QuickMenuToggle {
    _init(extension) {
        super._init({
            title: 'Colorblind Lens',
            iconName: ICON,
            toggleMode: false,
        });

        this._settings = extension.settings;
        this.menu.setHeader(ICON, 'Colorblind Lens', 'Super+Shift+C draws or closes a lens');

        this._modeItems = new Map();
        for (const [key, mode] of Object.entries(MODES)) {
            const item = new PopupMenu.PopupMenuItem(mode.label);
            item.connect('activate', () => this._settings.set_string('mode', key));
            this.menu.addMenuItem(item);
            this._modeItems.set(key, item);
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem('Strength'));
        const sliderItem = new PopupMenu.PopupBaseMenuItem({activate: false});
        this._slider = new Slider(0);
        this._slider.x_expand = true;
        this._slider.connect('notify::value', () => {
            const strength = Math.round(this._slider.value * 20) / 10;
            if (strength !== this._settings.get_double('strength'))
                this._settings.set_double('strength', strength);
        });
        sliderItem.add_child(this._slider);
        this.menu.addMenuItem(sliderItem);

        this.connect('clicked', () => extension.toggle());
        this._settings.connectObject(
            'changed::mode', () => this._sync(),
            'changed::strength', () => this._sync(),
            this);
        this._sync();
    }

    _sync() {
        const mode = this._settings.get_string('mode');
        const strength = this._settings.get_double('strength');
        for (const [key, item] of this._modeItems) {
            item.setOrnament(key === mode
                ? PopupMenu.Ornament.CHECK : PopupMenu.Ornament.NONE);
        }
        this.subtitle = `${(MODES[mode] ?? MODES[DEFAULT_MODE]).short} · ${Math.round(strength * 100)}%`;
        if (Math.abs(this._slider.value - strength / 2) > 0.03)
            this._slider.value = strength / 2;
    }
});

const LensIndicator = GObject.registerClass(
class LensIndicator extends SystemIndicator {
    _init(extension) {
        super._init();

        this._icon = this._addIndicator();
        this._icon.icon_name = ICON;
        this._icon.visible = false;

        this.toggle = new LensToggle(extension);
        this.quickSettingsItems.push(this.toggle);
    }

    setActive(active) {
        this._icon.visible = active;
        this.toggle.checked = active;
    }

    destroy() {
        this.quickSettingsItems.forEach(item => item.destroy());
        super.destroy();
    }
});

export default class ColorblindLensExtension extends Extension {
    enable() {
        this.settings = this.getSettings();
        this._lens = null;
        this._selector = null;
        this._startId = 0;

        this._indicator = new LensIndicator(this);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);

        Main.wm.addKeybinding('toggle-lens', this.settings,
            Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this.toggle());

        // Locking the screen disables extensions; bring back a lens that
        // was open when the screen locked.
        if (this._areaBeforeLock) {
            const {x, y, width, height} = this._areaBeforeLock;
            this._areaBeforeLock = null;
            this._ensureLens().setRect(x, y, width, height);
            this._lens.setChromeVisible(true);
            this._indicator.setActive(true);
        }
    }

    disable() {
        Main.wm.removeKeybinding('toggle-lens');
        if (this._startId) {
            GLib.Source.remove(this._startId);
            this._startId = 0;
        }
        this._areaBeforeLock = Main.sessionMode.isLocked && this._lens
            ? this._lens.rect : null;
        this.close();
        this._indicator.destroy();
        this._indicator = null;
        this.settings = null;
    }

    toggle() {
        if (this._lens || this._selector) {
            this.close();
            return;
        }
        if (this._startId)
            return;

        // Let the quick settings menu drop its grab before the selector
        // takes one of its own.
        Main.panel.closeQuickSettings();
        this._startId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._startId = 0;
            this._startSelection();
            return GLib.SOURCE_REMOVE;
        });
    }

    close() {
        this._selector?.close();
        this._selector = null;
        this._lens?.destroy();
        this._lens = null;
        this._indicator?.setActive(false);
    }

    _ensureLens() {
        if (!this._lens) {
            this._lens = new Lens(this.settings);
            this._lens.connect('close-requested', () => this.close());
        }
        return this._lens;
    }

    _startSelection() {
        if (this._lens || this._selector)
            return;

        const selector = new LensSelector();
        selector.connect('area-changed', (s, x, y, width, height) => {
            this._ensureLens().setRect(x, y, width, height);
        });
        selector.connect('finished', (s, how) => this._finishSelection(how));
        this._selector = selector;
        this._indicator.setActive(true);
        selector.open();
    }

    _finishSelection(how) {
        this._selector?.close();
        this._selector = null;

        if (how === 'reuse') {
            const last = this.settings.get_value('last-area').deepUnpack();
            if (last.length === 4)
                this._ensureLens().setRect(...last);
        }

        if (how === 'cancel' || !this._lens) {
            this.close();
            return;
        }

        this._lens.setChromeVisible(true);
        this._lens.saveArea();
        this._indicator.setActive(true);
    }
}
