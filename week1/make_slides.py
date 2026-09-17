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
  5. slides that       - with a 100% x 100% canvas reveal.js does not scale the
     do not fit          content, so long slides (bullets + a large picture) run
                         off the bottom of the screen. Two measures are injected:
                         images are capped at 58% of the window height, and a
                         shrink-to-fit script scales any slide that is still too
                         big, on every slide change and window resize. Verified
                         headless at 1920x1080.

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
/* --- fit the screen (fix 5) --- */
.reveal img{
  max-height: 58vh;
  width: auto;
  height: auto;
  object-fit: contain;
}
.reveal .jp-Cell{
  padding-top: 0;
  padding-bottom: 0;
}
.reveal .jp-MarkdownCell .jp-InputPrompt{
  display: none;
}
.reveal .fitwrap{
  transform-origin: center center;
  will-change: transform;
}
</style>
"""

FIT_SCRIPT = """<script>
// Shrink-to-fit: reveal.js does not scale a 100%%x100%% canvas, so a slide with
// a lot of text plus a picture can run off the bottom. Every leaf slide gets its
// content wrapped once in .fitwrap; if the wrapper is taller or wider than the
// window, it is scaled down just enough to fit. Runs on ready, slide change and
// resize, and again after MathJax has typeset formulas.
require(["%(prefix)s/dist/reveal.js"], function (Reveal) {
  var MARGIN_V = 0.94, MARGIN_H = 0.98;

  function leaves() {
    return Array.prototype.filter.call(
      document.querySelectorAll(".reveal .slides section"),
      function (s) { return !s.querySelector(":scope > section"); }
    );
  }
  function wrapOnce() {
    leaves().forEach(function (sec) {
      if (sec.querySelector(":scope > .fitwrap")) return;
      var w = document.createElement("div");
      w.className = "fitwrap";
      while (sec.firstChild) w.appendChild(sec.firstChild);
      sec.appendChild(w);
    });
  }
  function fit(sec) {
    if (!sec) return;
    var w = sec.querySelector(":scope > .fitwrap");
    if (!w) return;
    var box = document.querySelector(".reveal");
    var availH = box.clientHeight * MARGIN_V;
    var availW = box.clientWidth * MARGIN_H;
    // zoom (not transform) so the slide box really shrinks and reveal.js can
    // still centre it vertically. Measured and corrected iteratively, because
    // vh-based image caps change the content height when the zoom changes.
    var k = 1;
    w.style.zoom = "";
    for (var pass = 0; pass < 5; pass++) {
      var r = w.getBoundingClientRect();
      if (!r.height || !r.width) return;
      var f = Math.min(availH / r.height, availW / r.width);
      if (f >= 0.995) break;
      k = Math.max(0.3, k * f * 0.99);
      w.style.zoom = k;
    }
  }
  function relayout() { try { Reveal.layout(); } catch (e) {} }
  // two passes: the first scales the slide, reveal.js then re-centres it, and
  // the second pass corrects the rounding that centring introduces
  function fitCurrent() {
    var s = Reveal.getCurrentSlide();
    fit(s); relayout(); fit(s); relayout();
  }
  function fitAll() {
    var ls = leaves();
    ls.forEach(fit); relayout();
    ls.forEach(fit); relayout();
  }

  Reveal.on("ready", function () {
    wrapOnce();
    fitAll();
    setTimeout(fitAll, 600);   // after MathJax
    setTimeout(fitAll, 2000);
  });
  Reveal.on("slidechanged", function () {
    wrapOnce();
    fitCurrent();
    setTimeout(fitCurrent, 250);
  });
  window.addEventListener("resize", function () { setTimeout(fitAll, 120); });
});
</script>
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

    # 5. shrink-to-fit for slides that are still too tall
    n_fit = 0
    if "fitwrap" not in s.split("<body")[0] or "function fitCurrent" not in s:
        s = s.replace("</html>", (FIT_SCRIPT % {"prefix": REVEAL_PREFIX}) + "</html>", 1)
        n_fit = 1

    html_path.write_text(s, encoding="utf-8")
    print(f"  patched: css=yes, slide-size={n_size}, coloured-spans={n_span}, fit-script={n_fit}")

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
