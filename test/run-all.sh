#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
# Run both headless suites: one monitor, then a three-monitor desk.
#   test/run-all.sh WORKDIR
# Pass GPU=1 on NVIDIA, and a short TMPDIR if /tmp is not writable.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=${1:?usage: run-all.sh WORKDIR}
status=0

run() {
    "$here/run-headless.sh" "$@" 2>/dev/null \
        | grep -E '^(PASS|FAIL|      \(|all checks|[0-9]+ failure)'
    return "${PIPESTATUS[0]}"
}

echo "== one monitor"
run "$root/single" || status=1
echo "== three monitors"
DRIVER="$here/drive_monitors.py" MONITORS="1920x1080 2560x1440 1920x1080" \
    run "$root/monitors" || status=1
exit $status
