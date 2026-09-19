# Site build

Renders this repository's Markdown into a static site in _site/ for Cloudflare Pages.

    python3 .site-build/build.py --src . --out _site --surface publications --base-url https://parallax.urekalabs.ai

Requires Python 3.12 and pandoc 3.x. The build skips hidden paths (this folder included) and refuses to
clear an output folder that does not hold a previous build. Output is deterministic: the same input gives
byte-identical files. Tests: python3 -m pytest -q .site-build/tests.
