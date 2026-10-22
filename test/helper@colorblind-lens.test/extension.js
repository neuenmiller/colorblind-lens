// SPDX-License-Identifier: GPL-2.0-or-later
// SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon

import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Puts the throwaway test shell in unsafe mode so the test driver can use
// Eval and Screenshot over D-Bus. Unsafe mode opens the shell to any
// program, so this refuses to run anywhere but under run-headless.sh.
export default class TestHelper extends Extension {
    enable() {
        if (GLib.getenv('COLORBLIND_LENS_TEST') !== '1')
            throw new Error('This helper only runs under test/run-headless.sh');
        global.context.unsafe_mode = true;
    }

    disable() {
        global.context.unsafe_mode = false;
    }
}
