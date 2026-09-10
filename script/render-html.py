#!/usr/bin/env python3
"""Join the numbered script markdown files into a single static HTML file.

Reads every numbered section file in this directory (01-*.md, 02-*.md, ...)
and renders them into one large-print, minimal, single-file HTML page for
internal read-through use (both speakers read off the same screen).

Semantics handled:
  * Files            -> <section> with an <h1> heading (+ TOC entry).
  * Internal headers (## / ### ...) -> <h2> sub-headings (unread, for scanning).
  * Speaker turns    -> one <article class="speech speaker-m|speaker-e"> bubble
                        per paragraph for [M] (MIDWYFE) and [E] (ENTROPEAN);
                        consecutive short paragraphs may share a bubble, so no
                        single bubble is ever close to a full page.
  * Actions          -> <p class="action">, e.g. a line that is only _pause_
                        or _Laura and Andy pause and swap hats_.
  * Slide cues       -> <div class="slide">, for `<slide>` lines and for
                        `*Slide: ...*` lines.

The page also embeds a tiny script: clicking any bubble, cue or heading
focuses it, and the up/down arrow keys step through the script line by line.

Usage:
    python3 render-html.py [--output script.html] [--dir .]

Only the standard library is used; the stylesheet lives in a <style> block
at the top of the generated file.
"""

import argparse
import html
import re
from pathlib import Path

SPEAKER_RE = re.compile(r"^\[([A-Za-z][A-Za-z0-9]*)\]\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
NUMBERED_RE = re.compile(r"^\d{2}")
SLIDE_TAG_RE = re.compile(r"^<\s*slide\s*>\s*$", re.IGNORECASE)
# A line fully wrapped in _..._ or *...* is a stage direction / action cue,
# e.g. `_pause_` or `*Slide: "..."*` or `_Laura and Andy swap hats_`.
ACTION_RE = re.compile(r"^(?:_([^_]+)_|\*([^*]+)\*)\s*$")
SLIDE_CUE_RE = re.compile(r"^slide\s*:", re.IGNORECASE)

SPEAKERS = {
    "M": "MIDWYFE",
    "E": "ENTROPEAN",
}

# A paragraph at or below this word count is "short" and may share a bubble
# with a short neighbour instead of getting one to itself.
SHORT_WORDS = 35

INLINE_RE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|_[^_]+?_)")


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def render_inline(text):
    """Escape HTML then apply minimal inline markdown (*em*, _em_, **strong**)."""
    parts = INLINE_RE.split(html.escape(text))
    out = []
    for part in parts:
        if len(part) >= 4 and part.startswith("**") and part.endswith("**"):
            out.append(f"<strong>{part[2:-2]}</strong>")
        elif (
            len(part) >= 2
            and ((part.startswith("*") and part.endswith("*"))
                 or (part.startswith("_") and part.endswith("_")))
        ):
            out.append(f"<em>{part[1:-1]}</em>")
        else:
            out.append(part)
    return "".join(out)


def flush_paragraph(buffer, blocks):
    """Join wrapped markdown lines into one <p>, or <blockquote> for quotes."""
    # Strip empty lines; group may still be empty.
    lines = [ln for ln in buffer]
    buffer.clear()
    if not lines:
        return
    if all(ln.lstrip().startswith(">") for ln in lines):
        stripped = [re.sub(r"^\s*>\s?", "", ln) for ln in lines]
        text = " ".join(s.strip() for s in stripped if s.strip())
        blocks.append(f"<blockquote>{render_inline(text)}</blockquote>")
    else:
        text = " ".join(ln.strip() for ln in lines if ln.strip())
        if text:
            blocks.append(f"<p>{render_inline(text)}</p>")


def _plain_words(chunk):
    """Word count of an HTML chunk, ignoring tags."""
    return len(re.sub(r"<[^>]+>", "", chunk).split())


def _is_short(chunk, words):
    return words <= SHORT_WORDS and not chunk.startswith("<blockquote")


def flush_speech(blocks, speaker, paras):
    """Emit one <article> bubble per paragraph of the speaker's turn.

    Consecutive short paragraphs (e.g. a one-line punchline following a
    short setup) may share a bubble, and a short trailing line joins the
    previous bubble rather than sitting alone -- but no bubble ever holds
    more than a few short paragraphs, so each stays well under a page.
    Continuation bubbles after the first carry a small "(cont.)" marker.
    """
    if speaker is None or not paras:
        return
    key = speaker.upper()
    name = SPEAKERS.get(key, key)
    cls = f"speaker-{key.lower()}"

    groups = []  # each group: list of (html, words, is_short)
    for chunk in paras:
        words = _plain_words(chunk)
        short = _is_short(chunk, words)
        if (
            short
            and groups
            and len(groups[-1]) < 2
            and all(s for _, _, s in groups[-1])
        ):
            groups[-1].append((chunk, words, short))
        else:
            groups.append([(chunk, words, short)])
    # A short trailing line should not sit in a bubble on its own.
    if len(groups) > 1 and len(groups[-1]) == 1 and groups[-1][0][2]:
        groups[-2].append(groups[-1][0])
        groups.pop()
        if len(groups[-1]) > 2:
            # Pair from the end so the turn still ends on a shared bubble.
            groups[-1:] = [groups[-1][:1], groups[-1][1:]]

    for n, group in enumerate(groups):
        inner = "\n".join(h for h, _, _ in group)
        badge = f"{html.escape(key)} &middot; {html.escape(name)}"
        cont = ""
        if n:
            badge += ' <span class="cont-mark">(cont.)</span>'
            cont = " cont"
        blocks.append(
            f'<article class="speech {cls}{cont}" data-speaker="{html.escape(key)}">\n'
            f'<header class="who" aria-label="Speaker {html.escape(name)}">'
            f'<span class="badge">{badge}</span></header>\n'
            f"{inner}\n"
            f"</article>"
        )


def render_section(path, index):
    """Render one markdown file -> (section_id, title, html, slide_count)."""
    raw = path.read_text(encoding="utf-8")
    section_id = f"s{index:02d}-{slugify(path.stem[3:] or path.stem)}"
    title = path.stem.replace("-", " ").strip()
    sub_id = 0

    blocks = []        # finished top-level HTML chunks for this section
    paras = []         # finished <p>/etc chunks for the open speech block
    buf = []           # wrapped lines accumulating into one paragraph
    speaker = None     # current speaker key ("M"/"E") or None
    slides = 0

    def emit_bubbles():
        """Flush the open paragraph and emit one bubble per paragraph."""
        flush_paragraph(buf, paras)
        flush_speech(blocks, speaker, paras)
        paras.clear()

    def close_speech():
        nonlocal speaker
        emit_bubbles()
        speaker = None

    first_heading_seen = False
    slide_cue_buf = []  # accumulates a `*Slide: ...*` cue wrapped over lines
    for raw_line in raw.splitlines():
        line = raw_line.strip()

        # A slide-content cue may wrap over several lines; gather them
        # into one logical line before matching.
        if slide_cue_buf:
            slide_cue_buf.append(line)
            if line.endswith("*"):
                line = " ".join(slide_cue_buf)
                slide_cue_buf = []
            else:
                continue
        elif re.match(r"^\*slide\s*:", line, re.IGNORECASE) and not line.endswith("*"):
            slide_cue_buf.append(line)
            continue

        if not line:
            if speaker is not None:
                flush_paragraph(buf, paras)
            else:
                flush_paragraph(buf, blocks)
            continue

        heading = HEADING_RE.match(line)
        if heading:
            close_speech()
            flush_paragraph(buf, blocks)
            text = heading.group(2).strip()
            if not first_heading_seen:
                # The file's own title becomes the section <h1>.
                title = re.sub(r"\s*\(\d+(?:\.\d+)?\s*m(?:in)?\)\s*$", "", text).strip()
                first_heading_seen = True
                continue
            sub_id += 1
            hid = f"{section_id}-{slugify(text) or sub_id}"
            blocks.append(
                f'<h2 id="{hid}">{render_inline(text)}</h2>'
            )
            continue

        if SLIDE_TAG_RE.match(line):
            if speaker is not None:
                emit_bubbles()  # keep the turn open, keep cue ordering
            else:
                flush_paragraph(buf, blocks)
            slides += 1
            blocks.append(
                f'<div class="slide" role="note" aria-label="Slide change">'
                f'<span class="slide-pill">&#9654; slide {slides}</span></div>'
            )
            continue

        action = ACTION_RE.match(line)
        if action:
            if speaker is not None:
                emit_bubbles()  # keep the turn open, keep cue ordering
            else:
                flush_paragraph(buf, blocks)
            cue = (action.group(1) or action.group(2)).strip()
            if SLIDE_CUE_RE.match(cue):
                slides += 1
                detail = SLIDE_CUE_RE.sub("", cue).strip(" \u2013-—:")
                rendered = render_inline(detail) if detail else ""
                label = f"&#9654; slide {slides}"
                if rendered:
                    label += f" &mdash; {rendered}"
                blocks.append(
                    f'<div class="slide" role="note" aria-label="Slide cue">'
                    f'<span class="slide-pill">{label}</span></div>'
                )
            else:
                icon = "&#10074;&#10074;" if "pause" in cue.lower() else "&#9673;"
                blocks.append(
                    f'<p class="action" role="note">'
                    f'<span aria-hidden="true">{icon}</span> '
                    f"{render_inline(cue)}</p>"
                )
            continue

        spoken = SPEAKER_RE.match(line)
        if spoken:
            if speaker is not None:
                emit_bubbles()
            else:
                flush_paragraph(buf, blocks)
            speaker = spoken.group(1).upper()
            rest = spoken.group(2).strip()
            if rest:
                buf.append(rest)
            continue

        buf.append(raw_line.rstrip())

    # End of file.
    if speaker is not None:
        emit_bubbles()
    else:
        flush_paragraph(buf, blocks)

    body = "\n".join(blocks)
    section = (
        f'<section class="script-section" id="{section_id}" aria-label="{html.escape(title)}">\n'
        f"<h1>{render_inline(title)}</h1>\n"
        f'<p class="file-tag">{html.escape(path.name)}</p>\n'
        f"{body}\n"
        f"</section>"
    )
    return section_id, title, section, slides


CSS = """
:root {
  --ink: #000000;
  --muted: #333333;
  --paper: #ffffff;
  --m-bar: #00705f;
  --m-bg: #f0f6f4;
  --e-bar: #4f35c2;
  --e-bg: #f2f0fa;
  --slide: #5a3c00;
  --slide-bg: #fff8e6;
  --line: #d8d8d8;
  --focus: #000000;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Arial, sans-serif;
  font-size: 21px;
  line-height: 1.65;
}
main {
  max-width: 880px;
  margin: 0 auto;
  padding: 2rem 1.5rem 5rem;
}
.page-head { margin-bottom: 2rem; }
.page-head h1 { font-size: 2rem; margin: 0 0 0.25rem; }
.page-head p { color: var(--muted); margin: 0.25rem 0; font-size: 1rem; }
.hint { font-size: 0.95rem; color: var(--muted); }
.legend { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
.legend .badge { font-size: 0.95rem; }
nav.toc {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin: 0 0 2.5rem;
  background: #fafafa;
}
nav.toc h2 { font-size: 1rem; margin: 0 0 0.5rem; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--muted); }
nav.toc ol { margin: 0; padding-left: 1.4rem; }
nav.toc li { margin: 0.3rem 0; }
nav.toc a { color: inherit; }
section.script-section {
  border-top: 3px solid var(--ink);
  margin-top: 3rem;
  padding-top: 1rem;
  scroll-margin-top: 1rem;
}
section.script-section > h1 { font-size: 1.8rem; margin: 0; }
.file-tag { color: var(--muted); font-size: 0.9rem; margin: 0.15rem 0 1.5rem; }
h2 { font-size: 1.3rem; margin: 2rem 0 0.75rem; scroll-margin-top: 1rem; }
/* Speaker blocks: thin left bar + very subtle background tint. The bar
   carries the speaker identity; all text stays near-black for contrast. */
.speech {
  border-left: 6px solid #999;
  border-radius: 0 10px 10px 0;
  padding: 0.9rem 1.2rem 1rem;
  margin: 1.25rem 0;
  color: #000;
}
.speech p { margin: 0.7rem 0; }
.speech p:first-of-type { margin-top: 0.6rem; }
.speech p:last-child { margin-bottom: 0; }
.speech.speaker-m { border-color: var(--m-bar); background: var(--m-bg); }
.speech.speaker-e { border-color: var(--e-bar); background: var(--e-bg); }
.speech.cont { padding-top: 0.7rem; }
.speech.cont .badge { font-size: 0.75rem; }
.who { margin: 0; }
.badge {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 0.1rem 0.7rem;
}
.speaker-m .badge { color: #00463c; background: #fff; }
.speaker-e .badge { color: #2f1d8f; background: #fff; }
blockquote {
  border-left: 4px solid #666;
  margin: 1rem 0;
  padding: 0.2rem 0 0.2rem 1rem;
  color: #111;
  font-style: italic;
}
.speech blockquote { background: rgba(255,255,255,0.6); border-radius: 0 8px 8px 0; }
/* Actions / stage directions: centred, quiet, clearly unread. */
p.action {
  text-align: center;
  font-style: italic;
  color: var(--muted);
  background: #f5f5f5;
  border: 1px dashed #999;
  border-radius: 10px;
  padding: 0.55rem 1rem;
  margin: 1.25rem auto;
  max-width: 34em;
}
/* Slide transitions: unmissable but compact. */
.slide { text-align: center; margin: 1.25rem 0; }
.slide-pill {
  display: inline-block;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--slide);
  background: var(--slide-bg);
  border: 2px solid var(--slide);
  border-radius: 999px;
  padding: 0.3rem 1.1rem;
}
/* Keyboard / click navigation: every step is focusable, the current one
   gets a heavy black outline. */
.speech, p.action, div.slide { cursor: pointer; }
.current { outline: 3px solid var(--focus); outline-offset: 4px; }
.speech:focus, p.action:focus, div.slide:focus,
section.script-section > h1:focus, section.script-section > h2:focus {
  outline: 3px solid var(--focus);
  outline-offset: 4px;
}
.back-top { display: block; margin-top: 2rem; font-size: 0.95rem; }
.back-top a { color: var(--muted); }
@media print {
  body { font-size: 14pt; }
  main { max-width: none; }
  nav.toc { break-after: avoid; }
  section.script-section { break-before: page; }
  .speech { break-inside: avoid; }
}
""".strip()


NAV_JS = """(function () {
  var steps = Array.prototype.slice.call(
    document.querySelectorAll(
      "article.speech, p.action, div.slide," +
      " section.script-section > h1, section.script-section > h2"
    )
  );
  var current = -1;
  function setCurrent(i, scroll) {
    if (!steps.length) return;
    if (i < 0) i = 0;
    if (i > steps.length - 1) i = steps.length - 1;
    if (current >= 0 && steps[current]) steps[current].classList.remove("current");
    current = i;
    var el = steps[current];
    el.classList.add("current");
    el.focus({ preventScroll: true });
    if (scroll !== false) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  steps.forEach(function (el, i) {
    el.setAttribute("tabindex", "0");
    el.addEventListener("click", function () { setCurrent(i, true); });
  });
  document.addEventListener("keydown", function (e) {
    var t = e.target;
    var tag = (t && t.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || (t && t.isContentEditable)) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setCurrent(current + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCurrent(current - 1); }
  });
})();"""


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<main id="top">
<header class="page-head">
<h1>{title}</h1>
<p>Internal read-through copy &mdash; large print. {n_sections} sections, {n_slides} slide cues.</p>
<p class="hint">Click any bubble to focus it, then step through with &uarr; / &darr;.</p>
<div class="legend" aria-label="Speaker key">
<span class="badge">M &middot; Midwyfe</span>
<span class="badge">E &middot; Entropean</span>
</div>
</header>
<nav class="toc" aria-label="Table of contents">
<h2>Contents</h2>
<ol>
{toc}
</ol>
</nav>
{sections}
</main>
</body>
</html>
"""


def main():
    default_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Render numbered script markdown files to one static HTML file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dir", type=Path, default=default_dir,
                        help="directory containing the numbered section files")
    parser.add_argument("--output", type=Path, default=default_dir / "script.html",
                        help="HTML file to write")
    parser.add_argument("--title", default="Talk script — read-through copy",
                        help="title used in <title> and the page header")
    args = parser.parse_args()

    files = sorted(p for p in args.dir.glob("*.md") if NUMBERED_RE.match(p.name))
    if not files:
        raise SystemExit(f"No numbered section files found in {args.dir}")

    rendered = []
    toc_items = []
    total_slides = 0
    for i, path in enumerate(files, start=1):
        section_id, title, section_html, slides = render_section(path, i)
        total_slides += slides
        rendered.append(section_html + '\n<p class="back-top"><a href="#top">&uarr; back to top</a></p>')
        toc_items.append(
            f'<li><a href="#{section_id}">{render_inline(title)}</a></li>'
        )

    page = PAGE.format(
        title=html.escape(args.title),
        css=CSS,
        n_sections=len(files),
        n_slides=total_slides,
        toc="\n".join(toc_items),
        sections="\n".join(rendered),
    )
    page = page.replace("</body>", "<script>\n" + NAV_JS + "\n</script>\n</body>")
    args.output.write_text(page + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(files)} sections, {total_slides} slide cues)")


if __name__ == "__main__":
    main()
