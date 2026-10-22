// SPDX-License-Identifier: GPL-2.0-or-later
// SPDX-FileCopyrightText: 2026 Kansapat Udomchokpaiboon

import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

// Dichromat simulation of Viénot, Brettel & Mollon (1999), in linear RGB.
// Copied from libDaltonLens (dl_vienot_*_rgbCvd_from_rgb). Row-major.
const SIMULATION = {
    protan: [
        0.11238, 0.88762, 0.00000,
        0.11238, 0.88762, -0.00000,
        0.00401, -0.00401, 1.00000,
    ],
    deutan: [
        0.29275, 0.70725, 0.00000,
        0.29275, 0.70725, -0.00000,
        -0.02234, 0.02234, 1.00000,
    ],
};

// Error redistribution of Fidaner, Lin & Ozguven (2005). Whatever the
// simulation threw away is pushed into green and blue, so a red-green
// difference turns into a blue-yellow one, which these eyes still see.
// Row-major.
const ERROR_SHIFT = [
    0.0, 0.0, 0.0,
    0.7, 1.0, 0.0,
    0.7, 0.0, 1.0,
];

const METHOD = {daltonize: 0, simulate: 1, strong: 2};

export const DEFAULT_MODE = 'strong';

export const MODES = {
    'strong': {
        label: 'Strong fix (any red-green type)',
        short: 'Strong fix',
        cvd: 'deutan',
        method: 'strong',
    },
    'deutan': {
        label: 'Gentle fix for green-weak (deutan)',
        short: 'Deutan fix',
        cvd: 'deutan',
        method: 'daltonize',
    },
    'protan': {
        label: 'Gentle fix for red-weak (protan)',
        short: 'Protan fix',
        cvd: 'protan',
        method: 'daltonize',
    },
    'deutan-sim': {
        label: 'Preview deutan vision',
        short: 'Deutan preview',
        cvd: 'deutan',
        method: 'simulate',
    },
    'protan-sim': {
        label: 'Preview protan vision',
        short: 'Protan preview',
        cvd: 'protan',
        method: 'simulate',
    },
};

// GLSL mat3 constructors take their arguments column by column.
function glslMat3(m) {
    const columns = [m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]];
    return `mat3(${columns.map(v => v.toFixed(5)).join(', ')})`;
}

const DECLARATIONS = `
uniform float cvd;
uniform float strength;
uniform float method;

const mat3 sim_protan = ${glslMat3(SIMULATION.protan)};
const mat3 sim_deutan = ${glslMat3(SIMULATION.deutan)};
const mat3 shift_matrix = ${glslMat3(ERROR_SHIFT)};

vec3 lens_to_linear(vec3 c) {
    vec3 lo = c / 12.92;
    vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
    return mix(lo, hi, step(vec3(0.04045), c));
}

vec3 lens_to_srgb(vec3 c) {
    vec3 lo = c * 12.92;
    vec3 hi = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
    return mix(lo, hi, step(vec3(0.0031308), c));
}

// Strong fix. Protan and deutan simulations both output colours with
// R = G, and every pair of colours either eye confuses differs in R - G.
// That signal goes back in where both eyes see it: reds gain blue
// (toward magenta, at the same brightness), greens lose blue and get
// darker. Every step eases toward its limit instead of clipping, so two
// different reds never land on the same colour, and greens never go
// below 30% brightness, so text stays readable against white and black.
// Constants were tuned on random confusion pairs and 25 everyday colours.
vec3 strong_fix(vec3 c, float strength) {
    float d = strength * (c.r - c.g);
    float pos = max(d, 0.0);
    float neg = max(-d, 0.0);
    float b = (1.0 - (1.0 - c.b) * exp(-3.0 * pos)) * exp(-neg);
    float g = c.g * exp(-1.5 * pos * c.b);
    float dark = 0.3 + 0.7 * exp(-1.5 * neg / 0.7);
    return vec3(c.r * dark, g * dark, b);
}
`;

// cogl_color_out holds the premultiplied texel at this point.
const CODE = `
float alpha = cogl_color_out.a;
if (alpha > 0.0) {
    vec3 c = clamp(cogl_color_out.rgb / alpha, 0.0, 1.0);
    vec3 result;
    if (method > 1.5) {
        result = strong_fix(c, strength);
    } else {
        mat3 sim_matrix = cvd > 0.5 ? sim_deutan : sim_protan;
        vec3 seen = lens_to_srgb(clamp(sim_matrix * lens_to_linear(c), 0.0, 1.0));
        if (method > 0.5)
            result = mix(c, seen, clamp(strength, 0.0, 1.0));
        else
            result = c + strength * (shift_matrix * (c - seen));
    }
    cogl_color_out.rgb = clamp(result, 0.0, 1.0) * alpha;
}
`;

function applyMode(effect, mode, strength) {
    const {cvd, method} = MODES[mode] ?? MODES[DEFAULT_MODE];
    effect.setFloat('cvd', cvd === 'deutan' ? 1 : 0);
    effect.setFloat('strength', strength);
    effect.setFloat('method', METHOD[method]);
    effect.queue_repaint();
}

// GNOME 50 adds shader snippets through Shell.GLSLEffect. GNOME 51
// removed it in favour of Clutter.ShaderEffect returning a Cogl.Snippet.
// Only the class whose base exists is defined.
const GLSLEffectLens = Shell.GLSLEffect && GObject.registerClass(
class GLSLEffectLens extends Shell.GLSLEffect {
    vfunc_build_pipeline() {
        this.add_glsl_snippet(Cogl.SnippetHook.FRAGMENT,
            DECLARATIONS, CODE, false);
    }

    setFloat(name, value) {
        this.set_uniform_float(this.get_uniform_location(name), 1, [value]);
    }

    configure(mode, strength) {
        applyMode(this, mode, strength);
    }
});

const ShaderEffectLens = !Shell.GLSLEffect && GObject.registerClass(
class ShaderEffectLens extends Clutter.ShaderEffect {
    vfunc_get_static_snippet() {
        return Cogl.Snippet.new(Cogl.SnippetHook.FRAGMENT, DECLARATIONS, CODE);
    }

    setFloat(name, value) {
        this.set_uniform_float(name, 1, [value]);
    }

    configure(mode, strength) {
        applyMode(this, mode, strength);
    }
});

export function createLensEffect() {
    const effect = new (GLSLEffectLens || ShaderEffectLens)();
    effect.configure(DEFAULT_MODE, 1.0);
    return effect;
}
