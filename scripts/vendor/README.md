# Bundled QR generator

qrcode 8.2, from https://pypi.org/project/qrcode/8.2/ (BSD license; original MIT attribution included in `qrcode/LICENSE`).

These upstream files are unchanged. Only the encoder and SVG import dependencies are included; CLI, tests, release tooling, Pillow rendering and other optional image styles are omitted. `image/pure.py` and `compat/png.py` are retained because `main.py` imports them, but SVG generation does not require PyPNG, Pillow or lxml.

The pairing page explicitly selects SVG output. No runtime package installation or network QR service is used. When updating, replace this subset from a trusted release and retain its license.
