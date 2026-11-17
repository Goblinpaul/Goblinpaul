#!/usr/bin/env python3
"""Official-color stack tiles, terminal chrome, and the combined skills grid.

Logos come from assets/skills/icons/ — official brand marks (Devicon,
Simple Icons, or the brand's press kit). This module never tints or
luminance-lifts those colors. Near-black official marks already use the
brand's official light/white (or reversed) variant so they read on the
dark tile.
"""
from __future__ import annotations

import html
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ICONS = ROOT / "assets" / "skills" / "icons"
SKILLS_DIR = ROOT / "assets" / "skills"
TILES = SKILLS_DIR / "tiles"

# Approved 54-icon set, approved order (16 per row).
TOOLS: list[tuple[str, str]] = [
    # Row 1 — languages, JS ecosystem, OS / core infra
    ("Python", "python"),
    ("JavaScript", "javascript"),
    ("TypeScript", "typescript"),
    ("HTML", "html5"),
    ("CSS", "css"),
    ("Bash", "bash"),
    ("PHP", "php"),
    ("Node.js", "nodedotjs"),
    ("npm", "npm"),
    ("React", "react"),
    ("Next.js", "nextdotjs"),
    ("Linux", "linux"),
    ("Windows", "windows"),
    ("Terminal", "windowsterminal"),
    ("Docker", "docker"),
    ("Traefik", "traefikproxy"),
    # Row 2 — infra, cloud, data, AI start
    ("Portainer", "portainer"),
    ("Nginx", "nginx"),
    ("Tailscale", "tailscale"),
    ("Cloudflare", "cloudflare"),
    ("AWS", "amazonaws"),
    ("Google Cloud", "googlecloud"),
    ("Hostinger", "hostinger"),
    ("Vercel", "vercel"),
    ("PostgreSQL", "postgresql"),
    ("MySQL", "mysql"),
    ("MongoDB", "mongodb"),
    ("SQLite", "sqlite"),
    ("Redis", "redis"),
    ("Supabase", "supabase"),
    ("RabbitMQ", "rabbitmq"),
    ("OpenAI", "openai"),
    # Row 3 — AI, vcs, automation, apps
    ("Claude", "claude"),
    ("Grok", "grok"),
    ("Cursor", "cursor"),
    ("Hugging Face", "huggingface"),
    ("Meta", "meta"),
    ("Git", "git"),
    ("GitHub", "github"),
    ("GitHub Actions", "githubactions"),
    ("n8n", "n8n"),
    ("Make", "make"),
    ("Zapier", "zapier"),
    ("Postman", "postman"),
    ("Playwright", "playwright"),
    ("VS Code", "visualstudiocode"),
    ("Nextcloud", "nextcloud"),
    ("WordPress", "wordpress"),
    # Row 4 — remaining apps + suite marks
    ("WooCommerce", "woocommerce"),
    ("Metabase", "metabase"),
    ("Figma", "figma"),
    ("Canva", "canva"),
    ("Adobe Creative Cloud", "adobecreativecloud"),
    ("Microsoft 365", "microsoft365"),
]

TILE = 40
GAP = 6
COLS = 16
PAD_X = 35  # (800 - (16*40 + 15*6)) / 2
PAD_TOP = 12
HEADER_H = 20
HEADER_GAP = 10
PAD_BOTTOM = 14
INNER = 26
INNER_PAD = 7
RX = 8
WIDTH = 800
ROWS = math.ceil(len(TOOLS) / COLS)
GRID_H = ROWS * TILE + (ROWS - 1) * GAP
GRID_Y0 = PAD_TOP + HEADER_H + HEADER_GAP
HEIGHT = GRID_Y0 + GRID_H + PAD_BOTTOM  # 234

# Terminal chrome — same as the other README slices.
RADIUS, TITLE_H = 10, 28
BG, CHROME, CHROME_LINE = "#020400", "#0a1c0a", "#1a5a1a"
GREEN, DIM = "#39ff14", "#2a8a2a"
TILE_BG, TILE_BORDER = "#111a11", "#1a3a1a"
FONT = '"Courier New", Courier, ui-monospace, "Liberation Mono", monospace'

# Entrance stagger: last tile starts at 0.85s, each fade/scale is 0.35s,
# so the whole grid is fully lit by 1.20s. Default opacity is 1 so a
# renderer that skips CSS animation still shows every tile.
ANIM_DURATION = 0.35
ANIM_DONE = 1.20
ANIM_LAST_DELAY = round(ANIM_DONE - ANIM_DURATION, 4)
ANIM_STEP = ANIM_LAST_DELAY / max(len(TOOLS) - 1, 1)


def delay_for(index: int) -> float:
    return round(index * ANIM_STEP, 4)


def tile_style(index: int) -> str:
    delay = delay_for(index)
    return f"""
      .stage {{
        transform-box: fill-box;
        transform-origin: 20px 20px;
        opacity: 1;
        animation: enter {ANIM_DURATION:.2f}s ease-out {delay:.4f}s both;
      }}
      @keyframes enter {{
        from {{ opacity: 0; transform: scale(0.86); }}
        to   {{ opacity: 1; transform: scale(1); }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        .stage {{ animation: none !important; opacity: 1; transform: none; }}
      }}
"""


NESTED_RE = re.compile(
    r'<svg\s+x="7"\s+y="7"\s+width="26"\s+height="26"\s+'
    r'viewBox="([^"]+)"([^>]*)>(.*)</svg>\s*</g>\s*</svg>\s*$',
    re.I | re.S,
)


def split_icon(slug: str) -> tuple[str, str, str]:
    """Return (viewBox, wrapper attrs, inner XML) from an official tile."""
    path = ICONS / f"{slug}.svg"
    if not path.exists():
        raise SystemExit(f"missing official icon: {path}")
    raw = path.read_text(encoding="utf-8")
    m = NESTED_RE.search(raw)
    if not m:
        raise SystemExit(f"unexpected official icon structure: {path}")
    vb, attrs, inner = m.group(1), m.group(2).strip(), m.group(3)
    return vb, attrs, inner


def prefix_ids(xml: str, prefix: str) -> str:
    """Prefix paint-server ids so many logos can share one SVG."""
    ids = set(re.findall(r'\bid="([^"]+)"', xml))
    ids |= set(re.findall(r"\bid='([^']+)'", xml))
    for ident in sorted(ids, key=len, reverse=True):
        xml = xml.replace(f'id="{ident}"', f'id="{prefix}{ident}"')
        xml = xml.replace(f"id='{ident}'", f"id='{prefix}{ident}'")
        xml = xml.replace(f"url(#{ident})", f"url(#{prefix}{ident})")
        xml = xml.replace(f'href="#{ident}"', f'href="#{prefix}{ident}"')
        xml = xml.replace(f"href='#{ident}'", f"href='#{prefix}{ident}'")
        xml = xml.replace(f'xlink:href="#{ident}"', f'xlink:href="#{prefix}{ident}"')
        xml = xml.replace(f"xlink:href='#{ident}'", f"xlink:href='#{prefix}{ident}'")
    return xml


def make_tile(name: str, slug: str, index: int) -> str:
    """Standard 40×40 tile with the official logo and a staggered entrance."""
    raw = (ICONS / f"{slug}.svg").read_text(encoding="utf-8")
    style = f'<style type="text/css"><![CDATA[{tile_style(index)}    ]]></style>'
    out = re.sub(r"<style\b[^>]*>.*?</style>", style, raw, count=1, flags=re.S)
    if out == raw:
        raise SystemExit(f"could not update animation in {slug}.svg")
    return out


def combined_grid_css() -> str:
    lines = [
        "      .prompt {",
        f"        fill: {GREEN};",
        "        font-size: 13px;",
        "        font-weight: 400;",
        f"        font-family: {FONT};",
        "      }",
        "      .tile {",
        "        opacity: 1;",
        f"        animation: tile-in {ANIM_DURATION:.2f}s ease-out both,",
        f"                   tile-lock 0s linear {ANIM_DONE:.2f}s forwards;",
        "        transform-box: fill-box;",
        "        transform-origin: 20px 20px;",
        "      }",
        "      @keyframes tile-in {",
        "        from { opacity: 0; transform: scale(0.86); }",
        "        to   { opacity: 1; transform: scale(1); }",
        "      }",
        "      @keyframes tile-lock {",
        "        to { opacity: 1; transform: none; }",
        "      }",
        "      @media (prefers-reduced-motion: reduce) {",
        "        .tile { animation: none; opacity: 1; transform: none; }",
        "      }",
    ]
    for i in range(len(TOOLS)):
        lines.append(
            f"      .t{i} {{ animation-delay: {delay_for(i):.4f}s, {ANIM_DONE:.2f}s; }}"
        )
    return "\n".join(lines)


def build_combined_skills() -> str:
    """Inner 800×234 grid (prompt + official logos). Used by assets/skills.svg."""
    chunks: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-label="Tools I know">',
        "  <title>Tools I know</title>",
        "  <defs>",
        '    <style type="text/css"><![CDATA[',
        combined_grid_css(),
        "    ]]></style>",
        "  </defs>",
        "",
        f'  <text class="prompt" x="{PAD_X}" y="{PAD_TOP + 13}">$ ls ~/stack</text>',
        "",
    ]
    for i, (name, slug) in enumerate(TOOLS):
        col, row = i % COLS, i // COLS
        x = PAD_X + col * (TILE + GAP)
        y = GRID_Y0 + row * (TILE + GAP)
        vb, attrs, inner = split_icon(slug)
        inner = prefix_ids(inner, f"{slug}-")
        attrs = prefix_ids(attrs, f"{slug}-")
        # Drop preserveAspectRatio from the source attrs; we always set it.
        attrs = re.sub(r'\s*preserveAspectRatio="[^"]*"', "", attrs).strip()
        wrapper = (" " + attrs) if attrs else ""
        safe = html.escape(name)
        chunks.append(f'  <g class="tile t{i}" transform="translate({x},{y})">')
        chunks.append(f"    <title>{safe}</title>")
        chunks.append(
            f'    <rect x="0.5" y="0.5" width="39" height="39" rx="{RX}" ry="{RX}" '
            f'fill="{TILE_BG}" stroke="{TILE_BORDER}" stroke-width="1"/>'
        )
        chunks.append(
            f'    <svg x="{INNER_PAD}" y="{INNER_PAD}" width="{INNER}" height="{INNER}" '
            f'viewBox="{vb}" preserveAspectRatio="xMidYMid meet"{wrapper}>'
        )
        chunks.append(inner)
        chunks.append("    </svg>")
        chunks.append("  </g>")
    chunks.append("</svg>")
    return "\n".join(chunks) + "\n"


def build_stack_top() -> str:
    """Terminal chrome + `$ ls ~/stack` prompt; open at the bottom."""
    body_h = GRID_Y0  # 42 — prompt band plus gap above the first icon row
    height = TITLE_H + body_h
    # Taller rounded rect, clipped by the viewBox, so the bottom edge is
    # open and the side strokes continue into the icon rows.
    over = height + RADIUS + 16
    prompt_y = TITLE_H + PAD_TOP + 13
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}"
     viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Tools I know">
  <title>stack</title>
  <defs>
    <clipPath id="term">
      <path d="M0,{height} L0,{RADIUS} Q0,0 {RADIUS},0 L{WIDTH - RADIUS},0
               Q{WIDTH},0 {WIDTH},{RADIUS} L{WIDTH},{height} Z"/>
    </clipPath>
    <style type="text/css"><![CDATA[
      .chrome-title {{
        fill: {DIM};
        font-size: 11px;
        font-family: {FONT};
      }}
      .prompt {{
        fill: {GREEN};
        font-size: 13px;
        font-family: {FONT};
      }}
    ]]></style>
  </defs>
  <rect x="0" y="0" width="{WIDTH}" height="{over}" rx="{RADIUS}" ry="{RADIUS}"
        fill="{BG}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
  <g clip-path="url(#term)">
    <rect x="0" y="0" width="{WIDTH}" height="{TITLE_H}" fill="{CHROME}"/>
    <line x1="0" y1="{TITLE_H}" x2="{WIDTH}" y2="{TITLE_H}" stroke="{CHROME_LINE}" stroke-width="1"/>
    <circle cx="18" cy="{TITLE_H / 2}" r="5" fill="#ff5f56"/>
    <circle cx="36" cy="{TITLE_H / 2}" r="5" fill="#ffbd2e"/>
    <circle cx="54" cy="{TITLE_H / 2}" r="5" fill="#27c93f"/>
    <text class="chrome-title" x="{WIDTH / 2}" y="{TITLE_H / 2 + 1}"
          text-anchor="middle" dominant-baseline="middle">stack</text>
    <text class="prompt" x="{PAD_X}" y="{prompt_y}">$ ls ~/stack</text>
  </g>
</svg>
'''


def build_stack_bottom() -> str:
    """Closes the terminal frame under the icon rows."""
    height = PAD_BOTTOM
    # Rect starts above the viewBox so only the rounded bottom is visible.
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}"
     viewBox="0 0 {WIDTH} {height}" role="img" aria-label="">
  <rect x="0" y="{-RADIUS - 16}" width="{WIDTH}" height="{height + RADIUS + 16}"
        rx="{RADIUS}" ry="{RADIUS}"
        fill="{BG}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
</svg>
'''


def build_side_cap(side: str) -> str:
    """35×40 cap that carries the window's left or right stroke through a row."""
    x = 0 if side == "left" else PAD_X
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{PAD_X}" height="{TILE}"
     viewBox="0 0 {PAD_X} {TILE}" role="img" aria-label="">
  <rect x="0" y="0" width="{PAD_X}" height="{TILE}" fill="{BG}"/>
  <line x1="{x}" y1="0" x2="{x}" y2="{TILE}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
</svg>
'''


def build_gap() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{GAP}" height="{TILE}"
     viewBox="0 0 {GAP} {TILE}" role="img" aria-label="">
  <rect width="{GAP}" height="{TILE}" fill="{BG}"/>
</svg>
'''


def build_vgap() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{GAP}"
     viewBox="0 0 {WIDTH} {GAP}" role="img" aria-label="">
  <rect width="{WIDTH}" height="{GAP}" fill="{BG}"/>
  <line x1="0" y1="0" x2="0" y2="{GAP}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
  <line x1="{WIDTH}" y1="0" x2="{WIDTH}" y2="{GAP}" stroke="{CHROME_LINE}" stroke-width="1.5"/>
</svg>
'''


def tool_rows() -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for item in TOOLS:
        row.append(item)
        if len(row) == COLS:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def stack_block() -> str:
    """README HTML between <!-- stack:start --> and <!-- stack:end -->."""
    rows = tool_rows()
    lines = [
        "<!-- stack:start -->",
        '<div align="center">',
        f'<table align="center" border="0" cellpadding="0" cellspacing="0" width="{WIDTH}" bgcolor="{BG}">',
        "<tr>",
        f'<td colspan="3"><img src="./assets/skills/stack-top.svg" width="{WIDTH}" align="top" alt="Tools I know."></td>',
        "</tr>",
    ]
    left = (
        f'<img src="./assets/skills/stack-left.svg" width="{PAD_X}" height="{TILE}" align="top" alt="">'
    )
    right = (
        f'<img src="./assets/skills/stack-right.svg" width="{PAD_X}" height="{TILE}" align="top" alt="">'
    )
    gap = (
        f'<img src="./assets/skills/stack-gap.svg" width="{GAP}" height="{TILE}" align="top" alt="">'
    )
    mid_w = WIDTH - 2 * PAD_X
    for i, row in enumerate(rows):
        if i:
            lines.append("<tr>")
            lines.append(
                f'<td colspan="3"><img src="./assets/skills/stack-vgap.svg" width="{WIDTH}" height="{GAP}" align="top" alt=""></td>'
            )
            lines.append("</tr>")
        parts: list[str] = []
        for j, (name, slug) in enumerate(row):
            if j:
                parts.append(gap)
            safe = html.escape(name, quote=True)
            parts.append(
                f'<img src="./assets/skills/tiles/{slug}.svg" width="{TILE}" height="{TILE}" '
                f'align="top" alt="{safe}" title="{safe}">'
            )
        lines.append("<tr>")
        lines.append(f'<td width="{PAD_X}" bgcolor="{BG}">{left}</td>')
        lines.append(f'<td width="{mid_w}" align="left" bgcolor="{BG}">{"".join(parts)}</td>')
        lines.append(f'<td width="{PAD_X}" bgcolor="{BG}">{right}</td>')
        lines.append("</tr>")
    lines += [
        "<tr>",
        f'<td colspan="3"><img src="./assets/skills/stack-bottom.svg" width="{WIDTH}" align="top" alt=""></td>',
        "</tr>",
        "</table>",
        "</div>",
        "<!-- stack:end -->",
    ]
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    print(f"  wrote {rel} ({path.stat().st_size} bytes)")


def write_stack(out_root: Path | None = None) -> None:
    """Write tiles, chrome pieces, and the combined official-color grid."""
    skills_dir = (out_root / "skills") if out_root is not None else SKILLS_DIR
    tiles_dir = skills_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    # Drop stale tiles (e.g. leftover individual Adobe/Office marks).
    for stale in tiles_dir.glob("*.svg"):
        stale.unlink()

    missing = [slug for _n, slug in TOOLS if not (ICONS / f"{slug}.svg").exists()]
    if missing:
        raise SystemExit(f"missing official icons: {', '.join(missing)}")
    if len(TOOLS) != 54 or len({s for _n, s in TOOLS}) != 54:
        raise SystemExit(f"expected 54 unique tools, got {len(TOOLS)}")

    for i, (name, slug) in enumerate(TOOLS):
        write_text(tiles_dir / f"{slug}.svg", make_tile(name, slug, i))

    write_text(skills_dir / "stack-top.svg", build_stack_top())
    write_text(skills_dir / "stack-bottom.svg", build_stack_bottom())
    write_text(skills_dir / "stack-left.svg", build_side_cap("left"))
    write_text(skills_dir / "stack-right.svg", build_side_cap("right"))
    write_text(skills_dir / "stack-gap.svg", build_gap())
    write_text(skills_dir / "stack-vgap.svg", build_vgap())
    write_text(skills_dir / "skills.svg", build_combined_skills())
    print(f"stack: {len(TOOLS)} official-color tiles")


def main() -> None:
    write_stack()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
