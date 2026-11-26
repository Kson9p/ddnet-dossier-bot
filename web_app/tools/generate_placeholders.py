"""Генератор демонстрационных SVG-заглушек для каталога анкет DDNet.

Скрипт создаёт абстрактные обложки, аватары и изображения галереи.
Никаких реальных фотографий, ников или логотипов не используется.

Запуск: python tools/generate_placeholders.py
"""

from __future__ import annotations

import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "placeholder"

# id, инициалы, цвет 1, цвет 2
PLAYERS = [
    ("nova", "NV", "#3b5bdb", "#7048e8"),
    ("kvant", "KV", "#0b7285", "#12b886"),
    ("mira", "MR", "#a61e4d", "#f06595"),
    ("pixel", "PX", "#5f3dc4", "#9c36b5"),
    ("vortex", "VX", "#d9480f", "#f08c00"),
    ("lumen", "LM", "#0c8599", "#22b8cf"),
    ("rift", "RF", "#2b8a3e", "#66a80f"),
    ("sable", "SB", "#495057", "#6741d9"),
    ("orbit", "OR", "#1864ab", "#5f3dc4"),
    ("echo", "EC", "#862e9c", "#c2255c"),
]

FONT = "Segoe UI, Inter, Arial, Helvetica, sans-serif"


def svg_open(w: int, h: int, extra: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" fill="none" {extra}>'
    )


def defs(c1: str, c2: str, grid: int = 64) -> str:
    return f"""<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c1}"/>
    <stop offset="1" stop-color="{c2}"/>
  </linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#000" stop-opacity="0"/>
    <stop offset="1" stop-color="#000" stop-opacity=".55"/>
  </linearGradient>
  <radialGradient id="glow" cx=".72" cy=".18" r=".9">
    <stop offset="0" stop-color="#fff" stop-opacity=".26"/>
    <stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </radialGradient>
  <pattern id="grid" width="{grid}" height="{grid}" patternUnits="userSpaceOnUse">
    <path d="M{grid} 0H0V{grid}" stroke="#fff" stroke-opacity=".055" stroke-width="1"/>
  </pattern>
</defs>"""


def demo_badge(x: int, y: int, label: str = "ДЕМО") -> str:
    w = 34 + len(label) * 13
    return f"""<g transform="translate({x} {y})">
  <rect width="{w}" height="36" rx="10" fill="#fff" fill-opacity=".14" stroke="#fff" stroke-opacity=".22"/>
  <text x="{w / 2}" y="24" text-anchor="middle" font-family="{FONT}" font-size="16"
        font-weight="700" letter-spacing="3" fill="#fff" fill-opacity=".85">{label}</text>
</g>"""


def route(rnd: random.Random, w: int, h: int, color: str = "#fff") -> str:
    """Ломаная линия, похожая на маршрут карты DDRace."""
    points = []
    x = rnd.randint(40, 140)
    y = rnd.randint(int(h * 0.45), int(h * 0.8))
    for i in range(6):
        points.append((x, y))
        x += rnd.randint(int(w * 0.1), int(w * 0.2))
        y = max(int(h * 0.12), min(int(h * 0.9), y + rnd.randint(-int(h * 0.22), int(h * 0.22))))
    if x < w - 60:
        points.append((w - 60, y))
    path = " ".join(f"{'M' if i == 0 else 'L'}{px} {py}" for i, (px, py) in enumerate(points))
    nodes = "".join(
        f'<circle cx="{px}" cy="{py}" r="9" fill="{color}" fill-opacity=".38"/>' for px, py in points
    )
    return (
        f'<path d="{path}" stroke="{color}" stroke-opacity=".2" stroke-width="10" '
        f'stroke-linecap="round" stroke-linejoin="round"/>{nodes}'
    )


def circles(rnd: random.Random, w: int, h: int, count: int = 5) -> str:
    out = []
    for _ in range(count):
        r = rnd.randint(50, int(min(w, h) * 0.35))
        cx = rnd.randint(0, w)
        cy = rnd.randint(0, h)
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" fill-opacity="{rnd.choice([0.03, 0.04, 0.06, 0.08])}"/>'
        )
    return "".join(out)


def cover(pid: str, initials: str, c1: str, c2: str) -> str:
    rnd = random.Random(f"{pid}-cover")
    w, h = 1200, 675
    art = [
        svg_open(w, h),
        defs(c1, c2),
        '<rect width="1200" height="675" fill="url(#bg)"/>',
        '<rect width="1200" height="675" fill="url(#grid)"/>',
        circles(rnd, w, h, 6),
        '<rect width="1200" height="675" fill="url(#glow)"/>',
        route(rnd, w, h),
        # Диагональные штрихи
        '<g opacity=".10">',
    ]
    for i in range(9):
        x = 120 + i * 130
        art.append(
            f'<rect x="{x}" y="-140" width="26" height="1000" fill="#fff" '
            f'transform="rotate(24 {x} 300)"/>'
        )
    art.append("</g>")
    art.append(
        f'<text x="1148" y="620" text-anchor="end" font-family="{FONT}" font-size="300" '
        f'font-weight="800" fill="#fff" fill-opacity=".15">{initials}</text>'
    )
    art.append(
        f'<text x="1150" y="650" text-anchor="end" font-family="{FONT}" font-size="17" '
        f'letter-spacing="5" fill="#fff" fill-opacity=".45">DDNET · ПЛЕЙСХОЛДЕР</text>'
    )
    art.append(demo_badge(44, 603))
    art.append("</svg>")
    return "".join(art)


def avatar(pid: str, initials: str, c1: str, c2: str) -> str:
    rnd = random.Random(f"{pid}-avatar")
    s = 512
    art = [
        svg_open(s, s),
        defs(c1, c2, 48),
        '<rect width="512" height="512" fill="url(#bg)"/>',
        '<rect width="512" height="512" fill="url(#grid)"/>',
        circles(rnd, s, s, 3),
        '<rect width="512" height="512" fill="url(#glow)"/>',
        # дуги
        '<circle cx="256" cy="256" r="196" stroke="#fff" stroke-opacity=".18" stroke-width="2"/>',
        '<circle cx="256" cy="256" r="150" stroke="#fff" stroke-opacity=".10" stroke-width="2"/>',
        f'<text x="256" y="318" text-anchor="middle" font-family="{FONT}" font-size="168" '
        f'font-weight="700" fill="#fff" fill-opacity=".92">{initials}</text>',
        "</svg>",
    ]
    return "".join(art)


def tee(x: int, y: int, size: int = 90, scarf: str = "#fff") -> str:
    """Простейший силуэт персонажа DDNet (tee)."""
    b = size
    eye = max(4, b // 12)
    return f"""<g transform="translate({x} {y})" opacity=".92">
  <rect x="0" y="0" width="{b}" height="{b}" rx="{int(b * 0.26)}" fill="#f7fbff" fill-opacity=".9"/>
  <rect x="0" y="{int(b * 0.62)}" width="{b}" height="{int(b * 0.1)}" fill="{scarf}" fill-opacity=".85"/>
  <circle cx="{int(b * 0.33)}" cy="{int(b * 0.4)}" r="{eye}" fill="#17212b"/>
  <circle cx="{int(b * 0.67)}" cy="{int(b * 0.4)}" r="{eye}" fill="#17212b"/>
  <rect x="{int(b * 0.18)}" y="{b}" width="{int(b * 0.22)}" height="{int(b * 0.1)}" rx="{int(b * 0.04)}" fill="#f7fbff" fill-opacity=".55"/>
  <rect x="{int(b * 0.6)}" y="{b}" width="{int(b * 0.22)}" height="{int(b * 0.1)}" rx="{int(b * 0.04)}" fill="#f7fbff" fill-opacity=".55"/>
</g>"""


def gallery_shot(pid: str, idx: int, c1: str, c2: str) -> str:
    rnd = random.Random(f"{pid}-shot-{idx}")
    w, h = 1200, 900
    art = [
        svg_open(w, h),
        defs(c1, c2, 72),
        '<rect width="1200" height="900" fill="url(#bg)"/>',
        '<rect width="1200" height="900" fill="url(#grid)"/>',
        circles(rnd, w, h, 4),
        '<rect width="1200" height="900" fill="url(#glow)"/>',
        # платформы
    ]
    for _ in range(5):
        pw = rnd.randint(150, 380)
        ph = rnd.randint(22, 42)
        px = rnd.randint(-40, w - 100)
        py = rnd.randint(140, h - 120)
        art.append(
            f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="{ph // 2}" '
            f'fill="#fff" fill-opacity=".12" stroke="#fff" stroke-opacity=".16"/>'
        )
    art.append(route(rnd, w, h))
    art.append(tee(rnd.randint(220, w - 360), rnd.randint(160, h - 320), rnd.randint(80, 120), c2))
    # HUD
    art.append(
        f'<text x="56" y="86" font-family="{FONT}" font-size="20" letter-spacing="4" '
        f'fill="#fff" fill-opacity=".65">MAP PREVIEW · ДЕМО</text>'
    )
    art.append(
        f'<rect x="56" y="112" width="180" height="4" rx="2" fill="#fff" fill-opacity=".25"/>'
    )
    art.append(
        f'<text x="1144" y="844" text-anchor="end" font-family="{FONT}" font-size="18" '
        f'letter-spacing="3" fill="#fff" fill-opacity=".4">ДЕМО-ИЗОБРАЖЕНИЕ</text>'
    )
    art.append("</svg>")
    return "".join(art)


def gallery_rings(pid: str, c1: str, c2: str) -> str:
    rnd = random.Random(f"{pid}-rings")
    w, h = 1200, 900
    art = [
        svg_open(w, h),
        defs(c1, c2, 80),
        '<rect width="1200" height="900" fill="url(#bg)"/>',
        '<rect width="1200" height="900" fill="url(#grid)"/>',
        circles(rnd, w, h, 4),
        '<rect width="1200" height="900" fill="url(#glow)"/>',
    ]
    for i in range(4):
        r = 180 + i * 120
        art.append(
            f'<circle cx="820" cy="420" r="{r}" stroke="#fff" stroke-opacity="{0.16 - i * 0.03}" '
            f'stroke-width="2"/>'
        )
    art.append(
        '<path d="M-80 760 L420 180" stroke="#fff" stroke-opacity=".12" stroke-width="120"/>'
    )
    art.append(tee(250, 300, 150, c2))
    art.append(
        f'<text x="60" y="810" font-family="{FONT}" font-size="22" letter-spacing="4" '
        f'fill="#fff" fill-opacity=".6">АТМОСФЕРА · ДЕМО</text>'
    )
    art.append(
        f'<text x="1144" y="844" text-anchor="end" font-family="{FONT}" font-size="18" '
        f'letter-spacing="3" fill="#fff" fill-opacity=".4">ПЛЕЙСХОЛДЕР</text>'
    )
    art.append("</svg>")
    return "".join(art)


def gallery_video(pid: str, c1: str, c2: str) -> str:
    rnd = random.Random(f"{pid}-video")
    w, h = 1200, 900
    art = [
        svg_open(w, h),
        defs(c1, c2, 72),
        '<rect width="1200" height="900" fill="url(#bg)"/>',
        '<rect width="1200" height="900" fill="url(#grid)"/>',
        circles(rnd, w, h, 5),
        '<rect width="1200" height="900" fill="url(#glow)"/>',
        '<rect width="1200" height="900" fill="#07111b" fill-opacity=".42"/>',
        route(rnd, w, h),
        f'<text x="600" y="540" text-anchor="middle" font-family="{FONT}" font-size="20" '
        f'letter-spacing="6" fill="#fff" fill-opacity=".65">ДЕМО-ВИДЕО</text>',
        f'<text x="1144" y="844" text-anchor="end" font-family="{FONT}" font-size="18" '
        f'letter-spacing="3" fill="#fff" fill-opacity=".4">ВИДЕО-ЗАГЛУШКА</text>',
        "</svg>",
    ]
    return "".join(art)


def favicon() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3b5bdb"/><stop offset="1" stop-color="#7048e8"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="16" fill="url(#g)"/>
  <path d="M17 21h11a11 11 0 0 1 0 22H17V21Zm8 6v10h3a5 5 0 0 0 0-10h-3Z" fill="#fff" fill-opacity=".92"/>
  <path d="M38 21h9a11 11 0 0 1 0 22h-9V21Zm7 6v10h2a5 5 0 0 0 0-10h-2Z" fill="#fff" fill-opacity=".6"/>
</svg>"""


def main() -> None:
    for sub in ("covers", "avatars", "gallery"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    for pid, initials, c1, c2 in PLAYERS:
        (OUT / "covers" / f"{pid}.svg").write_text(cover(pid, initials, c1, c2), encoding="utf-8")
        (OUT / "avatars" / f"{pid}.svg").write_text(avatar(pid, initials, c1, c2), encoding="utf-8")
        (OUT / "gallery" / f"{pid}-1.svg").write_text(
            gallery_shot(pid, 1, c1, c2), encoding="utf-8"
        )
        (OUT / "gallery" / f"{pid}-2.svg").write_text(
            gallery_rings(pid, c1, c2), encoding="utf-8"
        )
        (OUT / "gallery" / f"{pid}-video.svg").write_text(
            gallery_video(pid, c1, c2), encoding="utf-8"
        )

    (ROOT / "assets" / "favicon.svg").write_text(favicon(), encoding="utf-8")
    total = len(PLAYERS) * 5 + 1
    print(f"Готово: {total} файлов в {OUT}")


if __name__ == "__main__":
    main()
