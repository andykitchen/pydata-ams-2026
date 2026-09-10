#!/usr/bin/env python3
"""Compare <slide> cues in the talk sections with the reveal.js deck.

Reads every numbered section file (01.md, 02-*.md, ...) and counts the
explicit slide-advance cues, i.e. lines consisting solely of <slide>.
It then reads the reveal.js presentation (../index.html by default) and
counts, for each top-level <section> group, the number of slides it
contains: a group with nested <section> elements contributes one slide
per nested element, while a childless top-level <section> is a single
slide.

The pairing between script files and deck groups is taken from the HTML
comments "<!-- Section N - ... -->" in index.html, where N is the number
of the section file.  Deck groups without a numbered section comment
(title slide, appendix) are listed at the bottom as unmatched.

The table shows, for every section, the number of <slide> cues found in
the script versus the number of slides in the deck, together with their
difference, so that missing or superfluous slide cues stand out at a
glance.

Usage:
    python3 slide-count.py [--dir .] [--html ../index.html]

Only the standard library is used.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

NUMBERED_RE = re.compile(r"^(\d{2})")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TARGET_RE = re.compile(r"\((\d+(?:\.\d+)?)\s*m(?:in)?\)\s*$")
SLIDE_RE = re.compile(r"^<\s*slide\s*>\s*$", re.IGNORECASE)
SECTION_COMMENT_RE = re.compile(r"^Section\s+(\d+)\s*-\s*(.*)$")
HASHES_RE = re.compile(r"^#+\s*")


def truncate(text, width):
    return text if len(text) <= width else text[: width - 1] + "\u2026"


def parse_section(path):
    """Parse one section file.

    Returns (number, title, slide_cues).
    """
    number = int(NUMBERED_RE.match(path.name).group(1))
    title = path.stem.replace("-", " ").strip()
    slides = 0

    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if SLIDE_RE.match(line):
            slides += 1
            continue
        heading = HEADING_RE.match(line)
        if heading:
            title = TARGET_RE.sub("", heading.group(2)).strip(" -\u2013")
    return number, title, slides


class DeckParser(HTMLParser):
    """Collect the top-level <section> groups of a reveal.js deck.

    A group is one top-level <section> element; each nested <section>
    inside it is one slide, and a childless top-level <section> is a
    single slide.  The label of a group is the last HTML comment seen
    before the group's opening tag.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.groups = []
        self._depth = 0
        self._nested = 0
        self._label = ""
        self._comment = ""

    def handle_comment(self, data):
        self._comment = data.strip()

    def handle_starttag(self, tag, attrs):
        if tag != "section":
            return
        if self._depth == 0:
            self._label = self._comment
            self._nested = 0
        else:
            self._nested += 1
        self._depth += 1

    def handle_endtag(self, tag):
        if tag != "section":
            return
        self._depth -= 1
        if self._depth == 0:
            slides = self._nested if self._nested else 1
            number = None
            title = self._label
            match = SECTION_COMMENT_RE.match(self._label)
            if match:
                number = int(match.group(1))
                title = HASHES_RE.sub("", match.group(2)).strip()
                title = TARGET_RE.sub("", title).strip(" -\u2013")
            self.groups.append(
                {"number": number, "title": title or self._label, "slides": slides}
            )


def parse_deck(path):
    parser = DeckParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.groups


def main():
    default_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Compare <slide> cues in the script with the slides in index.html.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dir", type=Path, default=default_dir,
        help="directory containing the numbered section files",
    )
    parser.add_argument(
        "--html", type=Path, default=default_dir.parent / "index.html",
        help="the reveal.js presentation to compare against",
    )
    args = parser.parse_args()

    files = sorted(
        p for p in args.dir.glob("*.md") if NUMBERED_RE.match(p.name)
    )
    if not files:
        sys.exit(f"No numbered section files found in {args.dir}")
    if not args.html.is_file():
        sys.exit(f"Presentation file not found: {args.html}")

    groups = parse_deck(args.html)
    by_number = {g["number"]: g for g in groups if g["number"] is not None}

    print("Slide cues in the script vs. slides in the reveal.js deck\n")
    header = f"{'File':<27}{'Script':>7}{'Deck':>6}{'Diff':>6}  Section"
    print(header)
    print("-" * len(header))

    total_script = 0
    total_deck = 0
    used = set()

    for path in files:
        number, title, slides = parse_section(path)
        group = by_number.get(number)
        if group:
            used.add(number)
            deck = group["slides"]
            label = truncate(group["title"], 40)
        else:
            deck = 0
            label = truncate(title, 40) + " (not in deck)"
        diff = slides - deck
        total_script += slides
        total_deck += deck
        diff_str = f"{diff:+d}" if diff else "0"
        print(f"{path.name:<27}{slides:>7}{deck:>6}{diff_str:>6}  {label}")

    for group in groups:
        if group["number"] is None or group["number"] not in used:
            total_deck += group["slides"]
            label = truncate(group["title"] or "(unlabelled)", 40)
            print(f"{'-':<27}{'-':>7}{group['slides']:>6}{'':>6}  {label}")

    print("-" * len(header))
    diff_total = total_script - total_deck
    diff_str = f"{diff_total:+d}" if diff_total else "0"
    print(f"{'TOTAL':<27}{total_script:>7}{total_deck:>6}{diff_str:>6}")
    print(
        f"\nTotal: {total_script} <slide> cues in {len(files)} script sections vs. "
        f"{total_deck} slides in {len(groups)} deck groups"
    )


if __name__ == "__main__":
    main()
