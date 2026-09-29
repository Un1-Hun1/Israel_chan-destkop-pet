"""Pixel-art sprites for the desktop pet, drawn as character grids.

Rows given as 14 characters are the left half and get mirrored into a
symmetric 28-pixel row. Asymmetric details (bow, braid, hair clips,
armband) are stamped on top afterwards.
"""
from PIL import Image

KEY = (255, 0, 255)  # transparency key colour (never used in the sprite)

PALETTE = {
    "K": (60, 30, 44),     # outline
    "H": (244, 166, 156),  # hair (peach pink)
    "h": (214, 118, 112),  # hair shadow
    "L": (255, 212, 204),  # hair highlight
    "S": (255, 232, 220),  # skin
    "s": (242, 190, 174),  # skin shadow
    "I": (150, 14, 40),    # iris dark
    "E": (250, 70, 90),    # iris light
    "e": (255, 255, 255),  # eye shine
    "B": (255, 158, 168),  # blush
    "M": (194, 74, 90),    # mouth
    "W": (255, 255, 255),  # white uniform
    "w": (212, 220, 240),  # uniform shadow
    "U": (31, 95, 214),    # blue trim / stars
    "R": (222, 40, 60),    # red ribbon / tie
    "r": (158, 20, 40),    # dark red
    "N": (40, 34, 48),     # black (belt, tights, armband)
    "n": (80, 70, 96),     # tights highlight
    "O": (26, 22, 32),     # shoes
    "Y": (255, 255, 255),  # hair-clip star
    "F": (255, 150, 40),   # flame orange
    "f": (255, 234, 110),  # flame yellow
    "P": (255, 90, 130),   # heart
    "Z": (170, 190, 255),  # zzz
}

W = 28


def row(r):
    if len(r) == 14:
        return r + r[::-1]
    assert len(r) <= W, (r, len(r))
    return r.ljust(W, ".")


def segs(*parts):
    """Build a row from (start_col, pattern) pairs."""
    r = ["."] * W
    for col, pat in parts:
        for i, ch in enumerate(pat):
            r[col + i] = ch
    return "".join(r)


HEAD_TOP = [
    ".........KKKKK",
    ".......KKHHHHH",
    "......KHHHHHHH",
    ".....KHHLLHHHH",
    "....KHHLHHHHHH",
    "...KHHHHHHhHHH",
    "...KHHHHhHHHhH",
    "...KHHHhSShHhS",
    "...KHHhSSSSShS",
]

EYES = {
    "open": [
        "...KHHhKKKKKSS",
        "...KHHhSKeIISS",
        "...KHHhSKIEESS",
        "...KHHhSSsEsSS",
    ],
    "closed": [
        "...KHHhSSSSSSS",
        "...KHHhSSSSSSS",
        "...KHHhKKKKKSS",
        "...KHHhSSsssSS",
    ],
    "happy": [
        "...KHHhSSSSSSS",
        "...KHHhSSKKSSS",
        "...KHHhSKSSKSS",
        "...KHHhSSSSSSS",
    ],
    "shock": [
        "...KHHhSKKKKSS",
        "...KHHhSKeeKSS",
        "...KHHhSKeIKSS",
        "...KHHhSSKKSSS",
    ],
}

MOUTH = {
    "smile": "...KHHhSSSSSSM",
    "open":  "...KHHhSSSSSKM",
    "flat":  "...KHHhSSSSSSK",
}

HEAD_LOW = [
    "...KHHhSBBSSSS",
    None,  # mouth
    "...KHHHKSSSSSS",
    "...KHHHHKKSSSS",
    "..KHHHHHHHKKKK",
]

HEAD_ROWS = len(HEAD_TOP) + 4 + len(HEAD_LOW)

TORSO = {
    "down": [
        "..KHHHHHHHHKsS",
        "..KHHHHKKKKWWK",
        "..KHHHKWWWWWKR",
        "..KHHKWWWWWKRr",
        "..KHHKWWKWWUNR",
        "..KHHKWWKWWUNR",
        "..KHHKWwKWWWUN",
        "..KHHKWWKKNNNN",
        "..KHHKUUKKNNNn",
        "..KHHKSSKWWWWW",
    ],
    "up": [
        "..KHHHHHHHHKsS",
        "..KHHHHKKKKWWK",
        "KKKKKKKWWWWWKR",
        "SUWWWWWWWWWKRr",
        "KKKKKKKWWWWUNR",
        "..KHHHHKWWWUNR",
        "..KHHHHKWwWWUN",
        "..KHHHHKKKNNNN",
        "..KHHHHHKKNNNn",
        "..KHHHHHKWWWWW",
    ],
}

SKIRT = {
    "down": [
        "..KHHKSSKWWWWW",
        "...KHKKKWWWWWW",
        "...KHKWWWwWWWW",
        "...KKWWWwWWWWW",
        "...KWWWwWWWWWW",
        "..KUUUUUUUUUUU",
        "..KKKKKKKKKKKK",
    ],
    "up": [
        "..KHHHHKWWWWWW",
        "...KHHKWWWWWWW",
        "...KHKWWWwWWWW",
        "...KKWWWwWWWWW",
        "...KWWWwWWWWWW",
        "..KUUUUUUUUUUU",
        "..KKKKKKKKKKKK",
    ],
}

THIGHS = [
    "........KNnNNK",
    "........KNnNNK",
]
SHIN = [".KnNK", ".KnNK", ".KnNK", "KOOOK", "KKKKK"]
SHIN_X = 8


def _legs(right_dx):
    rows = list(THIGHS)
    for i, pat in enumerate(SHIN):
        rx = W - SHIN_X - len(pat)
        rows.append(segs((SHIN_X, pat), (rx + right_dx[i], pat[::-1])))
    return rows


LEGS = {
    "stand": _legs([0] * 5),
    "swing": _legs([0, 1, 1, 2, 2]),
    "step": [
        segs((8, "KNnNNKKNNnNK")),
        segs((7, "KNnNNK"), (15, "KNNnNK")),
        segs((7, "KnNK"), (17, "KNnK")),
        segs((6, "KnNK"), (18, "KNnK")),
        segs((5, "KnNK"), (19, "KNnK")),
        segs((4, "KOOOK"), (19, "KOOOK")),
        segs((4, "KKKKK"), (19, "KKKKK")),
    ],
    "none": ["." * 14] * 7,
}

BOW = [  # red ribbon on the side ponytail
    "KK...KK",
    "KRK.KRK",
    "KRRrRRK",
    "KRK.KrK",
    "KK...KK",
]
CLIP_STAR = [
    "..U..",
    "UUUUU",
    ".UYU.",
    "UUUUU",
    "..U..",
]
APRON_STAR = [
    "..UU..",
    "UUUUUU",
    ".U..U.",
    "UUUUUU",
    "..UU..",
]

EFFECTS = {
    "heart": [
        ".PP.PP.",
        "PPPPPPP",
        "PPPPPPP",
        ".PPPPP.",
        "..PPP..",
        "...P...",
    ],
    "z": [
        "ZZZZ",
        "..Z.",
        ".Z..",
        "ZZZZ",
    ],
    "zz": [
        "....ZZZ",
        "ZZZZ.Z.",
        "..ZZZZZ",
        ".Z.....",
        "ZZZZ...",
    ],
}

TOP_MARGIN = 7   # empty rows above the head for effects
SIDE_MARGIN = 4  # empty columns on each side

GRID_W = W + SIDE_MARGIN * 2
BODY_ROWS = HEAD_ROWS + len(TORSO["down"]) + len(SKIRT["down"])
GRID_H = TOP_MARGIN + BODY_ROWS + len(LEGS["stand"])
STAND_FOOT_ROW = GRID_H                 # feet at the very bottom
SIT_FOOT_ROW = TOP_MARGIN + BODY_ROWS   # skirt hem sits on the surface
TORSO_Y = HEAD_ROWS
SKIRT_Y = HEAD_ROWS + len(TORSO["down"])


def build(eyes="open", mouth="smile", arms="down", legs="stand", effect=None,
          effect_pos=(0, 0)):
    rows = list(HEAD_TOP) + EYES[eyes]
    for r in HEAD_LOW:
        rows.append(MOUTH[mouth] if r is None else r)
    rows += TORSO[arms] + SKIRT[arms] + LEGS[legs]

    grid = [["."] * GRID_W for _ in range(GRID_H)]
    ox, oy = SIDE_MARGIN, TOP_MARGIN

    def stamp(pattern, x0, y0):
        for y, r in enumerate(pattern):
            for x, ch in enumerate(r):
                if ch != "." and 0 <= y0 + y < GRID_H and 0 <= x0 + x < GRID_W:
                    grid[y0 + y][x0 + x] = ch

    stamp([row(r) for r in rows], ox, oy)
    # braid down the left side of the hair
    for y in range(HEAD_ROWS - 3, SKIRT_Y + 1):
        grid[oy + y][ox + 3] = "h" if y % 2 else "L"
    stamp(BOW, ox + 20, oy)
    stamp(CLIP_STAR, ox + 5, oy + 3)
    stamp(APRON_STAR, ox + 11, oy + SKIRT_Y + 1)
    if arms == "down":  # black armband on her left arm
        grid[oy + TORSO_Y + 4][ox + 20] = "N"
        grid[oy + TORSO_Y + 4][ox + 21] = "N"
    if effect:
        stamp(EFFECTS[effect], *effect_pos)
    return grid


ROCKET = [  # white-and-blue rocket pointing right
    "..KKKK",
    "..KUUUK",
    "..KUUUUKKKKKKKKKKKKKKKKKKKKKKKKKK",
    "...KUUKWWWWUUWWWWWWWWWWWWUUWWWWWKKK",
    "...KKWWWWWWUUWWWWKKKKWWWWUUWWWWWWWUKK",
    "KKKKWWWWWWWUUWWWKYYYYKWWWUUWWWWWWWUUUKK",
    "KwwKWWWWWWWUUWWWKYYYYKWWWUUWWWWWWWUUUUUK",
    "KKKKWWWWWWWUUWWWWKKKKWWWWUUWWWWWWWUUUKK",
    "...KKwwwwwwUUwwwwwwwwwwwwUUwwwwwwwUKK",
    "...KUUKwwwwUUwwwwwwwwwwwwUUwwwwwKKK",
    "..KUUUUKKKKKKKKKKKKKKKKKKKKKKKKKK",
    "..KUUUK",
    "..KKKK",
]
FLAMES = [
    [
        "....RRRR",
        "..RRFFFF",
        "RRFFffff",
        "..RRFFFF",
        "....RRRR",
    ],
    [
        "......RR",
        "...RRFFF",
        ".RRFFfff",
        "...RRFFF",
        "......RR",
    ],
]
FLAME_W = 8
ROCKET_W = FLAME_W + max(len(r) for r in ROCKET)


def blank(w, h):
    return [["."] * w for _ in range(h)]


def stamp_into(grid, pattern, x0, y0):
    for y, r in enumerate(pattern):
        for x, ch in enumerate(r):
            if ch != "." and 0 <= y0 + y < len(grid) and 0 <= x0 + x < len(grid[0]):
                grid[y0 + y][x0 + x] = ch


def rocket_grid(flame):
    g = blank(ROCKET_W, len(ROCKET))
    stamp_into(g, ROCKET, FLAME_W, 0)
    stamp_into(g, FLAMES[flame], 0, 4)
    return g


def riding_rocket(flame):
    """Her sitting astride the rocket, arms up. Returns (grid, foot_row)."""
    girl = build(eyes="happy", mouth="open", arms="up", legs="none")
    seat = SIT_FOOT_ROW - 2           # rocket top overlaps the skirt hem
    h = seat + len(ROCKET)
    g = blank(ROCKET_W, h)
    stamp_into(g, girl[:SIT_FOOT_ROW], FLAME_W + 20 - GRID_W // 2, 0)
    stamp_into(g, rocket_grid(flame), 0, seat)
    return g, h


def canopy(width, height):
    """Blue-and-white striped parachute dome."""
    g = blank(width, height)
    cx, rx = (width - 1) / 2, width / 2
    inside = [[((x - cx) / rx) ** 2 + ((height - 0.5 - y) / height) ** 2 <= 1
               for x in range(width)] for y in range(height)]
    for y in range(height):
        for x in range(width):
            if not inside[y][x]:
                continue
            edge = (y == height - 1 or x in (0, width - 1) or
                    not inside[y - 1][x] or not inside[y][x - 1] or not inside[y][x + 1])
            g[y][x] = "K" if edge else ("U" if (x * 6 // width) % 2 else "W")
    return g


def line(grid, x0, y0, x1, y1, ch="K"):
    steps = max(abs(x1 - x0), abs(y1 - y0))
    for i in range(steps + 1):
        x = round(x0 + (x1 - x0) * i / steps)
        y = round(y0 + (y1 - y0) * i / steps)
        grid[y][x] = ch


PARA_H = 10   # canopy height
PARA_TOP = 8  # rows added above the normal sprite


def parachuting(legs):
    girl = build(eyes="happy", mouth="smile", arms="up", legs=legs)
    g = blank(GRID_W, GRID_H + PARA_TOP)
    hand_y = PARA_TOP + TOP_MARGIN + TORSO_Y + 3
    line(g, 1, PARA_H - 1, SIDE_MARGIN, hand_y)
    line(g, GRID_W - 2, PARA_H - 1, GRID_W - 1 - SIDE_MARGIN, hand_y)
    line(g, GRID_W // 2 - 6, PARA_H - 1, SIDE_MARGIN + 6, hand_y + 2)
    line(g, GRID_W // 2 + 5, PARA_H - 1, GRID_W - 1 - SIDE_MARGIN - 6, hand_y + 2)
    stamp_into(g, girl, 0, PARA_TOP)
    stamp_into(g, canopy(GRID_W, PARA_H), 0, 0)
    return g, GRID_H + PARA_TOP


def render(grid, scale):
    img = Image.new("RGB", (len(grid[0]), len(grid)), KEY)
    px = img.load()
    for y, r in enumerate(grid):
        for x, ch in enumerate(r):
            if ch != ".":
                px[x, y] = PALETTE[ch]
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


# foot row (in sprite pixels) of frames whose feet are not at the bottom edge
FOOT_ROWS = {}


def frames(scale):
    """Return {name: PIL.Image} for every animation frame (facing right)."""
    heart = dict(effect="heart", effect_pos=(29, 0))
    z1 = dict(effect="z", effect_pos=(30, 2))
    z2 = dict(effect="zz", effect_pos=(29, 0))
    f = {
        "idle": build(),
        "blink": build(eyes="closed"),
        "walk1": build(legs="step"),
        "walk2": build(legs="stand"),
        # sitting on a window edge, legs dangling
        "sit1": build(legs="stand"),
        "sit2": build(legs="swing"),
        "sit_blink": build(eyes="closed"),
        "sleep1": build(eyes="closed", mouth="flat", **z1),
        "sleep2": build(eyes="closed", mouth="flat", **z2),
        # sitting on the ground (legs tucked under the skirt)
        "gsit1": build(legs="none"),
        "gsit2": build(legs="none"),
        "gsit_blink": build(eyes="closed", legs="none"),
        "gsleep1": build(eyes="closed", mouth="flat", legs="none", **z1),
        "gsleep2": build(eyes="closed", mouth="flat", legs="none", **z2),
        "fall": build(eyes="shock", mouth="open", arms="up", legs="swing"),
        "drag1": build(eyes="shock", mouth="open", arms="up", legs="stand"),
        "drag2": build(eyes="shock", mouth="open", arms="up", legs="swing"),
        "happy1": build(eyes="happy", mouth="open", **heart),
        "happy2": build(eyes="happy", mouth="smile", effect="heart", effect_pos=(29, 1)),
        "jump": build(eyes="happy", mouth="open", arms="up", legs="step"),
    }
    for k in ("sit1", "sit2", "sit_blink", "sleep1", "sleep2",
              "gsit1", "gsit2", "gsit_blink", "gsleep1", "gsleep2"):
        FOOT_ROWS[k] = SIT_FOOT_ROW
    for i in (0, 1):
        f[f"rocket{i + 1}"], FOOT_ROWS[f"rocket{i + 1}"] = riding_rocket(i)
        f[f"rocket_only{i + 1}"] = rocket_grid(i)
    f["para1"], FOOT_ROWS["para1"] = parachuting("stand")
    f["para2"], FOOT_ROWS["para2"] = parachuting("swing")
    out = {k: render(v, scale) for k, v in f.items()}
    for k, img in out.items():
        FOOT_ROWS.setdefault(k, img.height // scale)
    return out


if __name__ == "__main__":
    import sys
    fr = frames(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    names = ["idle", "walk1", "happy1", "rocket1", "rocket2", "para1", "para2"]
    w = sum(fr[n].width for n in names)
    h = max(fr[n].height for n in names)
    sheet = Image.new("RGB", (w, h), (230, 230, 230))
    x = 0
    for n in names:
        sheet.paste(fr[n], (x, h - fr[n].height))
        x += fr[n].width
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "preview.png")
