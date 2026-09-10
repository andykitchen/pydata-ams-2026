#!/usr/bin/env python3
"""Estimate the running time of the talk sections in this directory.

Reads every numbered section file (01.md, 02.md, ..., 10-*.md), counts the
spoken dialog words and estimates the running time at a given speaking rate
(110 wpm by default), adding a fixed allowance (2 seconds by default) for
every character (speaker) change, e.g. each handover between [M] and [E].

Not counted as dialog:
  * markdown headings (## / ### ...),
  * speaker tags such as [M] or [E],
  * stage directions on their own line, such as _pause_.

The parenthetical "(3m)" target found in each section heading is shown for
comparison against the estimate.
"""

import argparse
import re
import sys
from pathlib import Path

SPEAKER_RE = re.compile(r"^\[([A-Za-z][A-Za-z0-9]*)\]\s*$")
STAGE_RE = re.compile(r"^_[^_]{1,40}_$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TARGET_RE = re.compile(r"\((\d+(?:\.\d+)?)\s*m(?:in)?\)\s*$")
NUMBERED_RE = re.compile(r"^\d{2}")


def fmt_mmss(total_seconds):
    total = int(round(total_seconds))
    return f"{total // 60}:{total % 60:02d}"


def truncate(text, width):
    return text if len(text) <= width else text[: width - 1] + "\u2026"


def parse_section(path):
    """Parse one section file.

    Returns (title, target_min, words, changes, stage_directions, empty).
    """
    words = 0
    changes = 0
    stage_directions = 0
    prev_speaker = None
    title = path.stem.replace("-", " ").strip()
    target_min = None

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return title, target_min, 0, 0, 0, True

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        heading = HEADING_RE.match(line)
        if heading:
            title = heading.group(2).strip()
            match = TARGET_RE.search(title)
            if match:
                target_min = float(match.group(1))
                title = TARGET_RE.sub("", title).strip(" -\u2013")
            continue

        speaker = SPEAKER_RE.match(line)
        if speaker:
            current = speaker.group(1)
            if prev_speaker is not None and current != prev_speaker:
                changes += 1
            prev_speaker = current
            continue

        if STAGE_RE.match(line):
            stage_directions += 1
            continue

        words += len(line.split())

    return title, target_min, words, changes, stage_directions, False


def main():
    default_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Estimate talk running time from dialog word counts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dir", type=Path, default=default_dir,
        help="directory containing the numbered section files",
    )
    parser.add_argument(
        "--wpm", type=float, default=110.0,
        help="speaking rate in words per minute",
    )
    parser.add_argument(
        "--change-secs", type=float, default=2.0,
        help="seconds allowed per character (speaker) change",
    )
    parser.add_argument(
        "--section-secs", type=float, default=5.0,
        help="seconds per section change",
    )
    args = parser.parse_args()

    files = sorted(
        p for p in args.dir.glob("*.md") if NUMBERED_RE.match(p.name)
    )
    if not files:
        sys.exit(f"No numbered section files found in {args.dir}")

    print(
        f"Talk running-time estimate "
        f"({args.wpm:g} wpm, {args.change_secs:g}s per character change)\n"
    )
    header = (
        f"{'File':<27}{'Words':>7}{'Chg':>5}{'Speaking':>10}"
        f"{'Total':>9}{'Target':>9}  Section"
    )
    print(header)
    print("-" * len(header))

    total_words = 0
    total_changes = 0
    total_sections = 0
    total_seconds = 0.0
    targets = []

    for path in files:
        title, target_min, words, changes, stages, empty = parse_section(path)
        speaking_secs = words / args.wpm * 60
        total_secs = speaking_secs + changes * args.change_secs + args.section_secs

        total_words += words
        total_changes += changes
        total_seconds += total_secs
        total_sections += 1
        if target_min is not None:
            targets.append(target_min)

        target_str = f"{target_min:g}m" if target_min is not None else "-"
        note = " (empty)" if empty else ""
        print(
            f"{path.name:<27}{words:>7,}{changes:>5}"
            f"{fmt_mmss(speaking_secs):>10}{fmt_mmss(total_secs):>9}"
            f"{target_str:>9}  {truncate(title, 40)}{note}"
        )
        #if stages:
        #    print(f"{'':<27}(skipped {stages} stage direction(s))")

    print("-" * len(header))
    target_total = f"{sum(targets):g}m" if targets else "-"
    print(
        f"{'TOTAL':<27}{total_words:>7,}{total_changes:>5}"
        f"{fmt_mmss(total_words / args.wpm * 60):>10}"
        f"{fmt_mmss(total_seconds):>9}{target_total:>9}"
    )
    print(
        f"\nTotal: {total_words:,} dialog words at {args.wpm:g} wpm "
        f"= {total_seconds / 60:.1f} minutes "
        f"({fmt_mmss(total_seconds)} incl. {total_changes} character changes and {total_sections} sections"
        f"@ {args.change_secs:g}s / {args.section_secs:g}s)"
    )


if __name__ == "__main__":
    main()
