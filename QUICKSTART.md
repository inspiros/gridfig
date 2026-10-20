# Gridfig quick start

## 1. Start

Install Python 3.10+ and Typst 0.14+ (tested with Typst 0.15.1). Gridfig checks
Typst before opening the server. If it is missing, unusable, or too old, startup
stops with an installation/PATH hint instead of leaving you with a broken editor.

Open a terminal in the downloaded repository folder, then install the app
(requires [pipx](https://pipx.pypa.io/stable/installation/)):

```sh
pipx install '.[images]'
gridfig doctor
gridfig
```

`gridfig` and `gridfig serve` both start the editor. The installed command works
from any directory and bundles the editor, Typst helpers and example assets. Typst
is a separate prerequisite. The recommended installation includes Pillow for
image encoding; use `pipx install .` for a minimal installation. Run
`gridfig doctor` at any time to check Python, Typst, bundled assets and optional
Pillow. `gridfig --version` reports the app version.

To run directly from the source without installing:

```sh
python3 gridfig.py serve
```

Open the **full localhost URL printed in the terminal**. A free port and a new
session URL are chosen each time; an old URL will not work after restarting.
Leave the terminal running while you use the editor. Stop it with **Ctrl+C**.
For a fixed port, use `python3 gridfig.py serve --port 8765`.

Basic PNG/SVG layouts need no Python packages. For JPEG export or lossless
conversion of other raster formats, install optional Pillow in the Python
environment you use to start Gridfig:

```sh
python3 -m pip install Pillow
```

## 2. Make a figure

1. Click **Clear all images**, then choose the number of rows and columns. This
   clears the grid and tray while keeping the layout and labels.
2. **Add images**, click a cell, drop image files, or paste image data into a
   focused cell with Ctrl+V / Cmd+V. Drag existing images to swap them. Extra
   imports go to the image tray when the grid is full.
3. Set **Layout preset**: **Tight** removes the page margin, image gaps and header
   gaps, and uses Auto header heights; **Paper** restores balanced spacing;
   **Airy** adds more breathing room. Presets keep your images, labels, cell sizes,
   fonts, borders and rotations. Manually changing their spacing shows Custom.
4. Enable the header sides you want and edit their labels. Use `=*Ours*` for bold
   or `=$x_t$` for an equation. Choose units, image-cell sizes and font size.
5. Open **PDF preview**. It renders immediately and refreshes automatically after
   you pause editing. **Update preview** forces a refresh. A dimmed preview marked
   Updating is waiting for your latest changes. The green workspace lies outside
   the PDF page; enabled headers still occupy space with the Tight preset.
6. Click **Export PDF** for the paper figure. Click **Save project** to keep an
   editable copy containing the original images. Exporting only the PDF does not
   save an editable project.

For folder import, select **Method folders**, then choose a folder containing
`baseline/scene01.png`, `ours/scene01.png`, etc. Methods become columns and matching
sample stems become rows. Missing pairs are empty; duplicate stems within a method
are rejected. **Flat list** fills existing empty cells in natural filename order.

## The image tray

The **Image tray** sits below the workspace, outside the exported figure. Use
**Add to tray** or drop extra images there. Drag a tray card into a grid cell to
place it; an existing cell image moves back into the tray. Click a card to fill
the first empty cell. Drag grid images back to the tray, or use the small arrow
on a placed image. Drag tray cards onto one another to reorder them.

**Move grid to tray** sets all placed images aside without losing them.
**Clear all images** empties both the grid and tray. The × on a tray card removes
that unused image. None of these actions deletes original files on disk. The
prototype supports up to 100 grid cells, 200 tray images and an 80 MB encoded
project payload. Resizing the grid moves images from removed cells to the tray.

## 3. Resume or share

**You never have to write a `.gridfig.json` file.** It is the app's editable save
file. Click **Save project** and Gridfig creates it for you, including your grid,
unused tray images, labels, settings and original image data. **Open project**
loads it again. JSON is just the storage format; manual editing is optional and
only useful for advanced scripting.

**Open project** restores a saved `.gridfig.json` file, or start directly with:

```sh
python3 gridfig.py serve --project /path/to/figure.gridfig.json
```

**Download Typst project** saves a ZIP with the PDF, Typst sources, configuration,
original images, unused tray images, and any prepared encoded images. Tray images
are retained in the source ZIP but never appear in the exported PDF. A colleague can rebuild it
without the editor. Its README contains the compilation command.

You can also build a saved project or a config directly:

```sh
python3 gridfig.py build examples/comparison.json -o output/pdf/comparison.pdf
```

## Where images go and what gets cleaned up

| Item | Location | Lifetime |
| --- | --- | --- |
| Your original files | Wherever you selected them from | Gridfig reads them and does not modify or delete them. |
| Images selected in the editor | Browser tab memory | Retained for that tab session. Unsaved edits are lost on reload/close; there is no autosave. |
| Rendering copies and generated previews/PDFs | A new `gridfig-*` directory in the operating system's temporary folder, usually `/tmp` on Linux | Removed after each render/export request, including failed renders. An abrupt process termination can leave temporary files behind. |
| Save project, Export PDF, Download Typst project | Your browser's download destination, often Downloads, or the location you choose | Kept until you delete them. Gridfig does not clean up your downloads. |
| Command-line build output | The path supplied with `-o` (default `figure.pdf` in your current directory) | Kept until you delete it; temporary build inputs are cleaned up. |
| Bundled demo images | `examples/images/` in this repository | Part of the project; not removed on shutdown. |

The server stores no persistent upload directory. Saving a project is how you keep
your work. A saved `.gridfig.json` embeds both placed and tray images, so it remains usable if you
later move the original files.

See [README.md](README.md) for supported formats and compression, or the
[advanced guide](docs/advanced.md) for configuration and the native Typst API.
