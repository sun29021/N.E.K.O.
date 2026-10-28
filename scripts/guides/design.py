"""Shared look for the printable N.E.K.O. guides: CSS, drawn illustrations (inline SVG) and small helpers.

Everything is drawn here (no images, no web fonts, nothing downloaded), so the PDFs build offline.
"""

from __future__ import annotations

import html

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1c2433; font-size: 11pt; line-height: 1.45; }
.page { width: 210mm; min-height: 297mm; padding: 16mm 16mm 18mm; position: relative; page-break-after: always;
        background: #ffffff; }
.page:last-child { page-break-after: auto; }
.foot { position: absolute; bottom: 8mm; left: 16mm; right: 16mm; font-size: 8.5pt; color: #8a94a6;
        display: flex; justify-content: space-between; border-top: 1px solid #e3e8ef; padding-top: 2mm; }
h1 { font-size: 23pt; margin: 0 0 3mm; color: #0b2b3a; letter-spacing: .2px; }
h2 { font-size: 15pt; margin: 6mm 0 2.5mm; color: #0E7C74; }
h3 { font-size: 12pt; margin: 4mm 0 1.5mm; color: #0b2b3a; }
p { margin: 0 0 2.5mm; }
.lead { font-size: 12.5pt; color: #3b4658; margin-bottom: 5mm; }
.kicker { text-transform: uppercase; letter-spacing: 2.5px; font-size: 9pt; color: #0E7C74; font-weight: 700; }
.small { font-size: 9.5pt; color: #5b6576; }
ul { margin: 0 0 3mm 5mm; padding-left: 4mm; } li { margin-bottom: 1.2mm; }
code, .code { font-family: Consolas, monospace; font-size: 9.5pt; background: #eef3f7; padding: .3mm 1.5mm;
              border-radius: 3px; color: #0b2b3a; }
.cmdbox { font-family: Consolas, monospace; font-size: 9.5pt; background: #0d1624; color: #b8f5ff; border-radius: 6px;
          padding: 3mm 4mm; margin: 2mm 0 4mm; white-space: pre-wrap; word-break: break-all; }

/* cover */
.cover { background: radial-gradient(circle at 70% 30%, #12304a 0%, #070b14 60%); color: #e8f4ff; padding: 22mm 18mm; }
.cover h1 { color: #ffffff; font-size: 34pt; line-height: 1.1; margin-top: 8mm; }
.cover .sub { font-size: 15pt; color: #9fd9ff; margin-top: 4mm; max-width: 150mm; }
.cover .tagline { position: absolute; bottom: 22mm; left: 18mm; right: 18mm; font-size: 11pt; color: #9fb3c8; }
.cover .brand { font-size: 12pt; letter-spacing: 8px; color: #3ef0ff; font-weight: 700; }
.cover .badge { display: inline-block; border: 1px solid #3ef0ff66; color: #9ff8ff; border-radius: 99px;
                padding: 1.5mm 5mm; margin: 2mm 2mm 0 0; font-size: 10pt; }

/* steps */
.step { display: flex; gap: 5mm; margin: 4mm 0; align-items: flex-start; page-break-inside: avoid; }
.num { flex: 0 0 11mm; height: 11mm; border-radius: 50%; background: #0E7C74; color: #fff; font-weight: 800;
       font-size: 14pt; display: flex; align-items: center; justify-content: center; }
.num.b { background: #3a5bd9; } .num.c { background: #b4570d; }
.step .body { flex: 1; } .step .body h3 { margin-top: 1.5mm; }

/* cards & grids */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; margin: 3mm 0; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 3.5mm; margin: 3mm 0; }
.card { border: 1px solid #dfe6ee; border-radius: 9px; padding: 3.5mm 4mm; background: #fbfdff; page-break-inside: avoid; }
.card h3 { margin-top: 0; display: flex; align-items: center; gap: 2.5mm; }
.card .ic { width: 9mm; height: 9mm; flex: 0 0 9mm; }
.feature { border-left: 4px solid #3ef0ff; }

/* say-this bubbles */
.say { display: inline-block; background: #e9fbff; border: 1px solid #9fe7f2; color: #064b57; border-radius: 14px 14px 14px 3px;
       padding: 1mm 3mm; margin: .8mm 1.2mm .8mm 0; font-size: 10pt; font-weight: 600; }
.say:before { content: "\\201C"; color: #0E7C74; } .say:after { content: "\\201D"; color: #0E7C74; }
.does { color: #5b6576; font-size: 9.5pt; }

/* callouts */
.note { border-radius: 8px; padding: 3mm 4mm; margin: 3mm 0; page-break-inside: avoid; display: flex; gap: 3mm; }
.note .t { font-weight: 700; } .note > svg { flex: 0 0 7mm; width: 7mm; height: 7mm; }
.tip { background: #eefbf3; border: 1px solid #a8e2bf; } .tip .t { color: #11753b; }
.safe { background: #fff7e8; border: 1px solid #f2cf8c; } .safe .t { color: #9a5b00; }
.stop { background: #fff0f1; border: 1px solid #f3b5bd; } .stop .t { color: #b3122b; }
.info { background: #eef4ff; border: 1px solid #b9cdf7; } .info .t { color: #2747a8; }

/* tables */
table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 10pt; page-break-inside: auto; }
th { background: #0b2b3a; color: #fff; text-align: left; padding: 2mm 3mm; font-weight: 600; }
td { border-bottom: 1px solid #e3e8ef; padding: 1.8mm 3mm; vertical-align: top; }
tr:nth-child(even) td { background: #f6f9fc; }
tr { page-break-inside: avoid; }

/* mock-ups */
.window { border-radius: 8px; overflow: hidden; border: 1px solid #c9d3df; box-shadow: 0 2mm 5mm #0b2b3a22; margin: 3mm 0;
          page-break-inside: avoid; }
.window .bar { background: #1f2a3a; color: #dce6f2; font-size: 9pt; padding: 1.6mm 3mm; display: flex; gap: 2mm; align-items: center; }
.window .bar i { width: 2.6mm; height: 2.6mm; border-radius: 50%; background: #ff5f57; display: inline-block; }
.window .bar i:nth-child(2) { background: #febc2e; } .window .bar i:nth-child(3) { background: #28c840; }
.term { background: #0d1624; color: #cfe3f5; font-family: Consolas, monospace; font-size: 8.8pt; padding: 3mm 4mm;
        white-space: pre; line-height: 1.35; overflow: hidden; }
.term .g { color: #6ee7a8; } .term .y { color: #ffd479; } .term .c { color: #7fe9ff; }
.phone { width: 64mm; border: 3px solid #1b2433; border-radius: 9mm; padding: 4mm 2.5mm; background: #0f1621;
         margin: 2mm auto; page-break-inside: avoid; }
.phone .top { color: #e6eef8; font-size: 9pt; font-weight: 700; text-align: center; margin-bottom: 2.5mm; }
.phone .top span { display: block; font-weight: 400; color: #8aa0b8; font-size: 7.5pt; }
.bub { font-size: 8.4pt; line-height: 1.32; padding: 1.8mm 2.5mm; border-radius: 3mm; margin: 1.4mm 0; max-width: 86%; }
.bub.me { background: #7c4dff; color: #fff; margin-left: auto; border-bottom-right-radius: 1mm; }
.bub.bot { background: #1f2c3d; color: #e6eef8; border-bottom-left-radius: 1mm; }
.bub .btns { display: flex; gap: 1.5mm; margin-top: 1.5mm; }
.bub .btns b { flex: 1; text-align: center; background: #2b3d55; border-radius: 2mm; padding: 1mm; color: #9fe7ff; }
.dialog { background: #f4f7fb; padding: 3.5mm 4mm; font-size: 9.5pt; }
.dialog .btnrow { display: flex; justify-content: flex-end; gap: 2mm; margin-top: 2mm; }
.btn { border: 1px solid #b9c5d3; background: #fff; border-radius: 4px; padding: .6mm 3.5mm; font-size: 9pt;
       display: inline-block; margin: .8mm 0; }
.btn.def { border: 2px solid #3a5bd9; } .btn.danger { background: #c62839; color: #fff; border-color: #c62839; }
.tabs { display: flex; gap: 0; font-size: 8.5pt; border-bottom: 1px solid #c9d3df; background: #eef3f8; }
.tabs span { padding: 1.5mm 3mm; color: #5b6576; } .tabs span.on { color: #0b2b3a; border-bottom: 2px solid #0E7C74; font-weight: 700; }
.center { text-align: center; } .right { text-align: right; }
.row { display: flex; gap: 6mm; align-items: center; }
.col { flex: 1; }
.figcap { font-size: 8.8pt; color: #6b7587; text-align: center; margin-top: 1mm; }
.chip { display: inline-block; border-radius: 99px; padding: .6mm 3mm; font-size: 8.8pt; font-weight: 700; margin-right: 1.5mm; }
.chip.g { background: #dff7e9; color: #11753b; } .chip.y { background: #fff1d6; color: #9a5b00; }
.chip.r { background: #ffe1e5; color: #b3122b; } .chip.b { background: #e3ecff; color: #2747a8; }
.toc { columns: 2; column-gap: 8mm; font-size: 10.5pt; } .toc div { margin-bottom: 1.6mm; break-inside: avoid; }
.toc b { color: #0E7C74; display: inline-block; width: 8mm; }
"""

# ---------------------------------------------------------------------- icons (24x24 line drawings)
_ICON_PATHS = {
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>',
    "brain": '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><circle cx="12" cy="16" r="3"/>'
             '<path d="M10.5 11l1 2.5M13.5 11l-1 2.5M11 9h2"/>',
    "hand": '<path d="M7 12V6.5a1.5 1.5 0 0 1 3 0V11m0-5.5a1.5 1.5 0 0 1 3 0V11m0-4a1.5 1.5 0 0 1 3 0v4m0-2a1.5 1.5 0 0 1 3 0v5'
            'a7 7 0 0 1-7 7h-1a6 6 0 0 1-5-3l-2.5-4a1.5 1.5 0 0 1 2.5-1.6L7 13"/>',
    "speaker": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
    "laptop": '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
    "desktop": '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M9 20h6M12 16v4"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "music": '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
    "file": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M9.5 12h6M9.5 15.5h6"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "box": '<path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/>',
    "cloud": '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "warn": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4.5M12 17.5v.5"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1'
            'M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "book": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
    "eye": '<path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "upgrade": '<path d="M12 20V6M6 11l6-6 6 6"/><path d="M5 21h14"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "power": '<path d="M12 3v8"/><path d="M6.5 6.5a8 8 0 1 0 11 0"/>',
    "download": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 20h16"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17" cy="9" r="2.5"/><path d="M15.5 14.5a5 5 0 0 1 6 5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16.5 9.5"/>',
}


def icon(name: str, color: str = "#0E7C74", size: str = "9mm") -> str:
    return (f'<svg class="ic" viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICON_PATHS[name]}</svg>')


def orb(size_mm: int = 60, glow: str = "#3ef0ff", label: str = "") -> str:
    """Neko's glowing orb."""
    gid = f"g{abs(hash((glow, size_mm, label))) % 10**6}"
    text = (f'<text x="100" y="186" text-anchor="middle" font-size="15" fill="#c9d8ea" '
            f'font-family="Segoe UI">{html.escape(label)}</text>') if label else ""
    return f"""<svg viewBox="0 0 200 {195 if label else 200}" width="{size_mm}mm" height="{size_mm * (195 if label else 200) / 200:.1f}mm">
<defs><radialGradient id="{gid}" cx="50%" cy="45%" r="55%">
<stop offset="0%" stop-color="#ffffff"/><stop offset="18%" stop-color="{glow}"/>
<stop offset="55%" stop-color="{glow}" stop-opacity=".35"/><stop offset="100%" stop-color="{glow}" stop-opacity="0"/></radialGradient></defs>
<circle cx="100" cy="92" r="88" fill="url(#{gid})"/>
<circle cx="100" cy="92" r="58" fill="none" stroke="{glow}" stroke-opacity=".7" stroke-width="1.5" stroke-dasharray="3 6"/>
<circle cx="100" cy="92" r="72" fill="none" stroke="{glow}" stroke-opacity=".35" stroke-width="1"/>
<circle cx="100" cy="92" r="30" fill="none" stroke="#ffffff" stroke-opacity=".8" stroke-width="2"/>
{text}</svg>"""


def orb_states() -> str:
    states = [("#3ef0ff", "Ready"), ("#4dffa6", "Listening"), ("#a06bff", "Thinking"), ("#ffb547", "Waiting for OK"),
              ("#ff5c7a", "Problem")]
    cells = "".join(f'<div class="center" style="flex:1">{orb(26, c)}<div style="color:{c};font-size:10pt"><b>{t}</b></div></div>'
                    for c, t in states)
    return f'<div class="row" style="background:#070b14;border-radius:10px;padding:4mm 2mm;color:#fff">{cells}</div>'


def say(*phrases: str) -> str:
    return "".join(f'<span class="say">{html.escape(p)}</span>' for p in phrases)


def note(kind: str, title: str, text: str) -> str:
    ic = {"tip": ("check", "#11753b"), "safe": ("shield", "#9a5b00"), "stop": ("warn", "#b3122b"),
          "info": ("book", "#2747a8")}[kind]
    return (f'<div class="note {kind}">{icon(ic[0], ic[1], "7mm")}<div><span class="t">{title}</span> '
            f"{text}</div></div>")


def card(ic: str, title: str, body: str, color: str = "#0E7C74", extra: str = "") -> str:
    return f'<div class="card {extra}"><h3>{icon(ic, color)}{title}</h3>{body}</div>'


def step(n: str, title: str, body: str, tone: str = "") -> str:
    return f'<div class="step"><div class="num {tone}">{n}</div><div class="body"><h3>{title}</h3>{body}</div></div>'


def phone(title: str, sub: str, bubbles: list[tuple[str, str]], buttons: tuple[str, str] | None = None) -> str:
    """bubbles: [("me"|"bot", text)]; buttons are added to the last bot bubble."""
    out = []
    for i, (who, text) in enumerate(bubbles):
        btn = ""
        if buttons and who == "bot" and i == max(j for j, b in enumerate(bubbles) if b[0] == "bot"):
            btn = f'<div class="btns"><b>{buttons[0]}</b><b>{buttons[1]}</b></div>'
        out.append(f'<div class="bub {who}">{text}{btn}</div>')
    return f'<div class="phone"><div class="top">{title}<span>{sub}</span></div>{"".join(out)}</div>'


def window(title: str, inner: str, width: str = "100%") -> str:
    return f'<div class="window" style="width:{width}"><div class="bar"><i></i><i></i><i></i>&nbsp;{title}</div>{inner}</div>'


def table(head: list[str], rows: list[list[str]], widths: list[str] | None = None) -> str:
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def how_it_works() -> str:
    """You -> ears -> brain -> hands -> voice."""
    boxes = [("mic", "Ears", "hears you say her name"), ("brain", "Brain", "understands and decides"),
             ("hand", "Hands", "does things on the PC"), ("speaker", "Voice", "answers out loud")]
    parts = []
    for i, (ic, t, d) in enumerate(boxes):
        x = 18 + i * 170
        parts.append(f'<rect x="{x}" y="30" width="140" height="110" rx="16" fill="#f2fbfd" stroke="#9fe7f2" stroke-width="2"/>'
                     f'<g transform="translate({x + 50},44) scale(1.7)" fill="none" stroke="#0E7C74" stroke-width="1.8" '
                     f'stroke-linecap="round" stroke-linejoin="round">{_ICON_PATHS[ic]}</g>'
                     f'<text x="{x + 70}" y="108" text-anchor="middle" font-size="17" font-weight="700" fill="#0b2b3a">{t}</text>'
                     f'<text x="{x + 70}" y="128" text-anchor="middle" font-size="11.5" fill="#5b6576">{d}</text>')
        if i < 3:
            parts.append(f'<path d="M{x + 145} 85 h20" stroke="#0E7C74" stroke-width="3" marker-end="url(#ar)"/>')
    return (f'<svg viewBox="0 0 700 160" width="100%"><defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" '
            f'refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#0E7C74"/></marker></defs>{"".join(parts)}</svg>')


def network(owner_laptop: bool = True) -> str:
    """Laptop + office PC + phones + Tailscale + Telegram."""
    def dev(x: int, y: int, ic: str, title: str, sub: str, color: str) -> str:
        return (f'<rect x="{x}" y="{y}" width="170" height="92" rx="14" fill="#ffffff" stroke="{color}" stroke-width="2.4"/>'
                f'<g transform="translate({x + 14},{y + 22}) scale(1.9)" fill="none" stroke="{color}" stroke-width="1.7" '
                f'stroke-linecap="round" stroke-linejoin="round">{_ICON_PATHS[ic]}</g>'
                f'<text x="{x + 66}" y="{y + 40}" font-size="15" font-weight="700" fill="#0b2b3a">{title}</text>'
                f'<text x="{x + 66}" y="{y + 60}" font-size="11" fill="#5b6576">{sub}</text>')
    return f"""<svg viewBox="0 0 700 330" width="100%">
<defs><marker id="a2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#3a5bd9"/></marker></defs>
<ellipse cx="350" cy="165" rx="105" ry="48" fill="#eef4ff" stroke="#b9cdf7" stroke-width="2" stroke-dasharray="6 5"/>
<text x="350" y="160" text-anchor="middle" font-size="15" font-weight="700" fill="#2747a8">Tailscale</text>
<text x="350" y="180" text-anchor="middle" font-size="11" fill="#2747a8">your private network</text>
{dev(20, 40, "laptop", "Laptop", "main PC - the owner", "#0E7C74")}
{dev(510, 40, "desktop", "Office PC", "strong graphics card", "#b4570d")}
{dev(20, 215, "phone", "Your phone", "owner: approves", "#7c4dff")}
{dev(510, 215, "phone", "Office phone", "everyday use", "#7c4dff")}
<path d="M190 86 L255 140" stroke="#3a5bd9" stroke-width="2.4" marker-end="url(#a2)"/>
<path d="M510 86 L445 140" stroke="#3a5bd9" stroke-width="2.4" marker-end="url(#a2)"/>
<path d="M190 255 L262 190" stroke="#7c4dff" stroke-width="2" stroke-dasharray="5 4"/>
<path d="M510 255 L438 190" stroke="#7c4dff" stroke-width="2" stroke-dasharray="5 4"/>
<text x="350" y="62" text-anchor="middle" font-size="11.5" fill="#3b4658">laptop borrows the office PC's AI power</text>
<text x="350" y="292" text-anchor="middle" font-size="11.5" fill="#3b4658">phones chat through Telegram, call through Tailscale</text>
</svg>"""


def traffic_light() -> str:
    rows = [("#2fbf71", "Green - just does it", "open an app, play music, answer a question, read a file"),
            ("#f2a516", "Yellow - asks you first", "move a file, type into a field, run your program, send your screen"),
            ("#e0384f", "Red - asks every time", "delete, send, pay, shut down, publish an update (phone: + PIN)")]
    out = []
    for i, (c, t, d) in enumerate(rows):
        y = 18 + i * 74
        out.append(f'<circle cx="62" cy="{y + 30}" r="26" fill="{c}"/>'
                   f'<text x="110" y="{y + 26}" font-size="17" font-weight="700" fill="#0b2b3a">{t}</text>'
                   f'<text x="110" y="{y + 48}" font-size="12.5" fill="#5b6576">{d}</text>')
    return (f'<svg viewBox="0 0 700 240" width="100%"><rect x="26" y="8" width="72" height="226" rx="18" fill="#1c2433"/>'
            f'{"".join(out)}</svg>')


def page(inner: str, foot_left: str, n: int, cls: str = "") -> str:
    foot = "" if "cover" in cls else f'<div class="foot"><span>{foot_left}</span><span>{n}</span></div>'
    return f'<section class="page {cls}">{inner}{foot}</section>'


def document(title: str, pages: list[str]) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")
