# Colorblind Lens

A GNOME Shell extension that puts a lens on your screen for red-green
colorblind eyes. Press Super+Shift+C and drag a rectangle, as you would
with the screenshot tool. Everything you see through that rectangle is
recolored so that reds and greens no longer look alike, and the rest of
the screen stays as it is. The lens is live, so video, scrolling and
typing show through it without delay, and clicks pass through it to the
windows underneath.

![A dashboard with red and green lines, status dots, a heatmap and a test
plate. The right half is under the lens, where reds have turned magenta
and greens darker.](docs/screenshot.png)

It runs on GNOME 50 and 51 under Wayland.

## What it does to colors

Inside the lens, reds take on blue and turn magenta, and greens get
darker. Red-green colorblind eyes still see the difference between blue
and yellow and between light and dark, so colors they used to mix up now
differ in ways they can see.

The picture below shows one screen three ways. The second and third rows
simulate how green-weak and red-weak eyes see it. Outside the lens the
red and green lines, the status dots and the heatmap cells blur together;
inside it they separate. The plate on the right hides a 5 that shows only
through the lens.

![The same screen three times: as normal eyes see it, as a deutan eye
sees it, and as a protan eye sees it.](docs/how-it-looks.png)

## Install

Download `colorblind-lens@thamk.me.shell-extension.zip` from the
[latest release](https://github.com/neuenmiller/colorblind-lens/releases/latest)
and install it:

```bash
gnome-extensions install --force colorblind-lens@thamk.me.shell-extension.zip
```

GNOME on Wayland only loads new extensions at login, so log out and back
in. Then turn it on in the Extensions app, or with:

```bash
gnome-extensions enable colorblind-lens@thamk.me
```

From a checkout of this repository, `./install.sh` packs, installs and
enables it in one go; log out and back in afterwards.

## Use

Press Super+Shift+C. The screen dims and you drag a rectangle. A plain
click makes a 480 × 320 lens around the click, Enter brings back the last
lens you had, and Escape or a right click cancels. A lens stays on one
monitor: a drawn lens stops at the edge of the monitor where the drag
began.

Once the lens is up:

- drag the pill above it to move it, onto another monitor if you like;
- drag any edge or corner to resize it;
- click the mode name to cycle through the modes;
- scroll over the pill to change the strength in 10% steps;
- click × or press Super+Shift+C again to close it.

The Colorblind Lens tile in Quick Settings opens and closes the lens too,
and its arrow opens a menu with the modes and a strength slider. A lens
that is open when the screen locks comes back when you unlock it.

| Mode | For |
|---|---|
| Strong fix (default) | any red-green colorblind eye; you do not need to know your type |
| Deutan fix | green-weak eyes, with smaller color changes |
| Protan fix | red-weak eyes, with smaller color changes |
| Deutan preview, Protan preview | people with normal vision, to see roughly what those eyes see |

Strength 100% is the intended setting for the Strong fix. If your
colorblindness is mild, start at 50%. Above 100% it separates colors
further and greens get darker.

## How well it works

These figures come from [`tools/evaluate.py`](tools/evaluate.py), which
models colorblind vision with published simulations. They are model
numbers, not a clinical measurement, and the lens does not restore color
vision: it trades accurate colors for colors you can tell apart. Trying
it with your own eyes is the test that counts.

The script builds thousands of pairs of colors that a simulated eye
confuses, applies each mode, and measures how different the two colors
of each pair then look to that eye, as CIEDE2000 ΔE. A ΔE near 1 is about
the smallest difference people notice side by side. The table gives the
median over all pairs; the gentle fix is the one matching each eye's
type.

| Simulated eye | No lens | Gentle fix, 100% | Strong fix, 100% |
|---|---|---|---|
| Protanopia (no working red cones) | 0.0 | 7.7 | 11.7 |
| Deuteranopia (no working green cones) | 0.0 | 7.4 | 12.2 |
| Protanomaly, severity 0.6 | 3.6 | 6.9 | 11.8 |
| Deuteranomaly, severity 0.6 | 3.2 | 5.7 | 10.2 |
| How far colors move, for normal eyes | 0 | 4.9 to 8.5 | 12.4 |

The cost of the larger separation is the last row: the Strong fix changes
colors more. Two other checks guard against side effects. Of the color
pairs a simulated eye could already tell apart, 2 to 5% become hard to
tell apart under the Strong fix, against 1 to 3.5% under the gentle fix.
For 25 everyday colors, the smallest difference from white or black
stays between 16 and 22, within about 2 of its value without the lens,
so colored text stays readable. Turning the gentle fix up to 200% fails
that check: some colors then match white or black.

## How it works

The lens uses the same approach as GNOME's magnifier. It is a clone of
the whole shell picture (`Main.uiGroup`), clipped to the rectangle and
drawn above it, so it shows exactly what is underneath without capturing
the screen, and nothing leaves the compositor. A fragment shader
recolors the clone.

The Strong fix rests on a property of the Viénot, Brettel & Mollon (1999)
simulations of red-green dichromacy. For both protan and deutan eyes,
every simulated color has equal red and green in linear RGB, and two
colors look the same to such an eye only when they differ along one
direction in which red and green move in opposite ways. So red minus
green changes along every line of colors those eyes confuse, and it is
zero for every color they see as everyone else does. The shader measures
red minus green and writes it back where both eyes can see it. Reddish
colors gain blue, moving toward magenta at the same brightness. Greenish
colors lose blue and get darker, but never below 30% of their
brightness. Every step eases toward its limit instead of clipping, so two
different reds never end up as the same color. The constants were chosen
by scoring candidates on the measures above.

The gentle fixes use the daltonize method of Fidaner, Lin & Ozguven
(2005): simulate what the eye sees, take the difference from the real
color as the information it loses, and add that difference to the green
and blue channels.

## Limitations

- GNOME 50 and 51 on Wayland only. GNOME 51 has been tested only in a
  headless container (`test/run-in-container.sh`). It is not on
  extensions.gnome.org; see [How this was made](#how-this-was-made).
- After installing or updating, log out and back in.
- The lens repaints whenever anything on screen changes, so a large lens
  over a playing video costs some GPU time.
- Screenshots and screen recordings include the lens.
- There is no settings window. To change the shortcut:

  ```bash
  gsettings --schemadir ~/.local/share/gnome-shell/extensions/colorblind-lens@thamk.me/schemas \
      set org.gnome.shell.extensions.colorblind-lens toggle-lens "['<Super><Alt>l']"
  ```

- It has been used on one machine (Fedora 44, an NVIDIA RTX 3060, three
  monitors of different sizes) and in the headless test shells below.

## Development

The tests start throwaway headless GNOME Shells with their own config,
D-Bus and runtime directories, then draw, move, resize, lock and close
lenses with a virtual mouse and keyboard. They check every shaded pixel
against the shader formula, check that lenses and their pill stay on
real monitors in an irregular three-monitor layout, and measure a hidden
number on generated test plates under simulated colorblind vision.

```bash
GPU=1 test/run-all.sh /a/new/empty/dir           # both suites
test/run-in-container.sh 45 /a/new/empty/dir     # another Fedora release, with podman
python3 tools/evaluate.py                        # the table above
tools/pack.sh                                    # build the zip into dist/
DRIVER=tools/screenshots.py MONITORS=1600x1000 GPU=1 \
    test/run-headless.sh /a/new/empty/dir        # the pictures in docs/
```

`GPU=1` uses your normal graphics driver and is needed on NVIDIA; leave
it out to render with llvmpipe. The test helper extension puts its shell
in unsafe mode so the driver can use D-Bus Eval, and although it refuses
to run outside the test runner, it should never be installed in a real
session.

## How this was made

Kansapat Udomchokpaiboon designed and tested Colorblind Lens. Most of
the code was written by Claude, an AI model made by Anthropic, under his
direction. extensions.gnome.org does not accept extensions written mostly
by AI, so it is published here instead.

## Credits

- Françoise Viénot, Hans Brettel and John D. Mollon (1999), "Digital
  video colourmaps for checking the legibility of displays by
  dichromats", for the simulation. The matrix values are taken from
  [libDaltonLens](https://github.com/DaltonLens/libDaltonLens) by
  Nicolas Burrus (public domain).
- Onur Fidaner, Poliang Lin and Nevran Ozguven (2005), "Analysis of
  Color Blindness", for the daltonize method of the gentle fixes.
- Gustavo M. Machado, Manuel M. Oliveira and Leandro A. F. Fernandes
  (2009), "A Physiologically-based Model for Simulation of Color Vision
  Deficiency", used in the evaluation only, with values from
  [colour-science](https://github.com/colour-science/colour).

## License

GPL-2.0-or-later. Copyright 2026 Kansapat Udomchokpaiboon. See
[LICENSE](LICENSE).
