#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
# Run both headless suites on another Fedora release, to try the
# extension on a different GNOME Shell version without installing it.
#
#   test/run-in-container.sh 45 WORKDIR
#
# Needs podman. Renders with llvmpipe inside the container. CMD runs a
# different command in the checkout instead, e.g. for debugging:
#   CMD='test/run-headless.sh /work/one' test/run-in-container.sh 45 WORKDIR
set -euo pipefail

release=${1:?usage: run-in-container.sh FEDORA_RELEASE WORKDIR}
work=${2:?usage: run-in-container.sh FEDORA_RELEASE WORKDIR}
repo=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$work"

podman run --rm --security-opt label=disable \
    -e CMD="${CMD:-}" -e TMPDIR=/tmp \
    -v "$repo:/src:ro" -v "$work:/work" \
    -v "colorblind-lens-dnf-$release:/var/cache/libdnf5" \
    "registry.fedoraproject.org/fedora:$release" bash -c '
        set -e
        dnf -y -q --setopt=keepcache=True install gnome-shell dbus-daemon \
            dconf glib2 fontconfig abattis-cantarell-fonts google-noto-sans-fonts \
            mesa-dri-drivers python3-gobject python3-pillow python3-numpy \
            python3-dbusmock >/dev/null
        echo "GNOME Shell: $(gnome-shell --version)"
        # GNOME Shell 51 needs a system bus with logind on it at startup;
        # there is no systemd in the container, so mock logind.
        mkdir -p /run/dbus
        dbus-uuidgen --ensure
        dbus-daemon --system --fork
        python3 -m dbusmock --system --template logind >/dev/null 2>&1 &
        sleep 1
        cp -r /src /tmp/repo
        cd /tmp/repo
        eval "${CMD:-test/run-all.sh /work/run}"'
