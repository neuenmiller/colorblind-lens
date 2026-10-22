#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
# Build the installable zip into dist/.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
uuid=colorblind-lens@thamk.me
mkdir -p "$repo/dist"

# gnome-extensions pack compiles nothing into the zip; GNOME compiles
# the schema when the zip is installed.
rm -f "$repo/$uuid/schemas/gschemas.compiled"
gnome-extensions pack "$repo/$uuid" --force --out-dir "$repo/dist" \
    --extra-source=effect.js --extra-source=lens.js --extra-source=selector.js \
    --extra-source="$repo/LICENSE"
echo "$repo/dist/$uuid.shell-extension.zip"
