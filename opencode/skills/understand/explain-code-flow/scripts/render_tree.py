#!/usr/bin/env python3
"""Render an explain-code-flow tree with aligned descriptions and boxed wire leaves.

Hand-counting leader dots drifts by a character or two on long trees, which is
worse than no alignment at all. Write the tree in the tiny DSL below and let this
script do the padding.

DSL, one line per node, read from stdin or a file:

    <glyphs><locator> @@ <description>     a spine line (a frame the debugger stops in)
    <prefix>##<LABEL>                      opens a boxed leaf; <prefix> is used verbatim
    <prefix>>> <body line>                 a line inside the open box
    anything else                          passed through untouched (▼ TRIGGER, blank lines)

Everything left of `##` / `>>` is the literal prefix, so you draw the runners
(`│  `) that place the box under its node. Example:

    └─ checkoutOrder (src/services/checkout.ts:118) @@ the order write
       └─ ⇢ src/db/queries/orders.ts:26 @@ a deliberately narrow projection
          ##SQL
          >> SELECT orders{id, tenant_id, currency}
          >> ← WHERE id = $1
          >> literal :29 · queryOne :28

The description column is derived from the longest locator in the input and held
for every spine line, so one invocation must cover the whole answer — rendering
two trees separately gives them two different columns.

    render_tree.py tree.txt
    render_tree.py --col 72 < tree.txt     # force a column
"""

import argparse
import sys

PAD = 5          # leader room past the longest locator: " " + >=2 dots + " "
WIDE = 100       # a column past this means the subtree is too deep to nest


def render(lines, forced_col=None):
    spines = [l.split("@@", 1) for l in lines if "@@" in l]
    if not spines and forced_col is None:
        return lines, None

    col = forced_col or max(len(s[0].rstrip()) for s in spines) + PAD
    out, box, prefix, label = [], [], "", ""

    def flush():
        nonlocal box
        if not box:
            return
        w = max(len(b) for b in box)
        out.append(f"{prefix}┌─ {label} " + "─" * (w - len(label) - 1) + "┐")
        out.extend(f"{prefix}│ {b.ljust(w)} │" for b in box)
        out.append(f"{prefix}└" + "─" * (w + 2) + "┘")
        box = []

    for line in lines:
        if "##" in line and "@@" not in line:
            flush()
            prefix, label = line.split("##", 1)
            label = label.strip()
        elif ">>" in line and "@@" not in line:
            box.append(line.split(">>", 1)[1].strip())
        elif "@@" in line:
            flush()
            locator, desc = line.split("@@", 1)
            locator = locator.rstrip()
            dots = col - 3 - len(locator)
            if dots < 1:
                out.append(f"{locator}  {desc.strip()}   # OVERFLOW: split with ↳")
            else:
                out.append(f"{locator} {'·' * dots} {desc.strip()}")
        else:
            flush()
            out.append(line)
    flush()
    return out, col


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", nargs="?", help="DSL file; defaults to stdin")
    ap.add_argument("--col", type=int, help="force the description column")
    args = ap.parse_args()

    src = open(args.file) if args.file else sys.stdin
    lines = [l.rstrip("\n") for l in src]

    out, col = render(lines, args.col)
    print("\n".join(out))

    if col and col > WIDE:
        print(
            f"\n# column {col} exceeds {WIDE} — the deepest subtree is too deep to nest.\n"
            f"# Pull it out as its own tree and point at it with ↳ rather than widening.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
