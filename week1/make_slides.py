"""
Regenerate a reveal.js deck from a course notebook, matching the original
D. Pavlyuk decks (reveal.js 4.0.2, "blood" theme, images embedded).

    python make_slides.py presentation1.1.Introduction.ipynb

Plain `jupyter nbconvert --to slides` is not enough - it needs four fixes:

  1. slide metadata  - Google Colab strips `slideshow.slide_type` from cells.
                       Without it the whole notebook collapses into one slide.
                       This script refuses to run if the metadata is missing,
                       so the problem is visible instead of silent.
  2. text colour     - JupyterLab's CSS sets the content colour to near-black,
                       which is invisible on the dark "blood" theme.
                       The injected <style> block restores light text.
  3. slide size      - nbconvert defaults to a fixed 960x700 canvas, which cuts
                       off longer slides. The original decks use 100% x 100%.
  4. coloured spans  - nbconvert 7's markdown renderer turns
                       `__<span style="color:...">X</span>__` into an *empty*
                       span followed by X, so the colour is lost. Repaired here.

Requires: pip install nbconvert
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REVEAL_PREFIX = "https://unpkg.com/reveal.js@4.0.2"
REVEAL_THEME = "blood"

STYLE_BLOCK = """<style>
.anchor-link{
	display:none;
}
.reveal h1{
  font-size: 2em;
  text-shadow:none;
}
.reveal h2{
  font-size: 1.5em;
  text-transform: capitalize;
}
.reveal h3{
  font-size: 1.2em;
  text-transform: capitalize;
}
:root{
    --jp-content-font-color1: #EEEEEE;
	--jp-content-font-size1: 1em;
	--jp-code-font-size: 0.8em;
}
.jp-InputPrompt {
  flex: none;
}
</style>
"""


def check_slide_metadata(nb_path: Path) -> None:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    have = sum(
        1
        for c in nb["cells"]
        if c.get("metadata", {}).get("slideshow", {}).get("slide_type")
    )
    if have == 0:
        sys.exit(
            f"ERROR: no cell in {nb_path.name} has a slide type.\n"
            "Colab strips this metadata on save. Set it in Jupyter\n"
            "(View -> Cell Toolbar -> Slideshow) before converting,\n"
            "or restore it from the previous .slides.html."
        )
    print(f"  slide metadata: {have}/{len(nb['cells'])} cells")


def patch_html(html_path: Path) -> None:
    s = html_path.read_text(encoding="utf-8")

    # 2. light text on the dark theme
    if "--jp-content-font-color1: #EEEEEE" not in s:
        s = s.replace("</head>", STYLE_BLOCK + "</head>", 1)

    # 3. full-window slides instead of a fixed, clipping canvas
    s, n_size = re.subn(
        r"width:\s*\d+\s*,\s*\n\s*height:\s*\d+\s*,",
        "width: '100%',\n            height: '100%',",
        s,
    )

    # 4. coloured spans emptied by the markdown renderer
    s, n_span = re.subn(
        r'<span style="([^"]*)"></span>([^<]+)', r'<span style="\1">\2</span>', s
    )

    html_path.write_text(s, encoding="utf-8")
    print(f"  patched: css=yes, slide-size={n_size}, coloured-spans={n_span}")

    remote = re.findall(r'<img[^>]*src="(?!data:)([^"]*)"', s)
    if remote:
        print("  WARNING: images not embedded (need internet at presentation time):")
        for u in remote:
            print("    ", u)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: python {Path(sys.argv[0]).name} <notebook.ipynb>")

    nb_path = Path(sys.argv[1]).resolve()
    if not nb_path.exists():
        sys.exit(f"not found: {nb_path}")

    print(f"Converting {nb_path.name}")
    check_slide_metadata(nb_path)

    subprocess.run(
        [
            sys.executable, "-m", "jupyter", "nbconvert", "--to", "slides",
            str(nb_path), "--embed-images",
            f"--SlidesExporter.reveal_url_prefix={REVEAL_PREFIX}",
            f"--SlidesExporter.reveal_theme={REVEAL_THEME}",
        ],
        check=True,
    )

    html_path = nb_path.with_name(nb_path.stem + ".slides.html")
    patch_html(html_path)
    print(f"Done: {html_path.name}")


if __name__ == "__main__":
    main()
