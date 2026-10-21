#!/usr/bin/env python3
"""Dependency-free Gridfig CLI and localhost editor. Requires Typst 0.14+."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import importlib.resources
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import zipfile

__version__ = "0.1.0"
ROOT = Path(__file__).resolve().parent
if not (ROOT / "lib.typ").is_file():
    ROOT = Path(str(importlib.resources.files("gridfig_assets")))
MIN_TYPST = (0, 14, 0)
SIDES = ("top", "left", "bottom", "right")
EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
MAX_BODY = 80 * 1024 * 1024
NUMBERS = {
    "cell_width_mm": (1, 250), "cell_height_mm": (1, 250),
    "gap_mm": (0, 30), "header_gap_mm": (0, 30),
    "side_width_mm": (1, 100), "font_size_pt": (1, 72),
    "stroke_pt": (0, 5), "margin_mm": (0, 30),
    "top_height_mm": (1, 100), "bottom_height_mm": (1, 100),
}


class GridfigError(ValueError):
    pass


def number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise GridfigError(f"{name} must be a number between {low} and {high}.")


def asset_path(value):
    if not isinstance(value, str) or "\\" in value:
        raise GridfigError("Image paths must use forward slashes.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "images" or path.suffix.lower() not in EXTENSIONS:
        raise GridfigError("Images must be PNG, JPEG, SVG, WebP or GIF files inside images/ (no ../ paths).")
    return path


def validate(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        raise GridfigError("The project must have version: 1.")
    rows = config.get("images")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20 or not isinstance(rows[0], list) or not 1 <= len(rows[0]) <= 20:
        raise GridfigError("Choose between 1 and 20 rows and columns.")
    cols = len(rows[0])
    if len(rows) * cols > 100:
        raise GridfigError("The prototype supports at most 100 image cells.")
    for row in rows:
        if not isinstance(row, list) or len(row) != cols:
            raise GridfigError("Every image row must have the same number of cells.")
        for path in row:
            if path is not None:
                asset_path(path)
    tray = config.get("tray", [])
    if not isinstance(tray, list) or len(tray) > 200:
        raise GridfigError("The image tray supports at most 200 unused images.")
    for path in tray:
        asset_path(path)
    if len(tray) != len(set(tray)):
        raise GridfigError("The image tray must not contain duplicate image paths.")
    headers = config.get("headers", {})
    if not isinstance(headers, dict) or set(headers) - set(SIDES):
        raise GridfigError("Headers can be top, left, bottom, or right.")
    for side, labels in headers.items():
        if labels is None:
            continue
        count = cols if side in ("top", "bottom") else len(rows)
        if not isinstance(labels, list) or len(labels) != count:
            raise GridfigError(f"The {side} header needs {count} labels.")
        for label in labels:
            if not isinstance(label, str) and not (isinstance(label, dict) and set(label) == {"typst"} and isinstance(label["typst"], str)):
                raise GridfigError("Labels must be strings or objects like {\"typst\": \"$x_t$\"}.")
            if len(label if isinstance(label, str) else label["typst"]) > 2000:
                raise GridfigError("Header labels must be shorter than 2000 characters.")
    layout = config.get("layout", {})
    if not isinstance(layout, dict) or set(layout) - set(NUMBERS) - {"fit", "font", "rotations"}:
        raise GridfigError("Unknown layout option. See README.md for supported settings.")
    for name, bounds in NUMBERS.items():
        if name in layout:
            if name in ("top_height_mm", "bottom_height_mm") and layout[name] is None:
                continue
            number(layout[name], *bounds, name)
    if layout.get("fit", "contain") not in ("contain", "cover", "stretch"):
        raise GridfigError("fit must be contain, cover, or stretch.")
    if not isinstance(layout.get("font", "Libertinus Serif"), str):
        raise GridfigError("font must be a font family name.")
    rotations = layout.get("rotations", {})
    if not isinstance(rotations, dict) or set(rotations) - set(SIDES):
        raise GridfigError("Rotations can be set for top, left, bottom, or right.")
    for side, value in rotations.items():
        number(value, -360, 360, side + " rotation")
    encoding = config.get("export", {})
    if not isinstance(encoding, dict) or set(encoding) - {"compression", "jpeg_quality"}:
        raise GridfigError("Export options are compression and jpeg_quality.")
    if encoding.get("compression", "lossless") not in ("preserve", "lossless", "jpeg"):
        raise GridfigError("Compression must be preserve, lossless, or jpeg. PDF has no native WebP image filter.")
    quality = encoding.get("jpeg_quality", 90)
    number(quality, 1, 100, "JPEG quality")
    if type(quality) is not int:
        raise GridfigError("JPEG quality must be a whole number.")
    return config


def image_paths(config, *, include_tray=False):
    placed = {path for row in config["images"] for path in row if path is not None}
    return placed | set(config.get("tray", [])) if include_tray else placed


def check_typst():
    executable = shutil.which("typst")
    hint = "Install Typst from https://typst.app/open-source/ and make sure 'typst --version' works in this terminal."
    if not executable:
        raise GridfigError("Typst was not found on PATH. " + hint)
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GridfigError("Typst could not start. " + hint) from error
    match = re.search(r"\btypst\s+(\d+)\.(\d+)\.(\d+)", result.stdout)
    if result.returncode or not match:
        raise GridfigError("Could not read the Typst version. " + hint)
    version = tuple(map(int, match.groups()))
    if version < MIN_TYPST:
        raise GridfigError(f"Typst {'.'.join(map(str, version))} is too old; Gridfig needs 0.14.0 or newer. " + hint)
    return ".".join(map(str, version))


def doctor():
    print(f"Python {sys.version.split()[0]}: OK")
    ready = True
    try:
        print(f"Typst {check_typst()}: OK")
    except GridfigError as error:
        print(f"Typst: MISSING OR UNUSABLE\n  {error}")
        ready = False
    if importlib.util.find_spec("PIL"):
        print("Pillow: available (optional raster re-encoding enabled)")
    else:
        print("Pillow: optional, not installed. For raster re-encoding: python3 -m pip install Pillow")
    resources_ok = all((ROOT / path).is_file() for path in ("lib.typ", "figure.typ", "web/index.html", "web/app.js", "examples/comparison.json"))
    print("Bundled assets: " + ("OK" if resources_ok else "MISSING; reinstall Gridfig"))
    return ready and resources_ok


def compile_figure(folder, output, *, preview=False):
    if not shutil.which("typst"):
        raise GridfigError("Typst was not found. Install Typst and put it on PATH, then restart Gridfig.")
    cmd = ["typst", "compile", "--root", str(folder), "--input", "config=figure.json"]
    if preview:
        cmd += ["--ppi", "144"]
    cmd += [str(folder / "figure.typ"), str(output)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired as error:
        raise GridfigError("Rendering took more than 45 seconds. Try fewer images or simpler labels.") from error
    if result.returncode:
        raise GridfigError(result.stderr.strip() or "Typst could not compile the figure.")
    return result.stderr.strip()


def encode_raster(data, mode, quality=90):
    """No resizing. Lossless preserves decoded pixels; JPEG explicitly trades detail for size."""
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise GridfigError("Raster re-encoding needs Pillow: python3 -m pip install Pillow. Choose 'Original encoding' to avoid it.") from error
    try:
        with Image.open(io.BytesIO(data)) as source:
            im = ImageOps.exif_transpose(source)
            profile = im.info.get("icc_profile")
            output = io.BytesIO()
            if mode == "lossless":
                # PNG supports palette, alpha, grayscale and 16-bit grayscale too.
                if im.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
                    if im.mode == "CMYK":
                        raise GridfigError("Lossless PNG cannot preserve CMYK pixels. Choose Original encoding for this image.")
                    im = im.convert("RGBA")
                im.save(output, format="PNG", compress_level=9, icc_profile=profile)
                return output.getvalue(), ".png"
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                im = flattened
            elif im.mode not in ("RGB", "L", "CMYK"):
                im = im.convert("RGB")
            im.save(output, format="JPEG", quality=quality, subsampling=0, optimize=True, icc_profile=profile)
            return output.getvalue(), ".jpg"
    except GridfigError:
        raise
    except (OSError, ValueError) as error:
        raise GridfigError(f"Cannot re-encode an image: {error}") from error


def stage(folder, config, assets):
    validate(config)
    for name in ("lib.typ", "figure.typ"):
        shutil.copyfile(ROOT / name, folder / name)
    rendered = json.loads(json.dumps(config))
    mode = config.get("export", {}).get("compression", "lossless")
    replacements = {}
    placed = image_paths(config)
    for name in image_paths(config, include_tray=True):
        path = asset_path(name)
        if name not in assets:
            raise GridfigError(f"Missing image: {name}")
        target = folder / str(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(assets[name])
        if name not in placed:
            continue
        # Vectors stay vectors. Existing PNG data already has lossless encoding.
        if mode == "preserve" or path.suffix.lower() == ".svg" or (mode == "lossless" and path.suffix.lower() == ".png"):
            continue
        data, suffix = encode_raster(assets[name], mode, config.get("export", {}).get("jpeg_quality", 90))
        key = hashlib.sha256(name.encode() + data).hexdigest()[:24]
        converted = f"images/_encoded/{key}{suffix}"
        dest = folder / converted
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        replacements[name] = converted
    if replacements or config.get("tray"):
        (folder / "source.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rendered["images"] = [[replacements.get(name, name) for name in row] for row in config["images"]]
    # A source ZIP rebuilds directly with Typst; encoding is already applied.
    rendered.pop("export", None)
    rendered.pop("tray", None)
    if replacements:
        rendered["export"] = {"compression": "preserve"}
    (folder / "figure.json").write_text(json.dumps(rendered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_project(path):
    project = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(project, dict) and project.get("format") == "gridfig-editor":
        return unpack_project(project)
    config = validate(project)
    assets = {}
    for name in image_paths(config, include_tray=True):
        target = (path.parent / name).resolve()
        if not target.is_relative_to(path.parent.resolve()):
            raise GridfigError(f"Image escapes the project directory: {name}")
        assets[name] = target.read_bytes()
    return config, assets


def unpack_project(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), dict):
        raise GridfigError("The project must contain a configuration and image assets.")
    config = validate(payload.get("config"))
    assets = {}
    for name in image_paths(config, include_tray=True):
        value = payload["assets"].get(name)
        if not isinstance(value, str):
            raise GridfigError(f"Missing image data: {name}")
        try:
            assets[name] = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as error:
            raise GridfigError(f"Invalid image encoding: {name}") from error
    return config, assets


def bundle(folder):
    readme = """# Gridfig project

Install Typst 0.14 or newer, then run from this directory:

    typst compile --root . --input config=figure.json figure.typ figure.pdf

Or upload figure.typ, lib.typ, figure.json and images/ together to the Typst web app.
Edit figure.json to change labels, image paths, spacing and dimensions.
Plain strings are text; {\"typst\": \"$x_t$\"} enables Typst markup.
Rich labels execute Typst markup: open projects from people you trust.
Images are copied without resizing. Preview PNGs are only previews.
If re-encoding was requested, figure.json uses prepared images/_encoded/ assets.
Original image files are also retained; source.json records original settings.
"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder))
        archive.writestr("README.md", readme)
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, body, mime="application/json", status=200):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in allowed or (origin and origin != f"http://{host}"):
            self.reply({"error": "This editor accepts same-origin localhost requests only."}, status=403)
            return None
        prefix = "/" + self.server.token + "/"
        if not self.path.startswith(prefix):
            self.reply({"error": "Open the editor URL printed in your terminal."}, status=404)
            return None
        return self.path[len(prefix):]

    def do_GET(self):
        route = self.route()
        if route is None:
            return
        if route in ("", "app.js", "model.js", "style.css", "logo.svg"):
            name = route or "index.html"
            mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "model.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8", "logo.svg": "image/svg+xml"}[name]
            self.reply((ROOT / "web" / name).read_bytes(), mime)
        elif route == "api/demo":
            config, assets = read_project(getattr(self.server, "project_path", ROOT / "examples" / "comparison.json"))
            self.reply({"config": config, "assets": {name: base64.b64encode(data).decode() for name, data in assets.items()}})
        else:
            self.reply({"error": "Not found"}, status=404)

    def do_POST(self):
        route = self.route()
        if route is None:
            return
        if route not in ("api/render", "api/export"):
            self.reply({"error": "Not found"}, status=404)
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.reply({"error": "Use application/json."}, status=415)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise GridfigError("The request is too large (80 MB limit, including base64 encoding).")
            payload = json.loads(self.rfile.read(size))
            config, assets = unpack_project(payload)
            # Bound simultaneous Typst processes when multiple browser requests arrive.
            with self.server.render_lock, tempfile.TemporaryDirectory(prefix="gridfig-") as tmp:
                folder = Path(tmp)
                stage(folder, config, assets)
                if route == "api/render":
                    warning = compile_figure(folder, folder / "preview.png", preview=True)
                    self.reply({"preview": base64.b64encode((folder / "preview.png").read_bytes()).decode(), "warning": warning})
                else:
                    compile_figure(folder, folder / "figure.pdf")
                    self.reply({"pdf": base64.b64encode((folder / "figure.pdf").read_bytes()).decode(), "project": base64.b64encode(bundle(folder)).decode()})
        except (GridfigError, ValueError, KeyError, TypeError, OSError, binascii.Error) as error:
            self.reply({"error": str(error)}, status=400)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"gridfig {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build a JSON project as a PDF")
    build.add_argument("config", type=Path)
    build.add_argument("-o", "--output", type=Path, default=Path("figure.pdf"))
    build.add_argument("--bundle", type=Path, help="Also save a portable Typst project ZIP")
    serve = sub.add_parser("serve", help="Start the local browser editor")
    serve.add_argument("--port", type=int, default=0, help="Default: choose an available localhost port")
    serve.add_argument("--project", type=Path, help="Start the editor with a config or saved .gridfig.json project")
    sub.add_parser("doctor", help="Check Python, Typst, bundled assets and optional Pillow")
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv or ["serve"])
    try:
        if args.command == "doctor":
            if not doctor():
                parser.exit(1)
            return
        typst_version = check_typst()  # Fail before binding a port or reading a large project.
        if args.command == "build":
            config, assets = read_project(args.config)
            with tempfile.TemporaryDirectory(prefix="gridfig-") as tmp:
                folder = Path(tmp)
                stage(folder, config, assets)
                warning = compile_figure(folder, folder / "figure.pdf")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(folder / "figure.pdf", args.output)
                if args.bundle:
                    args.bundle.parent.mkdir(parents=True, exist_ok=True)
                    args.bundle.write_bytes(bundle(folder))
            if warning:
                print(warning, file=sys.stderr)
            print(f"Saved {args.output.resolve()}")
        else:
            server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
            server.token = secrets.token_urlsafe(24)
            server.render_lock = threading.Lock()
            if args.project:
                read_project(args.project)  # Fail before opening an unusable editor.
                server.project_path = args.project.resolve()
            print(f"Gridfig editor: http://127.0.0.1:{server.server_address[1]}/{server.token}/", flush=True)
            print(f"Typst {typst_version} is ready.", flush=True)
            print("Runs locally. Ctrl+C stops the server. Download a project ZIP to save your work.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (GridfigError, OSError, ValueError) as error:
        parser.exit(1, f"gridfig: {error}\n")


if __name__ == "__main__":
    main()
