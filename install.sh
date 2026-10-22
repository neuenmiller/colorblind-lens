#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
# Install Colorblind Lens from this checkout for the current user and
# enable it. GNOME on Wayland only loads new extension code at login, so
# log out and back in afterwards.
set -euo pipefail

uuid=colorblind-lens@thamk.me
here=$(cd "$(dirname "$0")" && pwd)

zip=$("$here/tools/pack.sh" | tail -1)
gnome-extensions install --force "$zip"

# The running shell does not know a newly installed extension yet, so
# `gnome-extensions enable` would fail; add it to the enabled list directly.
python3 - "$uuid" <<'EOF'
import sys
from gi.repository import Gio
settings = Gio.Settings.new('org.gnome.shell')
enabled = settings.get_strv('enabled-extensions')
if sys.argv[1] not in enabled:
    settings.set_strv('enabled-extensions', enabled + [sys.argv[1]])
Gio.Settings.sync()
EOF

echo "Installed $uuid. Log out and back in, then press Super+Shift+C."
