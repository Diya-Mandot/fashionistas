"""Render the demo closet's garment illustrations as SVGs.

Run from backend/:  uv run python seed_images/render.py
Output is committed, so the demo never depends on network image hosts.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.seed import art_manifest  # noqa: E402

BG = "#F7F2EA"

COLOR_HEX = {
    "white": "#F5F2EC",
    "black": "#232323",
    "heather grey": "#A3A3A0",
    "grey": "#8E9196",
    "navy stripe": "#26344D",
    "sage": "#9CAF94",
    "dark denim": "#2F4262",
    "light denim": "#7F9EC2",
    "camel": "#C49A6C",
    "emerald": "#1F8A5B",
    "charcoal": "#3C3E42",
    "tan": "#B98A5E",
    "gold": "#C9A24A",
    "silver": "#B9BDC3",
}


def shade(hex_color: str, factor: float) -> str:
    """factor < 1 darkens, > 1 lightens."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    if factor < 1:
        r, g, b = (int(c * factor) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * (factor - 1)) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def is_light(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 170


# Each art kind returns SVG markup given fill (f), outline (o) and detail (d) colors.
LONG_SLEEVE_BODY = (
    "M130,118 L170,96 Q200,112 230,96 L270,118 L304,140 L322,330 L292,336 "
    "L280,196 L280,392 L120,392 L120,196 L108,336 L78,330 L96,140 Z"
)


def _body(path: str, f: str, o: str) -> str:
    return f'<path d="{path}" fill="{f}" stroke="{o}" stroke-width="2" stroke-linejoin="round"/>'


def art_tee(f, o, d, stripes=False):
    p = "M122,112 L168,92 Q200,114 232,92 L278,112 L322,162 L288,190 L270,172 L270,384 L130,384 L130,172 L112,190 L78,162 Z"
    s = _body(p, f, o)
    if stripes:
        s += '<clipPath id="c"><path d="' + p + '"/></clipPath><g clip-path="url(#c)">'
        s += "".join(f'<rect x="60" y="{y}" width="280" height="9" fill="#F5F2EC"/>' for y in range(140, 384, 26))
        s += "</g>" + _body(p, "none", o)
    s += f'<path d="M168,92 Q200,128 232,92" fill="none" stroke="{d}" stroke-width="3"/>'
    return s


def art_shirt(f, o, d):
    s = _body(LONG_SLEEVE_BODY, f, o)
    s += f'<path d="M170,96 L200,140 L184,152 L160,108 Z M230,96 L200,140 L216,152 L240,108 Z" fill="{shade(f, 0.93) if is_light(f) else shade(f, 1.12)}" stroke="{o}" stroke-width="1.5"/>'
    s += f'<line x1="200" y1="140" x2="200" y2="392" stroke="{d}" stroke-width="2"/>'
    s += "".join(f'<circle cx="207" cy="{y}" r="3.2" fill="{d}"/>' for y in range(170, 392, 42))
    s += f'<path d="M292,336 L322,330 M78,330 L108,336" stroke="{d}" stroke-width="5"/>'
    return s


def art_sweater(f, o, d, mock=False):
    s = _body(LONG_SLEEVE_BODY, f, o)
    if mock:
        s += f'<rect x="172" y="74" width="56" height="30" rx="8" fill="{shade(f, 1.12)}" stroke="{o}" stroke-width="2"/>'
    else:
        s += f'<path d="M170,96 Q200,124 230,96" fill="none" stroke="{d}" stroke-width="6"/>'
    s += "".join(f'<line x1="{x}" y1="374" x2="{x}" y2="392" stroke="{d}" stroke-width="1.5"/>' for x in range(126, 280, 8))
    s += f'<path d="M290,322 L321,316 M79,316 L110,322" stroke="{d}" stroke-width="8"/>'
    return s


def art_cami(f, o, d):
    s = f'<path d="M160,140 L172,82 M240,140 L228,82" stroke="{o}" stroke-width="3"/>'
    s += _body("M150,140 Q175,128 200,160 Q225,128 250,140 L278,384 L122,384 Z", f, o)
    s += f'<path d="M150,140 Q175,128 200,160 Q225,128 250,140" fill="none" stroke="{shade(f, 1.4)}" stroke-width="2"/>'
    return s


def art_tank(f, o, d):
    p = "M150,92 L176,92 Q200,140 224,92 L250,92 Q252,150 282,172 L282,384 L118,384 L118,172 Q148,150 150,92 Z"
    s = _body(p, f, o)
    s += f'<path d="M176,92 Q200,140 224,92" fill="none" stroke="{shade(f, 1.35)}" stroke-width="2"/>'
    return s


def art_trousers(f, o, d, wide=False, jeans=False):
    p = (
        "M140,90 L260,90 L306,404 L212,404 L200,196 L188,404 L94,404 Z"
        if wide
        else "M140,90 L260,90 L286,404 L216,404 L200,186 L184,404 L114,404 Z"
    )
    s = _body(p, f, o)
    s += f'<rect x="138" y="84" width="124" height="22" rx="3" fill="{shade(f, 0.88)}" stroke="{o}" stroke-width="2"/>'
    if jeans:
        st = "#D7A94F"
        s += f'<path d="M146,112 Q160,150 186,150 M254,112 Q240,150 214,150" fill="none" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
        s += f'<line x1="200" y1="106" x2="200" y2="180" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
    else:
        s += f'<line x1="160" y1="110" x2="150" y2="400" stroke="{d}" stroke-width="1.5"/><line x1="240" y1="110" x2="250" y2="400" stroke="{d}" stroke-width="1.5"/>'
    return s


def art_leggings(f, o, d):
    s = _body("M150,90 L250,90 L246,404 L208,404 L200,176 L192,404 L154,404 Z", f, o)
    s += f'<rect x="148" y="84" width="104" height="26" rx="4" fill="{shade(f, 1.15)}" stroke="{o}" stroke-width="2"/>'
    return s


def art_skirt(f, o, d):
    s = _body("M150,108 L250,108 L290,396 L110,396 Z", f, o)
    s += f'<rect x="146" y="96" width="108" height="20" rx="3" fill="{shade(f, 1.18)}" stroke="{o}" stroke-width="2"/>'
    s += f'<path d="M170,116 L160,396 M230,116 L240,396" stroke="{shade(f, 1.3)}" stroke-width="1.5"/>'
    return s


def art_slipdress(f, o, d):
    s = f'<path d="M166,130 L176,70 M234,130 L224,70" stroke="{o}" stroke-width="3"/>'
    s += _body("M156,130 Q180,120 200,150 Q220,120 244,130 L252,210 L284,420 L116,420 L148,210 Z", f, o)
    s += f'<path d="M150,214 Q200,226 250,214" fill="none" stroke="{shade(f, 1.4)}" stroke-width="1.5"/>'
    s += f'<path d="M180,240 Q190,330 170,418 M220,240 Q210,330 232,418" fill="none" stroke="{shade(f, 1.3)}" stroke-width="1.5"/>'
    return s


def art_wrapdress(f, o, d):
    p = "M150,110 L176,90 L200,168 L224,90 L250,110 L292,150 L276,176 L256,160 L252,212 L298,422 L102,422 L148,212 L144,160 L124,176 L108,150 Z"
    s = _body(p, f, o)
    s += f'<path d="M176,90 L242,214 M224,90 L200,168" fill="none" stroke="{d}" stroke-width="2"/>'
    s += f'<path d="M148,214 Q200,226 252,214" fill="none" stroke="{d}" stroke-width="5"/>'
    s += f'<path d="M252,214 L272,262" stroke="{d}" stroke-width="4"/>'
    return s


def art_jacket(f, o, d, kind="moto"):
    bottom = {"moto": 352, "denim": 344, "blazer": 372, "coat": 440}[kind]
    p = (
        f"M130,118 L170,96 L200,118 L230,96 L270,118 L304,140 L322,{min(bottom, 350) - 10} L292,{min(bottom, 350) - 4} "
        f"L280,196 L280,{bottom} L120,{bottom} L120,196 L108,{min(bottom, 350) - 4} L78,{min(bottom, 350) - 10} L96,140 Z"
    )
    s = _body(p, f, o)
    if kind == "moto":
        s += f'<path d="M170,96 L150,170 L196,196 L230,96" fill="{shade(f, 1.15)}" stroke="{o}" stroke-width="1.5"/>'
        s += f'<line x1="218" y1="150" x2="182" y2="{bottom}" stroke="#C0C4CA" stroke-width="3"/>'
        s += f'<path d="M232,240 L262,236 M138,236 L168,240" stroke="#C0C4CA" stroke-width="2.5"/>'
        s += f'<rect x="120" y="{bottom - 22}" width="160" height="22" fill="{shade(f, 1.12)}" stroke="{o}" stroke-width="1.5"/>'
    elif kind == "denim":
        st = "#D7A94F"
        s += f'<path d="M170,96 L186,150 L200,118 L214,150 L230,96" fill="{shade(f, 0.9)}" stroke="{o}" stroke-width="1.5"/>'
        s += f'<line x1="200" y1="118" x2="200" y2="{bottom}" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
        s += f'<rect x="138" y="190" width="44" height="40" rx="4" fill="none" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
        s += f'<rect x="218" y="190" width="44" height="40" rx="4" fill="none" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
        s += f'<line x1="120" y1="{bottom - 24}" x2="280" y2="{bottom - 24}" stroke="{st}" stroke-width="2" stroke-dasharray="5 4"/>'
    else:
        lapel = shade(f, 1.14)
        s += f'<path d="M170,96 L156,186 L200,{bottom - 120 if kind == "coat" else 250} L244,186 L230,96 L200,118 Z" fill="{lapel}" stroke="{o}" stroke-width="1.5"/>'
        s += f'<path d="M180,110 L200,{bottom - 120 if kind == "coat" else 250} L220,110" fill="#F5F2EC" stroke="none" opacity="0.9"/>'
        ys = (300, 360) if kind == "coat" else (280, 316)
        s += "".join(f'<circle cx="212" cy="{y}" r="5" fill="{d}"/>' for y in ys)
        s += f'<path d="M138,300 L176,300 M224,300 L262,300" stroke="{d}" stroke-width="2"/>'
    return s


def art_shoe(f, o, d, kind):
    sole = "#F2EFE9" if kind in ("sneakers", "runners") else shade(f, 0.6)
    if kind in ("sneakers", "runners"):
        upper = "M88,300 Q92,236 150,232 L206,226 Q236,250 282,258 Q322,266 322,300 Z"
        s = _body(upper, f, o)
        thick = 30 if kind == "runners" else 20
        s += f'<rect x="84" y="296" width="242" height="{thick}" rx="9" fill="{sole}" stroke="{shade(sole, 0.8)}" stroke-width="2"/>'
        s += "".join(f'<line x1="{170 + i * 12}" y1="{240 + i * 3}" x2="{184 + i * 12}" y2="{254 + i * 3}" stroke="{d}" stroke-width="3"/>' for i in range(4))
        if kind == "runners":
            s += f'<path d="M140,286 Q210,250 290,280" fill="none" stroke="{shade(f, 1.5)}" stroke-width="5"/>'
        return s
    if kind == "boots":
        s = _body("M150,132 L232,132 L236,272 Q296,282 314,312 L314,334 L140,334 L140,300 Z", f, o)
        s += f'<path d="M206,140 Q218,200 206,262 L236,262 L232,140 Z" fill="{shade(f, 1.25)}" stroke="{o}" stroke-width="1.5"/>'
        s += f'<rect x="136" y="330" width="182" height="16" rx="4" fill="{sole}"/>'
        s += f'<rect x="196" y="116" width="24" height="22" rx="4" fill="{shade(f, 1.3)}"/>'
        return s
    if kind == "heels":
        s = _body("M96,306 Q120,262 176,262 Q240,264 300,236 L310,248 Q292,282 290,300 L282,300 Q232,312 186,318 Q130,322 96,312 Z", f, o)
        s += f'<path d="M282,298 L292,298 L286,352 L280,352 Z" fill="{f}" stroke="{o}" stroke-width="1.5"/>'
        s += f'<path d="M150,268 Q196,282 250,256" fill="none" stroke="{shade(f, 1.6)}" stroke-width="2"/>'
        return s
    # loafers
    s = _body("M88,304 Q96,254 168,250 L250,254 Q302,262 318,304 Z", f, o)
    s += f'<rect x="84" y="300" width="238" height="16" rx="6" fill="{sole}"/>'
    s += f'<path d="M190,258 Q222,250 262,264 L256,282 Q222,272 196,278 Z" fill="{shade(f, 0.82)}" stroke="{o}" stroke-width="1.5"/>'
    return s


def art_earrings(f, o, d):
    s = ""
    for cx in (150, 250):
        s += f'<circle cx="{cx}" cy="250" r="54" fill="none" stroke="{f}" stroke-width="12"/>'
        s += f'<circle cx="{cx}" cy="250" r="54" fill="none" stroke="{shade(f, 1.35)}" stroke-width="3" stroke-dasharray="40 300"/>'
    return s


def art_necklace(f, o, d):
    s = f'<path d="M110,130 Q200,360 290,130" fill="none" stroke="{f}" stroke-width="7" stroke-dasharray="10 5" stroke-linecap="round"/>'
    s += f'<path d="M110,130 Q200,360 290,130" fill="none" stroke="{shade(f, 0.7)}" stroke-width="1.5"/>'
    s += f'<rect x="188" y="246" width="24" height="24" rx="4" fill="{f}" stroke="{shade(f, 0.7)}" stroke-width="2"/>'
    return s


def art_scarf(f, o, d):
    s = _body("M120,110 L280,110 L280,200 Q240,230 250,330 L210,330 Q206,230 160,206 L160,370 L120,370 Z", f, o)
    s += "".join(f'<line x1="{x}" y1="370" x2="{x}" y2="388" stroke="{f}" stroke-width="3"/>' for x in range(124, 160, 7))
    s += "".join(f'<line x1="{x}" y1="330" x2="{x}" y2="348" stroke="{f}" stroke-width="3"/>' for x in range(213, 250, 7))
    s += f'<path d="M120,150 L280,150 M120,170 L280,170" stroke="{d}" stroke-width="1.5"/>'
    return s


def art_tote(f, o, d):
    s = f'<path d="M150,206 Q150,110 200,110 Q250,110 250,206" fill="none" stroke="{o}" stroke-width="9"/>'
    s += _body("M106,200 L294,200 L310,404 L90,404 Z", f, o)
    s += f'<path d="M106,226 L294,226" stroke="{d}" stroke-width="1.5"/>'
    s += f'<rect x="188" y="236" width="24" height="14" rx="3" fill="#C9A24A"/>'
    return s


ARTS = {
    "tee": lambda f, o, d: art_tee(f, o, d),
    "tee_stripe": lambda f, o, d: art_tee(f, o, d, stripes=True),
    "shirt": art_shirt,
    "sweater": lambda f, o, d: art_sweater(f, o, d),
    "mockneck": lambda f, o, d: art_sweater(f, o, d, mock=True),
    "cami": art_cami,
    "tank": art_tank,
    "trousers": lambda f, o, d: art_trousers(f, o, d),
    "trousers_wide": lambda f, o, d: art_trousers(f, o, d, wide=True),
    "jeans": lambda f, o, d: art_trousers(f, o, d, jeans=True),
    "leggings": art_leggings,
    "skirt": art_skirt,
    "slipdress": art_slipdress,
    "wrapdress": art_wrapdress,
    "moto": lambda f, o, d: art_jacket(f, o, d, "moto"),
    "denimjacket": lambda f, o, d: art_jacket(f, o, d, "denim"),
    "blazer": lambda f, o, d: art_jacket(f, o, d, "blazer"),
    "coat": lambda f, o, d: art_jacket(f, o, d, "coat"),
    "sneakers": lambda f, o, d: art_shoe(f, o, d, "sneakers"),
    "runners": lambda f, o, d: art_shoe(f, o, d, "runners"),
    "boots": lambda f, o, d: art_shoe(f, o, d, "boots"),
    "heels": lambda f, o, d: art_shoe(f, o, d, "heels"),
    "loafers": lambda f, o, d: art_shoe(f, o, d, "loafers"),
    "earrings": art_earrings,
    "necklace": art_necklace,
    "scarf": art_scarf,
    "tote": art_tote,
}


def render(kind: str, color: str) -> str:
    f = COLOR_HEX.get(color, "#9A9A98")
    o = shade(f, 0.78) if is_light(f) else shade(f, 0.7)
    d = shade(f, 0.62) if is_light(f) else shade(f, 1.45)
    shadow_y = 380 if kind in ("sneakers", "runners", "loafers", "heels", "boots") else 440
    body = ARTS[kind](f, o, d)
    is_shoe = kind in ("sneakers", "runners", "loafers", "heels", "boots")
    transform = ' transform="translate(200,290) scale(1.35) translate(-200,-290)"' if is_shoe else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 480" width="400" height="480">'
        '<defs><radialGradient id="bg" cx="50%" cy="40%" r="70%">'
        f'<stop offset="0%" stop-color="#FBFAF7"/><stop offset="100%" stop-color="{BG}"/></radialGradient>'
        '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="#1A3226" flood-opacity="0.12"/></filter></defs>'
        '<rect width="400" height="480" fill="url(#bg)"/>'
        f'<ellipse cx="200" cy="{shadow_y}" rx="120" ry="10" fill="#1A3226" opacity="0.06"/>'
        f'<g filter="url(#soft)"{transform}>{body}</g></svg>'
    )


def main() -> None:
    for filename, kind, color in art_manifest():
        (HERE / filename).write_text(render(kind, color))
    print(f"Rendered {len(art_manifest())} images into {HERE}")


if __name__ == "__main__":
    main()
