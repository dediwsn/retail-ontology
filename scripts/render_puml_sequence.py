#!/usr/bin/env python3
"""
Render a PlantUML *sequence* diagram to SVG without Java or plantuml.jar.

This exists because the toolchain here has neither. It supports exactly the
subset of PlantUML sequence syntax used by docs/diagrams/*.puml:

    @startuml / @enduml            title <text>
    autonumber                     hide footbox
    box "<label>" #RRGGBB ... end box
    participant|actor|database|entity|control|boundary "<label>" as <ALIAS>
    A -> B : msg          (solid)      A --> B : msg   (dashed / return)
    A ->> B : msg         (open head)  A -->> B : msg
    group|alt|opt|loop <label> ... else <label> ... end
    note over A[, B] : text            note left|right of A : text
    == divider ==                      ' line comment

`\\n` inside any label is a line break, matching PlantUML. Anything else is
ignored with a warning rather than silently dropped.

Usage:  python3 scripts/render_puml_sequence.py <in.puml> <out.svg>
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

# ── metrics ────────────────────────────────────────────────────────────────
FONT = "DejaVu Sans, Noto Sans CJK KR, Malgun Gothic, Apple SD Gothic Neo, sans-serif"
FS_TITLE, FS_PART, FS_MSG, FS_NOTE, FS_GROUP, FS_DIV = 19, 13, 12.5, 12, 11.5, 13.5
LINE_H = 15
PART_PAD_X, PART_MIN_W, PART_H = 16, 112, 0   # PART_H computed per participant
BASE_GAP = 30
MARGIN_X, MARGIN_TOP = 34, 30
SELF_W = 46

C_BG      = "#FFFFFF"
C_INK     = "#16211F"
C_MUTED   = "#5D6B66"
C_LIFE    = "#B7C5BF"
C_ARROW   = "#2C4A42"
C_PART_ST = "#426057"
C_GRP     = "#79A296"
C_GRP_TAB = "#DCE8E3"
C_NOTE_BG = "#FDF6E3"
C_NOTE_ST = "#D6C088"
C_DIV     = "#9BB0A8"
C_BOX_ST  = "#9FB3AC"


def text_w(s: str, size: float) -> float:
    """Width estimate. CJK/Hangul glyphs are ~full-em; Latin ~0.55em."""
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o > 0x1100 and not (0x2000 <= o <= 0x206F):
            w += size * 0.98
        elif ch in "iljt.,:;'|!":
            w += size * 0.30
        elif ch.isupper():
            w += size * 0.66
        else:
            w += size * 0.55
    return w


def soft_wrap(line: str, limit: float, size: float) -> List[str]:
    if text_w(line, size) <= limit:
        return [line]
    out, cur = [], ""
    for word in line.split(" "):
        trial = f"{cur} {word}".strip()
        if cur and text_w(trial, size) > limit:
            out.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out


def lines_of(label: str, limit: float = 245.0, size: float = FS_MSG) -> List[str]:
    out: List[str] = []
    for raw in label.split("\\n"):
        out.extend(soft_wrap(raw.strip(), limit, size))
    return out or [""]


# ── model ──────────────────────────────────────────────────────────────────
@dataclass
class Participant:
    alias: str
    label: str
    kind: str
    box: Optional[int]
    lines: List[str] = field(default_factory=list)
    w: float = 0.0
    h: float = 0.0
    x: float = 0.0


@dataclass
class Box:
    label: str
    color: str
    first: int = 0
    last: int = -1


@dataclass
class Ev:
    kind: str                    # msg | note | divider | grp | else | end
    a: str = ""
    b: str = ""
    text: str = ""
    dashed: bool = False
    open_head: bool = False
    side: str = ""               # note placement
    num: Optional[int] = None
    y: float = 0.0
    h: float = 0.0


MSG_RE = re.compile(r"^(\w+)\s*(-->>|--\>|->>|->)\s*(\w+)\s*:\s*(.*)$")
PART_RE = re.compile(
    r'^(participant|actor|database|entity|control|boundary|collections)\s+'
    r'"([^"]*)"\s+as\s+(\w+)', re.I)
BOX_RE = re.compile(r'^box\s+"([^"]*)"(?:\s+(#[0-9A-Fa-f]{3,8}))?')
NOTE_OVER_RE = re.compile(r"^note\s+over\s+([\w\s,]+?)\s*:\s*(.*)$", re.I)
NOTE_SIDE_RE = re.compile(r"^note\s+(left|right)\s+of\s+(\w+)\s*:\s*(.*)$", re.I)
GRP_RE = re.compile(r"^(group|alt|opt|loop|par|critical)\b\s*(.*)$", re.I)
DIV_RE = re.compile(r"^==\s*(.*?)\s*==$")


def parse(src: str):
    parts: Dict[str, Participant] = {}
    order: List[str] = []
    boxes: List[Box] = []
    evs: List[Ev] = []
    title = ""
    autonum = False
    cur_box: Optional[int] = None

    for raw in src.splitlines():
        line = raw.strip()
        if not line or line.startswith("'") or line.startswith("@"):
            continue
        low = line.lower()

        if low.startswith("title "):
            title = line[6:].strip(); continue
        if low == "autonumber":
            autonum = True; continue
        if low.startswith("hide "):
            continue
        if low == "end box":
            if cur_box is not None:
                boxes[cur_box].last = len(order) - 1
            cur_box = None; continue
        m = BOX_RE.match(line)
        if m:
            boxes.append(Box(m.group(1), m.group(2) or "#F4F6F5", first=len(order)))
            cur_box = len(boxes) - 1; continue
        m = PART_RE.match(line)
        if m:
            kind, label, alias = m.group(1).lower(), m.group(2), m.group(3)
            parts[alias] = Participant(alias, label, kind, cur_box)
            order.append(alias); continue
        m = DIV_RE.match(line)
        if m:
            evs.append(Ev("divider", text=m.group(1))); continue
        m = NOTE_OVER_RE.match(line)
        if m:
            names = [n.strip() for n in m.group(1).split(",") if n.strip()]
            evs.append(Ev("note", a=names[0], b=names[-1], text=m.group(2), side="over"))
            continue
        m = NOTE_SIDE_RE.match(line)
        if m:
            evs.append(Ev("note", a=m.group(2), b=m.group(2), text=m.group(3),
                          side=m.group(1).lower()))
            continue
        if low == "end":
            evs.append(Ev("end")); continue
        if low.startswith("else"):
            evs.append(Ev("else", text=line[4:].strip())); continue
        m = GRP_RE.match(line)
        if m and not MSG_RE.match(line):
            evs.append(Ev("grp", a=m.group(1).lower(), text=m.group(2).strip()))
            continue
        m = MSG_RE.match(line)
        if m:
            a, arrow, b, txt = m.group(1), m.group(2), m.group(3), m.group(4)
            if a not in parts or b not in parts:
                print(f"  warn: unknown participant in: {line}", file=sys.stderr); continue
            evs.append(Ev("msg", a=a, b=b, text=txt,
                          dashed=arrow.startswith("--"), open_head=arrow.endswith(">>")))
            continue
        print(f"  warn: unsupported line ignored: {line}", file=sys.stderr)

    if cur_box is not None:
        boxes[cur_box].last = len(order) - 1

    if autonum:
        n = 0
        for e in evs:
            if e.kind == "msg":
                n += 1
                e.num = n
    return title, parts, order, boxes, evs


def layout(parts, order, evs):
    idx = {a: i for i, a in enumerate(order)}

    for p in parts.values():
        p.lines = lines_of(p.label, limit=132, size=FS_PART)
        p.w = max(PART_MIN_W, max(text_w(l, FS_PART) for l in p.lines) + PART_PAD_X * 2)
        p.h = len(p.lines) * (LINE_H + 2) + 16

    # widen the gap between adjacent columns so their messages fit
    need = [0.0] * max(len(order) - 1, 1)
    for e in evs:
        if e.kind != "msg":
            continue
        ls = lines_of(e.text)
        wmax = max(text_w(l, FS_MSG) for l in ls) + (34 if e.num else 12)
        i, j = idx[e.a], idx[e.b]
        if i == j:
            if i < len(need):
                need[i] = max(need[i], wmax + SELF_W + 16)
        elif abs(i - j) == 1:
            k = min(i, j)
            need[k] = max(need[k], wmax + 16)

    x = MARGIN_X
    for i, alias in enumerate(order):
        p = parts[alias]
        p.x = x + p.w / 2
        if i < len(order) - 1:
            nxt = parts[order[i + 1]]
            # cap how far one long adjacent label may push the columns apart;
            # wider spans are allowed to overhang their neighbours slightly.
            want = need[i] - p.w / 2 - nxt.w / 2 + BASE_GAP * 0.4
            gap = max(BASE_GAP, min(want, 108.0))
            x += p.w + gap
    total_w = x + parts[order[-1]].w + MARGIN_X

    head_h = max(p.h for p in parts.values())
    y = MARGIN_TOP + head_h + 26
    depth, stack = 0, []
    rects = []

    for e in evs:
        if e.kind == "msg":
            ls = lines_of(e.text)
            e.h = len(ls) * LINE_H + (34 if e.a == e.b else 14)
            e.y = y
            y += e.h + 8
        elif e.kind == "note":
            ls = lines_of(e.text, limit=430, size=FS_NOTE)
            e.h = len(ls) * LINE_H + 16
            e.y = y
            y += e.h + 14
        elif e.kind == "divider":
            e.y = y + 12
            y += 48
        elif e.kind == "grp":
            e.y = y
            stack.append((e, depth, y))
            depth += 1
            y += 30
        elif e.kind == "else":
            e.y = y + 8
            y += 26
        elif e.kind == "end":
            if stack:
                g, d, y0 = stack.pop()
                depth -= 1
                rects.append((g, d, y0, y + 8))
            y += 18
    while stack:
        g, d, y0 = stack.pop()
        rects.append((g, d, y0, y + 8))

    total_h = y + 24
    return idx, total_w, total_h, head_h, rects


def render(title, parts, order, boxes, evs, idx, W, H, head_h, rects) -> str:
    o: List[str] = []
    add = o.append
    top = MARGIN_TOP + (36 if title else 0)
    H += (36 if title else 0)

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="{FONT}">')
    add('<defs>'
        f'<marker id="ah" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="8" '
        f'markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="{C_ARROW}"/></marker>'
        f'<marker id="ao" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="8" '
        f'markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10" fill="none" '
        f'stroke="{C_ARROW}" stroke-width="1.4"/></marker></defs>')
    add(f'<rect width="{W:.0f}" height="{H:.0f}" fill="{C_BG}"/>')

    if title:
        add(f'<text x="{MARGIN_X}" y="{MARGIN_TOP + 4:.0f}" font-size="{FS_TITLE}" '
            f'font-weight="700" fill="{C_INK}">{escape(title)}</text>')

    # participant-group boxes
    for b in boxes:
        if b.last < b.first:
            continue
        p0, p1 = parts[order[b.first]], parts[order[b.last]]
        x0 = p0.x - p0.w / 2 - 12
        x1 = p1.x + p1.w / 2 + 12
        add(f'<rect x="{x0:.1f}" y="{top - 20:.1f}" width="{x1 - x0:.1f}" '
            f'height="{head_h + 30:.1f}" rx="4" fill="{b.color}" stroke="{C_BOX_ST}" '
            f'stroke-width="1"/>')
        add(f'<text x="{x0 + 9:.1f}" y="{top - 7:.1f}" font-size="10.5" font-weight="600" '
            f'letter-spacing="0.8" fill="{C_MUTED}">{escape(b.label.upper())}</text>')

    # lifelines + heads
    for alias in order:
        p = parts[alias]
        add(f'<line x1="{p.x:.1f}" y1="{top + head_h + 6:.1f}" x2="{p.x:.1f}" '
            f'y2="{H - 16:.1f}" stroke="{C_LIFE}" stroke-width="1.2" stroke-dasharray="4 4"/>')
        hx, hy = p.x - p.w / 2, top
        if p.kind == "database":
            add(f'<rect x="{hx:.1f}" y="{hy:.1f}" width="{p.w:.1f}" height="{p.h:.1f}" '
                f'rx="12" fill="#FFFFFF" stroke="{C_PART_ST}" stroke-width="1.4"/>')
        elif p.kind == "actor":
            add(f'<rect x="{hx:.1f}" y="{hy:.1f}" width="{p.w:.1f}" height="{p.h:.1f}" '
                f'rx="{p.h / 2:.1f}" fill="#FFFFFF" stroke="{C_PART_ST}" stroke-width="1.4"/>')
        else:
            add(f'<rect x="{hx:.1f}" y="{hy:.1f}" width="{p.w:.1f}" height="{p.h:.1f}" '
                f'rx="3" fill="#FFFFFF" stroke="{C_PART_ST}" stroke-width="1.4"/>')
        ty = hy + 16 + (p.h - len(p.lines) * (LINE_H + 2) - 16) / 2
        for i, l in enumerate(p.lines):
            add(f'<text x="{p.x:.1f}" y="{ty + i * (LINE_H + 2):.1f}" text-anchor="middle" '
                f'font-size="{FS_PART}" font-weight="{"700" if i == 0 else "400"}" '
                f'fill="{C_INK if i == 0 else C_MUTED}">{escape(l)}</text>')

    # group frames (behind messages)
    for g, d, y0, y1 in sorted(rects, key=lambda r: r[1]):
        inset = d * 9
        x0 = MARGIN_X - 12 + inset
        x1 = W - MARGIN_X + 12 - inset
        add(f'<rect x="{x0:.1f}" y="{y0 + top - MARGIN_TOP:.1f}" width="{x1 - x0:.1f}" '
            f'height="{y1 - y0:.1f}" rx="3" fill="none" stroke="{C_GRP}" '
            f'stroke-width="1.1" stroke-dasharray="3 3"/>')
        kw = text_w(g.a, FS_GROUP) + 16
        add(f'<path d="M{x0:.1f} {y0 + top - MARGIN_TOP:.1f} h{kw:.1f} l8 14 '
            f'v0 h-{kw + 8:.1f} z" fill="{C_GRP_TAB}" stroke="{C_GRP}" stroke-width="1.1"/>')
        add(f'<text x="{x0 + 8:.1f}" y="{y0 + top - MARGIN_TOP + 11:.1f}" '
            f'font-size="{FS_GROUP}" font-weight="700" fill="#2F5348">{escape(g.a)}</text>')
        if g.text:
            add(f'<text x="{x0 + kw + 14:.1f}" y="{y0 + top - MARGIN_TOP + 11:.1f}" '
                f'font-size="{FS_GROUP}" fill="{C_MUTED}">{escape(g.text)}</text>')

    dy = top - MARGIN_TOP
    for e in evs:
        y = e.y + dy
        if e.kind == "divider":
            add(f'<line x1="{MARGIN_X - 12}" y1="{y:.1f}" x2="{W - MARGIN_X + 12:.0f}" '
                f'y2="{y:.1f}" stroke="{C_DIV}" stroke-width="1"/>')
            tw = text_w(e.text, FS_DIV) + 26
            add(f'<rect x="{(W - tw) / 2:.1f}" y="{y - 13:.1f}" width="{tw:.1f}" height="26" '
                f'rx="13" fill="{C_GRP_TAB}" stroke="{C_DIV}" stroke-width="1"/>')
            add(f'<text x="{W / 2:.1f}" y="{y + 5:.1f}" text-anchor="middle" '
                f'font-size="{FS_DIV}" font-weight="700" fill="#2F5348">{escape(e.text)}</text>')

        elif e.kind == "else":
            add(f'<line x1="{MARGIN_X - 4}" y1="{y:.1f}" x2="{W - MARGIN_X + 4:.0f}" '
                f'y2="{y:.1f}" stroke="{C_GRP}" stroke-width="1" stroke-dasharray="3 3"/>')
            add(f'<text x="{MARGIN_X + 4}" y="{y - 5:.1f}" font-size="{FS_GROUP}" '
                f'font-style="italic" fill="{C_MUTED}">[{escape(e.text)}]</text>')

        elif e.kind == "note":
            ls = lines_of(e.text, limit=430, size=FS_NOTE)
            w = max(text_w(l, FS_NOTE) for l in ls) + 24
            pa, pb = parts[e.a], parts[e.b]
            if e.side == "right":
                x0 = pa.x + 22
            elif e.side == "left":
                x0 = pa.x - 22 - w
            else:
                x0 = (pa.x + pb.x) / 2 - w / 2
            x0 = min(max(x0, 8), W - w - 8)
            add(f'<path d="M{x0:.1f} {y:.1f} h{w - 10:.1f} l10 10 v{e.h - 10:.1f} '
                f'h-{w:.1f} z" fill="{C_NOTE_BG}" stroke="{C_NOTE_ST}" stroke-width="1"/>')
            add(f'<path d="M{x0 + w - 10:.1f} {y:.1f} v10 h10 z" fill="{C_NOTE_ST}" '
                f'opacity="0.5"/>')
            for i, l in enumerate(ls):
                add(f'<text x="{x0 + 12:.1f}" y="{y + 18 + i * LINE_H:.1f}" '
                    f'font-size="{FS_NOTE}" fill="#4A4028">{escape(l)}</text>')

        elif e.kind == "msg":
            ls = lines_of(e.text)
            pa, pb = parts[e.a], parts[e.b]
            dash = ' stroke-dasharray="6 4"' if e.dashed else ""
            head = "ao" if e.open_head else "ah"
            num = f'<tspan font-weight="700" fill="{C_GRP}">{e.num}. </tspan>' if e.num else ""
            if e.a == e.b:
                ay = y + len(ls) * LINE_H + 4
                add(f'<path d="M{pa.x:.1f} {ay:.1f} h{SELF_W} v20 h-{SELF_W}" fill="none" '
                    f'stroke="{C_ARROW}" stroke-width="1.3"{dash} marker-end="url(#{head})"/>')
                for i, l in enumerate(ls):
                    pre = num if i == 0 else ""
                    add(f'<text x="{pa.x + SELF_W + 10:.1f}" y="{y + 10 + i * LINE_H:.1f}" '
                        f'font-size="{FS_MSG}" fill="{C_INK}">{pre}{escape(l)}</text>')
            else:
                ay = y + len(ls) * LINE_H + 8
                x1, x2 = pa.x, pb.x
                sgn = 1 if x2 > x1 else -1
                add(f'<line x1="{x1 + sgn * 2:.1f}" y1="{ay:.1f}" x2="{x2 - sgn * 6:.1f}" '
                    f'y2="{ay:.1f}" stroke="{C_ARROW}" stroke-width="1.3"{dash} '
                    f'marker-end="url(#{head})"/>')
                mid = (x1 + x2) / 2
                for i, l in enumerate(ls):
                    pre = num if i == 0 else ""
                    add(f'<text x="{mid:.1f}" y="{y + 8 + i * LINE_H:.1f}" text-anchor="middle" '
                        f'font-size="{FS_MSG}" fill="{C_INK}">{pre}{escape(l)}</text>')

    add("</svg>")
    return "\n".join(o)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    src = open(sys.argv[1], encoding="utf-8").read()
    title, parts, order, boxes, evs = parse(src)
    if not order:
        print("error: no participants found", file=sys.stderr)
        return 1
    idx, W, H, head_h, rects = layout(parts, order, evs)
    svg = render(title, parts, order, boxes, evs, idx, W, H, head_h, rects)
    open(sys.argv[2], "w", encoding="utf-8").write(svg)
    print(f"wrote {sys.argv[2]}  ({W:.0f}x{H:.0f}px, {len(order)} participants, "
          f"{sum(1 for e in evs if e.kind == 'msg')} messages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
