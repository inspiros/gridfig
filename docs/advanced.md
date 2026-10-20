# Configuration and native Typst API

The [browser editor](../README.md) creates projects for you. This guide is for
scripted builds and direct Typst use; JSON authoring is optional.

Run the commands below from the source repository root. Installed users can use
`gridfig build` in place of `python3 gridfig.py build`.

## Build from a configuration

Edit [examples/comparison.json](../examples/comparison.json), with images under
`images/` relative to that JSON file:

```sh
python3 gridfig.py build examples/comparison.json -o output/pdf/comparison.pdf
```

Optionally add `--bundle output/my-project.zip` to package the source, PDF and
original images for a colleague. You can also build a self-contained project
saved by the browser: `python3 gridfig.py build figure.gridfig.json -o figure.pdf`.
JSON paths must remain inside `images/`; they
cannot reference files outside the configuration's directory. A `null` cell is
an intentional empty cell.

```json
{
  "version": 1,
  "images": [
    ["images/sample-a.png", "images/sample-b.png"],
    ["images/sample-c.png", null]
  ],
  "headers": {
    "top": ["Baseline", {"typst": "*Ours*"}],
    "left": ["Example 1", {"typst": "$lambda = 0.7$"}]
  },
  "layout": {"cell_width_mm": 30, "gap_mm": 1.5}
}
```

Headers `top` and `bottom` each need one label per column; `left` and `right`
need one per row. Omit a side or set it to `null` to disable it.

Raster encoding is an optional top-level setting:

```json
"export": {"compression": "jpeg", "jpeg_quality": 85}
```

`compression` accepts `lossless` (default), `preserve` (Original encoding in the
editor), or `jpeg`. JPEG quality is a whole number from 1 to 100, default 90.
See the [compression notes](#raster-compression) for quality
and transparency behavior. SVG bypasses raster re-encoding. A `tray` array can
retain unused `images/...` paths; these never appear in the PDF.

Python applies encoding before calling Typst. Source ZIPs include original files
and any prepared `images/_encoded/` files. Their `figure.json` references prepared
files so they rebuild directly with Typst; `source.json`, when present, retains
the original mapping and settings. Compiling an unprepared configuration with
Typst alone ignores the `export` options.

The following defaults apply when configuration values are omitted; the editor's
example and presets may choose different values.

| Layout setting | Default | Meaning |
| --- | --- | --- |
| `cell_width_mm` | 28 | Physical image-cell width |
| `cell_height_mm` | same as width | Physical image-cell height |
| `gap_mm` | 1.5 | Gaps between image cells |
| `header_gap_mm` | 2 | Gaps between headers and image cells |
| `side_width_mm` | 18 | Width of each enabled left/right header column |
| `top_height_mm`, `bottom_height_mm` | null / Auto | Top/bottom header-row heights; numerical values are in mm |
| `font` | Libertinus Serif | Header font family, installed or bundled with Typst |
| `font_size_pt` | 9 | Header text size |
| `fit` | contain | `contain` keeps everything; `cover` crops; `stretch` distorts |
| `stroke_pt` | 0 | Image-cell border thickness; zero disables it |
| `margin_mm` | 2 | PDF page margin |
| `rotations` | `{}` | E.g. `{"left": 90, "top": -45}`, in degrees |

Supported images: PNG, JPEG, SVG, WebP, GIF (static first frame). For line art,
prefer SVG; for raster results, use original PNG/JPEG files. The prototype allows
up to 100 cells, 30 MB per uploaded image and 80 MB per editor request including
base64 overhead. Very large grids can therefore be better suited to direct Typst.

### Typst without Python

```sh
typst compile --root . figure.typ output/pdf/comparison.pdf
typst compile --root . --input config=examples/comparison.json figure.typ output/pdf/comparison.pdf
typst watch --root . figure.typ output/pdf/comparison.pdf
```

`figure.typ` defaults to the bundled comparison. Configuration paths passed to
`--input` are relative to the project root and use forward slashes. The pure Typst
route does not apply the Python adapter's size/path limits. In an exported ZIP,
the config is named `figure.json`; compile as described in the ZIP's README.

## Native Typst API

```typst
#import "lib.typ": gridfig, figure-page
#show: figure-page.with(margin: 0mm)
#let pic(path) = image(path, width: 100%, height: 100%, fit: "contain")
#gridfig(
  ((pic("images/a.png"), pic("images/b.png")),),
  top: ([Baseline], [*Ours* $lambda = 0.7$]),
  left: ([Scene 1],),
  cell-width: 30mm,
  side-width: 18mm,
  gap: 1mm,
  font-size: 9pt,
  rotations: (left: 90deg),
)
```

`gridfig` accepts a rectangular array of arbitrary Typst content. The helper above
sizes images to their containing cells; pass `none` for an empty cell. Optional
arguments are `top`, `left`, `bottom`, `right`, `cell-width`, `cell-height` (defaults
to width), `gap`, `header-gap`, `side-width`, `font`, `font-size`, `rotations`, and
`stroke` (a native Typst stroke). `top-height` and `bottom-height` accept lengths
or `auto`. Headers are ordinary content, so custom fonts,
colors, alignment, and equations work inside them. More involved rules can wrap
or compose `gridfig` with ordinary Typst content.

See [examples/native.typ](../examples/native.typ) for a runnable version. Copy
`lib.typ` into another project to reuse it. A Typst web-app project can contain
these same files, config and images; it does not need the local editor or Python.

## PDF and other native content

The editor and Python adapter accept PNG, JPEG, SVG, WebP and GIF. They do not
import PDF, even when the installed Typst supports it. The native `gridfig`
function accepts arbitrary Typst content, so it can use a PDF directly:

```typst
#let panel = image("images/panel.pdf", page: 1, width: 100%, height: 100%, fit: "contain")
#gridfig(((panel,),), cell-width: 40mm)
```

Use a Typst release with PDF image support (verified with 0.15.1). Typst chooses
the PDF representation; Gridfig's raster encoding options do not run in native
Typst. A vector PDF remains vector content where supported. Password-protected
PDFs and some output PDF standards are unsupported; see the
[Typst image reference](https://typst.app/docs/reference/visualize/image/) for
current restrictions.

## Raster compression

- **Lossless** keeps PNG inputs and converts other supported rasters to PNG,
  without resizing. It preserves decoded pixels; it cannot restore detail already
  lost in JPEG or lossy WebP. CMYK images require Original encoding.
- **Original encoding** passes files unchanged to Typst; JPEG normally retains its
  existing encoding. No Pillow needed.
- **JPEG** re-encodes at quality 1–100 and flattens transparency onto white.
  It is lossy even at quality 100.

Re-encoding needs Pillow, included with the `images` installation extra. SVG
remains vector where supported by Typst. Lossless WebP input is supported, but
PDF has no native standard WebP image filter; smaller WebP source files do not
necessarily produce smaller PDFs. Lossless conversion can increase file size.
