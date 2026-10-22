#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon
"""Score the lens modes on simulated colour vision. Prints the table in
the README.

Viewers: full protanopia and deuteranopia (Viénot, Brettel & Mollon
1999) and milder protanomaly and deuteranomaly (Machado, Oliveira &
Fernandes 2009, severities 0.4 to 0.8), all applied in linear RGB.

For each mode and viewer:
  separation  ΔE between pairs of colours the viewer confuses, after
              correction (10th percentile and median; higher is better)
  collapse    share of pairs the viewer could already tell apart
              (ΔE >= 15) that end up below ΔE 7 (lower is better)
  contrast    smallest ΔE between any of 25 everyday colours and white
              or black, as the viewer sees them (higher is better)
  change      median ΔE between each colour and its corrected version,
              for normal vision (how far the mode moves colours)
ΔE is CIEDE2000; pass --cie76 for the plain Euclidean CIELAB distance.
These are model numbers, not a clinical measurement.
"""
import argparse

import numpy as np

VIENOT = {  # libDaltonLens, dl_vienot_*_rgbCvd_from_rgb
    'protan': [[0.11238, 0.88762, 0.0], [0.11238, 0.88762, 0.0],
               [0.00401, -0.00401, 1.0]],
    'deutan': [[0.29275, 0.70725, 0.0], [0.29275, 0.70725, 0.0],
               [-0.02234, 0.02234, 1.0]],
}
MACHADO = {  # colour-science CVD_MATRICES_MACHADO2010
    ('protan', 0.4): [[0.539009, 0.579343, -0.118352], [0.082546, 0.866121, 0.051332],
                      [-0.007136, -0.011959, 1.019095]],
    ('protan', 0.6): [[0.385450, 0.769005, -0.154455], [0.100526, 0.829802, 0.069673],
                      [-0.007442, -0.022190, 1.029632]],
    ('protan', 0.8): [[0.259411, 0.923008, -0.182420], [0.110296, 0.804340, 0.085364],
                      [-0.006276, -0.034346, 1.040622]],
    ('deutan', 0.4): [[0.605511, 0.528560, -0.134071], [0.155318, 0.812366, 0.032316],
                      [-0.009376, 0.023176, 0.986200]],
    ('deutan', 0.6): [[0.498864, 0.674741, -0.173604], [0.205199, 0.754872, 0.039929],
                      [-0.011131, 0.030969, 0.980162]],
    ('deutan', 0.8): [[0.422823, 0.781057, -0.203881], [0.245752, 0.709602, 0.044646],
                      [-0.011843, 0.037423, 0.974421]],
}
SHIFT = np.array([[0.0, 0.0, 0.0], [0.7, 1.0, 0.0], [0.7, 0.0, 1.0]])

EVERYDAY = [(220, 40, 40), (255, 0, 0), (130, 20, 20), (200, 20, 60), (40, 160, 60),
            (0, 255, 0), (80, 130, 50), (20, 90, 30), (150, 220, 60), (255, 140, 0),
            (240, 170, 30), (140, 90, 40), (255, 150, 170), (240, 60, 150),
            (130, 60, 180), (150, 100, 230), (30, 100, 220), (100, 180, 240),
            (20, 40, 110), (30, 150, 150), (40, 200, 220), (250, 220, 40),
            (128, 128, 128), (225, 180, 150), (128, 140, 50)]


def to_linear(c):
    return np.where(c < 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c < 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def viewer(matrix):
    m = np.array(matrix)
    return lambda s: to_srgb(np.clip(to_linear(s) @ m.T, 0, 1))


def lab(s):
    xyz = to_linear(s) @ np.array([[0.4124, 0.3576, 0.1805],
                                   [0.2126, 0.7152, 0.0722],
                                   [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def de76(a, b):
    return np.linalg.norm(lab(a) - lab(b), axis=-1)


def de2000(a, b):
    """CIEDE2000 (Sharma, Wu & Dalal 2005 formulation)."""
    L1, a1, b1 = np.moveaxis(lab(a), -1, 0)
    L2, a2, b2 = np.moveaxis(lab(b), -1, 0)
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    hsum = h1p + h2p
    hpm = np.where(np.abs(h1p - h2p) > 180,
                   np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2), hsum / 2)
    hpm = np.where(C1p * C2p == 0, hsum, hpm)
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                   + Rt * (dCp / Sc) * (dHp / Sh))


# The lens modes, as in effect.js.
def strong(strength):
    def f(c):
        r, g, b = c[..., 0], c[..., 1], c[..., 2]
        d = strength * (r - g)
        pos, neg = np.maximum(d, 0), np.maximum(-d, 0)
        b2 = (1 - (1 - b) * np.exp(-3 * pos)) * np.exp(-neg)
        g2 = g * np.exp(-1.5 * pos * b)
        dark = 0.3 + 0.7 * np.exp(-1.5 * neg / 0.7)
        return np.clip(np.stack([r * dark, g2 * dark, b2], -1), 0, 1)
    return f


def gentle(cvd, strength):
    sim = viewer(VIENOT[cvd])
    return lambda c: np.clip(c + strength * ((c - sim(c)) @ SHIFT.T), 0, 1)


def confused_pairs(see, rng, n, null, threshold):
    """Pairs that differ by ΔE >= 12 for normal vision but by less than
    `threshold` for this viewer, found by stepping along the confusion
    direction `null` (linear RGB)."""
    out = []
    while len(out) < n:
        c = rng.uniform(0.02, 0.9, (n, 3))
        step = rng.uniform(0.05, 0.4, (n, 1)) * rng.choice([-1, 1], (n, 1))
        c2 = c + step * null / np.abs(null).max()
        ok = np.all((c2 >= 0) & (c2 <= 1), -1)
        s1, s2 = to_srgb(c[ok]), to_srgb(c2[ok])
        keep = (de76(s1, s2) >= 12) & (de76(see(s1), see(s2)) < threshold)
        out.extend(zip(s1[keep], s2[keep]))
    out = np.array(out[:n])
    return out[:, 0], out[:, 1]


def seen_pairs(see, rng, n):
    a, b = rng.uniform(0, 1, (2, n * 4, 3))
    a, b = to_srgb(a), to_srgb(b)
    keep = de76(see(a), see(b)) >= 15
    return a[keep][:n], b[keep][:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cie76', action='store_true')
    ap.add_argument('-n', type=int, default=3000)
    args = ap.parse_args()
    de = de76 if args.cie76 else de2000
    rng = np.random.default_rng(1)

    viewers = {f'{cvd}opia': (viewer(VIENOT[cvd]), cvd, 1.0) for cvd in VIENOT}
    for (cvd, sev), m in MACHADO.items():
        viewers[f'{cvd}omaly {sev}'] = (viewer(m), cvd, sev)
    null = {cvd: np.linalg.svd(np.array(VIENOT[cvd]))[2][-1] for cvd in VIENOT}

    modes = {'none': lambda c: c}
    for s in (0.5, 1.0, 2.0):
        modes[f'gentle {s:.0%}'] = None          # per viewer type, below
        modes[f'strong {s:.0%}'] = strong(s)
    everyday = np.array(EVERYDAY) / 255
    white, black = np.ones(3), np.zeros(3)
    rand = to_srgb(rng.uniform(0, 1, (4000, 3)))

    print(f'ΔE = {"CIE76" if args.cie76 else "CIEDE2000"}; '
          'separation p10/median, collapse %, contrast floor, change')
    for vname, (see, cvd, sev) in viewers.items():
        thr = 1.0 if sev == 1.0 else 5.0
        pa, pb = confused_pairs(see, rng, args.n, null[cvd], thr)
        sa, sb = seen_pairs(see, rng, args.n)
        print(f'\n{vname}  ({len(pa)} confused pairs, before: median ΔE '
              f'{np.median(de(see(pa), see(pb))):.1f})')
        for mname, f in modes.items():
            if f is None:
                f = gentle(cvd, float(mname.split()[1].rstrip('%')) / 100)
            sep = de(see(f(pa)), see(f(pb)))
            collapse = np.mean(de(see(f(sa)), see(f(sb))) < 7) * 100
            seen = see(f(everyday))
            floor = min(de(seen, see(white)).min(), de(seen, see(black)).min())
            change = np.median(de(f(rand), rand))
            print(f'  {mname:12s} {np.percentile(sep, 10):5.1f} / {np.median(sep):5.1f}'
                  f'   {collapse:4.1f}%   {floor:5.1f}   {change:5.1f}')


if __name__ == '__main__':
    main()
