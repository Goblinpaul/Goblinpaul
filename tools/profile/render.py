# Adapted from Giorgi Kobaidze's MIT-licensed tools/profile/render.py
# (https://github.com/georgekobaidze/georgekobaidze), especially the
# contribution-city isometric layout, quartile roofs, and window PRNG.
# Visual identity (terminal chrome, #020400 / #39ff14, Courier New) is
# original to this profile. See NOTICE and LICENSE.
"""Renders the profile README's SVG slices into assets/.

The approved Matrix-rain header (assets/header.svg) is never overwritten.
Run fetch.py first to refresh data/*.json; this script only reads those
files (and tools/profile/projects.json) and draws the other sections.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import math
import pathlib
import re
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / "data"
OUT = ROOT / "assets"
PROJECTS_FILE = HERE / "projects.json"

# Match the approved header exactly.
WIDTH, RADIUS, TITLE_H = 800, 10, 28
PAD_X, PAD_BOT = 12, 14
BG, CHROME, CHROME_LINE = "#020400", "#0a1c0a", "#1a5a1a"
GREEN, DIM = "#39ff14", "#2a8a2a"
MID, SOFT, TILE = "#1ec81e", "#0a1c0a", "#111a11"
FONT = '"Courier New", Courier, ui-monospace, "Liberation Mono", monospace'
e = html.escape


# ─────────────────────────────── chrome ────────────────────────────────
def base_css() -> str:
    return f"""
    text, .prompt, .label, .value, .dim, .chrome-title {{
      font-family: {FONT};
    }}
    .chrome-title {{
      fill: {DIM};
      font-size: 11px;
    }}
    .prompt {{
      fill: {GREEN};
      font-size: 13px;
    }}
    .label {{
      fill: {DIM};
      font-size: 11px;
    }}
    .value {{
      fill: {GREEN};
      font-size: 28px;
    }}
    .sub {{
      fill: {DIM};
      font-size: 12px;
    }}
    .fg {{
      fill: {GREEN};
      font-size: 13px;
    }}
    .muted {{
      fill: {DIM};
      font-size: 12px;
    }}
    @keyframes fadein {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
    @keyframes blink {{ 0%,45% {{ opacity: 1; }} 50%,95% {{ opacity: 0; }} 100% {{ opacity: 1; }} }}
    .ln {{ animation: fadein .35s ease-out both; }}
    .cursor {{ animation: blink 1.1s step-end infinite; }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
    """.strip()


def terminal_open(height: int, title: str, aria: str, desc: str = "", extra_css: str = "", extra_defs: str = "") -> str:
    d = f"\n  <desc>{e(desc)}</desc>" if desc else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}"
     role="img" aria-label="{e(aria)}">
  <title>{e(title)}</title>{d}
  <defs>
    <clipPath id="term">
      <rect x="1" y="1" width="{WIDTH-2}" height="{height-2}" rx="{RADIUS}" ry="{RADIUS}"/>
    </clipPath>
    <style type="text/css"><![CDATA[
{base_css()}
{extra_css}
    ]]></style>
    {extra_defs}
  </defs>
  <rect x="0" y="0" width="{WIDTH}" height="{height}" rx="{RADIUS}" ry="{RADIUS}"
        fill="{BG}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
  <g clip-path="url(#term)">
    <rect x="0" y="0" width="{WIDTH}" height="{TITLE_H}" fill="{CHROME}"/>
    <line x1="0" y1="{TITLE_H}" x2="{WIDTH}" y2="{TITLE_H}" stroke="{CHROME_LINE}" stroke-width="1"/>
    <circle cx="18" cy="{TITLE_H/2}" r="5" fill="#ff5f56"/>
    <circle cx="36" cy="{TITLE_H/2}" r="5" fill="#ffbd2e"/>
    <circle cx="54" cy="{TITLE_H/2}" r="5" fill="#27c93f"/>
    <text class="chrome-title" x="{WIDTH/2}" y="{TITLE_H/2 + 1}"
          text-anchor="middle" dominant-baseline="middle">{e(title)}</text>
'''


def terminal_close() -> str:
    return "  </g>\n</svg>\n"


def prompt_row(y: float, command: str, comment: str = "", cursor: bool = True) -> str:
    """A `$ command` line, optional dim comment, optional blinking block cursor."""
    # 13px Courier, ~7.8px advance (0.6em). "$ " is 2 cells.
    x = PAD_X + 8
    parts = [
        f'<text class="prompt" x="{x}" y="{y}" text-anchor="start" dominant-baseline="middle">{e("$ " + command)}</text>'
    ]
    end = x + (2 + len(command)) * 7.8
    if comment:
        parts.append(
            f'<text class="muted" x="{end + 10:.1f}" y="{y}" text-anchor="start" dominant-baseline="middle">{e("# " + comment)}</text>'
        )
        # no cursor when a trailing comment is shown
    elif cursor:
        # cap-height block at 13px, 0.5em wide — same recipe as the header cursors
        cur_w, cur_h = 13 * 0.5, 13 * (1170 / 2048)
        # typo-center offset so the cap midpoint sits on y
        typo = (1255 + -386) / 2 / 2048 * 13
        cap_mid_from_typo = (1170 / 2048 / 2) * 13 - typo
        cur_y = y + cap_mid_from_typo - cur_h / 2
        parts.append(
            f'<rect class="cursor" x="{end + 4:.1f}" y="{cur_y:.2f}" width="{cur_w:.2f}" height="{cur_h:.2f}" fill="{GREEN}"/>'
        )
    return "\n".join(parts)


# ─────────────────────────────── stats ────────────────────────────────
def fmt(n) -> str:
    return "—" if n is None else f"{n:,}"


def _days(n) -> str:
    n = int(n or 0)
    return "1 day" if n == 1 else f"{n} days"


def _followers(n) -> str:
    n = int(n or 0)
    return "1 follower" if n == 1 else f"{n} followers"


def corners(x, y, w, h, arm=9, color=None, sw=1.25, fill=True) -> str:
    """Four L-shaped corner brackets over a faint card body."""
    color = color or GREEN
    x2, y2 = x + w, y + h
    parts = []
    if fill:
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="2" fill="#0c140c" stroke="#163016" stroke-width="0.75"/>'
        )
    segs = [
        (x, y + arm, x, y, x + arm, y),
        (x2 - arm, y, x2, y, x2, y + arm),
        (x, y2 - arm, x, y2, x + arm, y2),
        (x2 - arm, y2, x2, y2, x2, y2 - arm),
    ]
    for x0, y0, xc, yc, x1, y1 in segs:
        parts.append(
            f'<path d="M{x0:.1f},{y0:.1f} L{xc:.1f},{yc:.1f} L{x1:.1f},{y1:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="square" stroke-linejoin="miter"/>'
        )
    return "\n  ".join(parts)


def corner_card(x, y, w, h, label, value, sub, delay) -> str:
    sub_svg = (
        f'<text class="sub" x="{x + 14}" y="{y + h - 14}">{e(sub)}</text>'
        if sub else ""
    )
    return (
        f'<g class="ln" style="animation-delay:{delay:.2f}s">\n'
        f'  {corners(x, y, w, h)}\n'
        f'  <text class="label" x="{x + 14}" y="{y + 22}" letter-spacing="1.2">{e(label)}</text>\n'
        f'  <text class="value" x="{x + 14}" y="{y + 56}">{e(value)}</text>\n'
        f'  {sub_svg}\n'
        f'</g>'
    )


def dotted_kv(x, y, key, value, width_chars=18) -> str:
    dots = "." * max(2, width_chars - len(key))
    return (
        f'<text x="{x}" y="{y}" xml:space="preserve">'
        f'<tspan class="label">{e(key)}</tspan>'
        f'<tspan class="muted">{dots}</tspan> '
        f'<tspan class="fg">{e(value)}</tspan></text>'
    )


def build_stats(d: dict) -> str:
    updated = datetime.date.fromisoformat(d["updated"])
    since = datetime.date.fromisoformat(d["created_at"][:10])
    year = d.get("year", updated.year)
    cy = d.get("contributions_year", d.get("commits_year", 0))
    ca = d.get("contributions_all", d.get("commits_all", 0))
    n_accounts = int(d.get("accounts") or 0)

    parts: list[str] = []
    head_y = TITLE_H + 20
    parts.append(
        f'<text class="fg" x="{PAD_X + 8}" y="{head_y}" text-anchor="start" '
        f'dominant-baseline="middle">~/stats</text>'
    )
    parts.append(
        f'<text class="muted" x="{WIDTH - PAD_X}" y="{head_y}" text-anchor="end" '
        f'dominant-baseline="middle">// 02</text>'
    )

    prompt_y = TITLE_H + 44
    parts.append(prompt_row(prompt_y, "gh stats --user goblinpaul"))

    tw, gap, ty, th = 176, 22, TITLE_H + 62, 100
    cards = [
        ("TOTAL STARS", fmt(d.get("stars", 0)), ""),
        (f"CONTRIBUTIONS {year}", fmt(cy), f"{fmt(ca)} all time"),
        ("PULL REQUESTS", fmt(d.get("prs", 0)), f"{fmt(d.get('prs_merged', 0))} merged"),
        ("CURRENT STREAK", f"{d.get('streak_current', 0)}d", f"longest: {_days(d.get('streak_longest', 0))}"),
    ]
    for i, (lab, val, sub) in enumerate(cards):
        parts.append(corner_card(PAD_X + i * (tw + gap), ty, tw, th, lab, val, sub, 0.12 + i * 0.06))

    ry, rh = ty + th + 16, 148
    lw, gap2 = 268, 22
    kv_x, kv_y0 = PAD_X + 16, ry + 28
    kv_rows = [
        ("followers", fmt(d.get("followers", 0))),
        ("forks", fmt(d.get("forks", 0))),
        ("member since", f"{since:%b %Y}"),
        ("accounts", fmt(n_accounts) if n_accounts else "—"),
    ]
    kv = "\n  ".join(dotted_kv(kv_x, kv_y0 + i * 28, k, v) for i, (k, v) in enumerate(kv_rows))
    parts.append(
        f'<g class="ln" style="animation-delay:.4s">\n'
        f'  {corners(PAD_X, ry, lw, rh)}\n'
        f'  {kv}\n'
        f'</g>'
    )

    lx = PAD_X + lw + gap2
    lwid = WIDTH - PAD_X - lx
    langs = sorted((d.get("languages") or {}).items(), key=lambda item: -item[1])
    total = sum(v for _, v in langs)
    palette = [GREEN, "#1ec81e", "#14b814", "#0e8a0e", "#2a8a2a", "#3a6a3a"]
    if total:
        top = langs[:6]
        other = total - sum(v for _, v in top)
        if other > 0 and len(top) == 6:
            items = [(k, v / total) for k, v in top[:5]] + [("Other", (top[5][1] + other) / total)]
        elif other > 0:
            items = [(k, v / total) for k, v in top] + [("Other", other / total)]
        else:
            items = [(k, v / total) for k, v in top]
        bx, by, bw = lx + 16, ry + 40, lwid - 32
        segs, cx = [], bx
        for (k, pct), c in zip(items, palette):
            w = max(bw * pct, 1.5)
            if cx + w > bx + bw:
                w = max(bx + bw - cx, 1)
            segs.append(f'<rect x="{cx:.1f}" y="{by}" width="{w:.1f}" height="10" fill="{c}"/>')
            cx += w
        legend = []
        col_w = bw / 2
        for i, ((k, pct), c) in enumerate(zip(items, palette)):
            col, row = i % 2, i // 2
            lxx = bx + col * col_w
            lyy = by + 32 + row * 20
            legend.append(
                f'<rect x="{lxx}" y="{lyy - 8}" width="8" height="8" fill="{c}"/>'
                f'<text x="{lxx + 14}" y="{lyy}" class="fg" style="font-size:12px">{e(k)}</text>'
                f'<text x="{lxx + col_w - 6}" y="{lyy}" text-anchor="end" class="muted" style="font-size:12px">{pct * 100:.1f}%</text>'
            )
        lang_inner = (
            f'<text class="label" x="{lx + 16}" y="{ry + 22}" letter-spacing="1.2">TOP LANGUAGES</text>'
            f'<rect x="{bx}" y="{by}" width="{bw}" height="10" fill="#061006"/>'
            + "".join(segs) + "".join(legend)
        )
    else:
        lang_inner = (
            f'<text class="label" x="{lx + 16}" y="{ry + 22}" letter-spacing="1.2">TOP LANGUAGES</text>'
            f'<text class="muted" x="{lx + 16}" y="{ry + 56}"># no language data yet</text>'
        )
    parts.append(
        f'<g class="ln" style="animation-delay:.5s">\n'
        f'  {corners(lx, ry, lwid, rh)}\n'
        f'  {lang_inner}\n'
        f'</g>'
    )

    fy = ry + rh + 20
    parts.append(
        f'<text x="{WIDTH - PAD_X}" y="{fy}" text-anchor="end" class="muted" style="font-size:11px">'
        f'// last sync {e(d["updated"])}</text>'
    )
    height = fy + PAD_BOT
    desc = (
        f"GitHub stats: {d.get('stars', 0)} total stars; "
        f"{cy} contributions in {year}, {ca} all time; "
        f"{d.get('prs', 0)} pull requests ({d.get('prs_merged', 0)} merged); "
        f"current streak {_days(d.get('streak_current', 0))}, longest {_days(d.get('streak_longest', 0))}; "
        f"{_followers(d.get('followers', 0))}; member since {since:%B %Y}."
    )
    if n_accounts:
        desc += f" Aggregated across {n_accounts} accounts."
    if langs:
        desc += " Top languages: " + ", ".join(k for k, _ in langs[:5]) + "."
    extra = "    .ln { opacity: 1; }\n"
    return (
        terminal_open(int(math.ceil(height)), "stats", "GitHub stats", desc, extra_css=extra)
        + "\n".join(parts)
        + terminal_close()
    )


# ─────────────────────────── contribution city ────────────────────────
# Algorithm adapted from georgekobaidze/georgekobaidze (MIT). Palette retinted
# to the header greens; origin/scale fitted to the 800px terminal well.
CITY_TW, CITY_TH = 22.0, 11.0
CITY_HMAX = 110
ROOFS = ["#0a3a0a", "#127a12", "#1ec81e", "#39ff14"]
WIN_ON, WIN_ON_SIDE, WIN_OFF = "#39ff14", "#1a8a1a", "#061006"


def _shade(hexc, f):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def _p(x, y):
    return f"{x:.1f},{y:.1f}"


def _rng(seed):
    state = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        yield (state >> 11) / 2**53


def _levels(counts):
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return [1, 1, 1]
    q = lambda f: nz[min(len(nz) - 1, int(len(nz) * f))]
    return [q(0.25), q(0.5), q(0.75)]


def build_city(calendar, updated) -> str:
    days = [(datetime.date.fromisoformat(d), n) for d, n in calendar]
    counts = [n for _, n in days]
    total, peak = sum(counts), max(counts) if counts else 0
    lv = _levels(counts)
    rnd = _rng(f"{updated}-{total}")
    start = days[0][0] if days else datetime.date.today()

    # Center the 53-week iso grid in the 800px window.
    # leftmost (w=0, dow=6): ox - 3*TW; rightmost (w=52, dow=0): ox + 26*TW
    ox = WIDTH / 2 - 11.5 * CITY_TW
    # leave room above the back of the grid for the prompt and the tallest roof
    prompt_bottom = TITLE_H + 36
    oy = prompt_bottom + 16 + CITY_HMAX + CITY_TH / 2

    cells = []
    for d, n in days:
        idx = (d - start).days
        cells.append((idx // 7, (d.weekday() + 1) % 7, n))
    cells.sort(key=lambda c: (c[0] + c[1], c[0]))

    shapes, flick = [], 0
    for w, dow, n in cells:
        cx = ox + (w - dow) * CITY_TW / 2
        cy = oy + (w + dow) * CITY_TH / 2
        L, R = (cx - CITY_TW / 2, cy), (cx + CITY_TW / 2, cy)
        T, B = (cx, cy - CITY_TH / 2), (cx, cy + CITY_TH / 2)
        if n == 0:
            shapes.append(
                f'<path d="M{_p(*T)}L{_p(*R)}L{_p(*B)}L{_p(*L)}Z" fill="#0a140a" stroke="#061006" stroke-width=".6"/>'
            )
            continue
        h = 8 + (CITY_HMAX - 8) * math.sqrt(n / peak) if peak else 8
        level = sum(n > t for t in lv)
        Tu, Ru, Bu, Lu = [(x, y - h) for x, y in (T, R, B, L)]
        shapes.append(
            f'<path d="M{_p(*L)}L{_p(*B)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="#0a2410"/>'
            f'<path d="M{_p(*B)}L{_p(*R)}L{_p(*Ru)}L{_p(*Bu)}Z" fill="#06180a"/>'
            f'<path d="M{_p(*Tu)}L{_p(*Ru)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="{ROOFS[level]}"/>'
        )
        on, side, off, fl = [], [], [], []
        for face, (a, b) in (("l", (L, B)), ("r", (B, R))):
            for r in range(int((h - 6) // 7)):
                v0 = 5 + r * 7
                for u0 in (0.18, 0.58):
                    lit = next(rnd) < 0.55
                    if not lit and next(rnd) < 0.5:
                        continue
                    pts = [
                        (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - v)
                        for u, v in ((u0, v0), (u0 + 0.26, v0), (u0 + 0.26, v0 + 3.2), (u0, v0 + 3.2))
                    ]
                    seg = "M" + "L".join(_p(*q) for q in pts) + "Z"
                    if not lit:
                        off.append(seg)
                    elif next(rnd) < 0.03:
                        fl.append((seg, face))
                    else:
                        (on if face == "l" else side).append(seg)
        if off:
            shapes.append(f'<path d="{"".join(off)}" fill="{WIN_OFF}"/>')
        if on:
            shapes.append(f'<path d="{"".join(on)}" fill="{WIN_ON}"/>')
        if side:
            shapes.append(f'<path d="{"".join(side)}" fill="{WIN_ON_SIDE}"/>')
        for seg, face in fl:
            flick += 1
            shapes.append(
                f'<path class="f{flick % 3}" d="{seg}" fill="{WIN_ON if face == "l" else WIN_ON_SIDE}"/>'
            )

    # stars in the upper sky (no moon/plane — kept quieter to match the header)
    stars = []
    for i in range(36):
        x, y = 40 + next(rnd) * 720, TITLE_H + 40 + next(rnd) * 90
        cls = f' class="s{i % 3}"' if i % 3 == 0 else ""
        stars.append(
            f'<circle{cls} cx="{x:.1f}" cy="{y:.1f}" r="{(0.5, 0.7, 1.0)[i % 3]}" fill="{GREEN}" opacity="{0.15 + next(rnd) * 0.35:.2f}"/>'
        )

    front_y = oy + (52 + 6) * CITY_TH / 2 + CITY_TH / 2
    legend_y = front_y + 28
    busiest_d, busiest_n = max(days, key=lambda t: t[1]) if days else (None, 0)
    info = [
        f'<tspan fill="{GREEN}">{total:,}</tspan> contributions · last 365 days',
        (
            f'busiest day <tspan fill="{GREEN}">{busiest_d:%b} {busiest_d.day}</tspan> · {busiest_n}'
            if busiest_n
            else ""
        ),
        f'{sum(1 for n in counts if n)} active days',
    ]
    info_svg = "".join(
        f'<text x="{WIDTH - PAD_X}" y="{TITLE_H + 58 + i * 16}" text-anchor="end" class="muted" style="font-size:11px">{t}</text>'
        for i, t in enumerate(info)
        if t
    )
    legend = "".join(
        f'<rect x="{PAD_X + 48 + i * 16}" y="{legend_y - 10}" width="11" height="11" fill="{c}"/>'
        for i, c in enumerate(["#0a140a"] + ROOFS)
    )
    body = f'''{prompt_row(TITLE_H + 16, "render-city --last 365d", "one building per day", cursor=False)}
<g>{"".join(stars)}</g>
{info_svg}
{"".join(shapes)}
<text x="{PAD_X}" y="{legend_y}" class="muted" style="font-size:11px">quiet</text>
{legend}
<text x="{PAD_X + 48 + 5 * 16 + 8}" y="{legend_y}" class="muted" style="font-size:11px">skyscraper</text>
'''
    css = """
    @keyframes tw { 0%,100% { opacity: .9; } 50% { opacity: .15; } }
    @keyframes fl { 0%,40%,100% { opacity: 1; } 45%,60% { opacity: .1; } }
    .s0 { animation: tw 3s infinite; }
    .f0 { animation: fl 5s infinite; }
    .f1 { animation: fl 7s infinite 2s; }
    .f2 { animation: fl 9s infinite 4s; }
    """
    desc = (
        f"Contribution city: an isometric skyline with one building per day of the last year, "
        f"taller and brighter for busier days. {total:,} contributions"
        + (f", busiest day {busiest_d:%B} {busiest_d.day} with {busiest_n}" if busiest_n else "")
        + "."
    )
    height = int(math.ceil(legend_y + PAD_BOT + 8))
    return terminal_open(height, "contribution-city", "Contribution city", desc, extra_css=css) + body + terminal_close()


# ─────────────────────────────── skills ────────────────────────────────
def build_skills() -> str:
    """Terminal chrome around the unchanged 54-icon grid in assets/skills/skills.svg."""
    src = (OUT / "skills" / "skills.svg").read_text(encoding="utf-8")
    # Pull the existing style (tile-in, .prompt, .tile) and the body after </defs>.
    style_m = re.search(r"<style[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</style>", src, re.S)
    grid_css = style_m.group(1).strip() if style_m else ""
    body_m = re.search(r"</defs>\s*(.*)</svg>\s*$", src, re.S)
    if not body_m:
        raise SystemExit("assets/skills/skills.svg has an unexpected structure")
    inner = body_m.group(1).strip()
    # The grid already includes `$ ls ~/stack` and 42px of top padding; sit it
    # directly under the title bar.
    height = TITLE_H + 234 + PAD_BOT
    body = f'<g transform="translate(0, {TITLE_H})">\n{inner}\n    </g>\n'
    return terminal_open(
        height,
        "stack",
        "Tools and stack",
        "Tools I know — 54-icon grid.",
        extra_css=grid_css,
    ) + body + terminal_close()


# ────────────────────────────── projects ──────────────────────────────
def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"


def build_projects_head(n: int) -> str:
    height = TITLE_H + 22 + 36 + PAD_BOT
    empty = ""
    if n == 0:
        empty = (
            f'<text class="muted" x="{PAD_X + 8}" y="{TITLE_H + 44}" '
            f'text-anchor="start" dominant-baseline="middle"># no projects listed yet</text>'
        )
    body = prompt_row(TITLE_H + 16, "ls -l ~/projects") + empty
    return terminal_open(int(height), "projects", "Projects", "Projects") + body + terminal_close()


def build_card(p: dict) -> str:
    """A half-width (400px) terminal-styled project card."""
    w, h = 400, 200
    name = p["name"]
    desc = p.get("description") or ""
    langs = p.get("languages") or []
    lang = " · ".join(langs)
    lines = textwrap.wrap(desc, 42)[:4]
    desc_svg = "\n".join(
        f'<text class="fg" x="16" y="{88 + i * 18}" style="font-size:13px">{e(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"
     role="img" aria-label="{e(name)}">
  <title>{e(name)}</title>
  <defs>
    <style type="text/css"><![CDATA[
{base_css()}
    ]]></style>
  </defs>
  <rect x="0.75" y="0.75" width="{w-1.5}" height="{h-1.5}" rx="{RADIUS}" ry="{RADIUS}"
        fill="{BG}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
  <rect x="1" y="1" width="{w-2}" height="{TITLE_H}" rx="{RADIUS}" ry="{RADIUS}" fill="{CHROME}"/>
  <rect x="1" y="{TITLE_H-4}" width="{w-2}" height="4" fill="{CHROME}"/>
  <line x1="1" y1="{TITLE_H}" x2="{w-1}" y2="{TITLE_H}" stroke="{CHROME_LINE}" stroke-width="1"/>
  <circle cx="16" cy="{TITLE_H/2}" r="4" fill="#ff5f56"/>
  <circle cx="30" cy="{TITLE_H/2}" r="4" fill="#ffbd2e"/>
  <circle cx="44" cy="{TITLE_H/2}" r="4" fill="#27c93f"/>
  <text class="chrome-title" x="{w/2}" y="{TITLE_H/2 + 1}" text-anchor="middle"
        dominant-baseline="middle">{e(name)}</text>
  <text class="prompt" x="16" y="52">$ cat README</text>
  {desc_svg}
  <text class="muted" x="16" y="{h-20}">{e(lang)}</text>
</svg>
'''


# ─────────────────────────────── footer ────────────────────────────────
def build_footer() -> str:
    height = TITLE_H + 22 + 48 + PAD_BOT
    body = (
        prompt_row(TITLE_H + 16, "exit", cursor=False)
        + f'<text class="fg" x="{PAD_X + 8}" y="{TITLE_H + 48}" style="font-size:13px">'
        f'Connection closed.</text>'
    )
    return terminal_open(int(height), "session", "Connection closed.", "Connection closed.") + body + terminal_close()


# ──────────────────────────────── main ─────────────────────────────────
def write(rel: str, svg: str) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def load_projects() -> list[dict]:
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        raise SystemExit("tools/profile/projects.json must be a list")
    out = []
    for i, p in enumerate(data):
        if not isinstance(p, dict) or not p.get("name"):
            raise SystemExit(f"projects.json[{i}] needs at least a name")
        out.append({
            "name": p["name"],
            "url": p.get("url") or "",
            "description": p.get("description") or "",
            "languages": list(p.get("languages") or []),
            "slug": p.get("slug") or slugify(p["name"]),
        })
    return out


def main() -> None:
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=pathlib.Path, default=DATA)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()
    OUT = args.out

    stats_path = args.data / "stats.json"
    if not stats_path.exists():
        raise SystemExit("missing data/stats.json — run fetch.py first")
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    projects = load_projects()

    # Never touch assets/header.svg — that is the approved v13 header.
    write("stats.svg", build_stats(stats))
    cal_file = args.data / "calendar.json"
    if cal_file.exists():
        write("contribution-city.svg", build_city(json.loads(cal_file.read_text()), stats["updated"]))
    write("skills.svg", build_skills())
    write("projects.svg", build_projects_head(len(projects)))
    # Remove stale cards, then write only current ones.
    for stale in OUT.glob("card-*.svg"):
        stale.unlink()
    for p in projects:
        write(f"card-{p['slug']}.svg", build_card(p))
    write("footer.svg", build_footer())
    print("header.svg left untouched")
    print("rendered into", OUT)


if __name__ == "__main__":
    main()
