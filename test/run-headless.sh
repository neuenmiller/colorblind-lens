#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
# Run Colorblind Lens inside a throwaway headless GNOME Shell and drive it.
# Everything (config, dconf, runtime dir, D-Bus) is private to WORKDIR,
# so the real session and its settings are never touched.
#
#   test/run-headless.sh WORKDIR
#
# Renders with llvmpipe by default; GPU=1 uses the normal GL driver
# (needed on NVIDIA, where Mesa cannot open the render node).
# DRIVER=other.py runs a different driver script, given WORKDIR and the
# path of drive.py so it can import the helpers.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=${1:?usage: run-headless.sh WORKDIR}

# WORKDIR is wiped on every run, so only take a path that is empty or
# missing, or one this script set up before.
if [[ -e $root && ! -e $root/.colorblind-lens-test && -n $(ls -A "$root" 2>/dev/null) ]]; then
    echo "run-headless.sh: refusing to wipe $root: not empty and not a test workdir" >&2
    exit 2
fi
rm -rf "$root"
mkdir -p "$root"/{config/dconf,data/gnome-shell/extensions,cache,state,keyfiles,shots}
touch "$root/.colorblind-lens-test"
# Wayland socket paths must fit in 108 bytes, so the runtime dir lives
# under a short path rather than inside WORKDIR.
runtime=$(mktemp -d "${TMPDIR:-/tmp}/lens-rt.XXXXXX")
# The private session's document portal can hold a mount in there for a
# moment after the session ends, so retry once and never fail on it.
trap 'rm -rf "$runtime" 2>/dev/null || { sleep 1; rm -rf "$runtime" 2>/dev/null; } || true' EXIT
glib-compile-schemas "$here/../colorblind-lens@thamk.me/schemas"
ln -s "$here/../colorblind-lens@thamk.me" "$root/data/gnome-shell/extensions/"
ln -s "$here/helper@colorblind-lens.test" "$root/data/gnome-shell/extensions/"

cat > "$root/keyfiles/00-test" <<'EOF'
[org/gnome/shell]
enabled-extensions=['colorblind-lens@thamk.me', 'helper@colorblind-lens.test']
disable-user-extensions=false
welcome-dialog-last-shown-version='999'
# Lets test/run-in-container.sh try GNOME versions not yet in metadata.json.
disable-extension-version-validation=true

[org/gnome/desktop/interface]
enable-animations=false
EOF
dconf compile "$root/config/dconf/user" "$root/keyfiles"

export XDG_CONFIG_HOME=$root/config XDG_DATA_HOME=$root/data
export XDG_CACHE_HOME=$root/cache XDG_STATE_HOME=$root/state
export XDG_RUNTIME_DIR=$runtime
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
if [[ ${GPU:-0} != 1 ]]; then
    export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json
    export LIBGL_ALWAYS_SOFTWARE=1 MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
fi
export ROOT=$root HERE=$here
# The test helper extension refuses to enable without this.
export COLORBLIND_LENS_TEST=1
# MONITORS="1920x1080 2560x1440" gives one virtual monitor per size.
monitor_args=()
for size in ${MONITORS:-1280x800}; do
    monitor_args+=(--virtual-monitor "$size")
done
export MONITOR_ARGS="${monitor_args[*]}"

dbus-run-session -- bash -c '
    gnome-shell --headless --wayland --no-x11 $MONITOR_ARGS \
        >"$ROOT/shell.log" 2>&1 &
    shell=$!
    status=0
    python3 ${DRIVER:-"$HERE/drive.py"} "$ROOT" ${DRIVER:+"$HERE/drive.py"} || status=$?
    kill $shell 2>/dev/null
    wait $shell 2>/dev/null
    exit $status'
