"""Integration checks: actual Typst compilation, original pixels, and source portability."""
import base64
import copy
import contextlib
import io
import itertools
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import struct
import sys
import tempfile
from types import SimpleNamespace
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gridfig


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.config, self.assets = gridfig.read_project(gridfig.ROOT / "examples/comparison.json")

    def test_invalid_projects_fail_before_compilation(self):
        mutations = [
            lambda c: c.update(version=2),
            lambda c: c.update(images=[]),
            lambda c: c["images"][0].pop(),
            lambda c: c["images"][0].__setitem__(0, "../private.png"),
            lambda c: c["images"][0].__setitem__(0, "images/../../private.png"),
            lambda c: c["headers"].update(top=["too few"]),
            lambda c: c["layout"].update(cell_width_mm=float("nan")),
            lambda c: c["layout"].update(cell_width_mm=True),
            lambda c: c["layout"].update(fit="crop"),
            lambda c: c["layout"].update(rotations={"left": "90"}),
        ]
        for mutate in mutations:
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.subTest(config=config), self.assertRaises(gridfig.GridfigError):
                gridfig.validate(config)

    def test_symlink_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images").mkdir()
            (root / "images" / "external.png").symlink_to(gridfig.ROOT / "examples/images/coast-ours.png")
            config = {"version": 1, "images": [["images/external.png"]]}
            path = root / "figure.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(gridfig.GridfigError, "escapes"):
                gridfig.read_project(path)

    def test_editor_save_can_be_used_as_a_cli_project(self):
        project = {"format": "gridfig-editor", "config": self.config,
                   "assets": {name: base64.b64encode(data).decode() for name, data in self.assets.items()}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.gridfig.json"
            path.write_text(json.dumps(project))
            config, assets = gridfig.read_project(path)
            self.assertEqual(config, self.config)
            self.assertEqual(assets, self.assets)

    def test_saved_project_restores_unused_tray_images(self):
        config = copy.deepcopy(self.config)
        config['tray'] = ['images/extra.png']
        assets = {**self.assets, 'images/extra.png': self.assets['images/coast-ours.png']}
        payload = {'format':'gridfig-editor','config':config,'assets':{name:base64.b64encode(data).decode() for name,data in assets.items()}}
        restored, decoded = gridfig.unpack_project(payload)
        self.assertEqual(restored['tray'], ['images/extra.png'])
        self.assertEqual(decoded, assets)


class StartupTests(unittest.TestCase):
    def test_missing_typst_stops_before_binding_a_port(self):
        stderr = io.StringIO()
        with mock.patch.object(gridfig.shutil,'which',return_value=None), mock.patch.object(gridfig,'ThreadingHTTPServer') as server, contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gridfig.main(['serve'])
            self.assertEqual(caught.exception.code,1)
            server.assert_not_called()
        self.assertIn('Typst was not found on PATH',stderr.getvalue())
        self.assertIn('https://typst.app/open-source/',stderr.getvalue())

    def test_old_or_unusable_typst_is_rejected(self):
        for version in ('typst 0.13.1','unexpected output'):
            with self.subTest(version=version), mock.patch.object(gridfig.shutil,'which',return_value='/typst'), mock.patch.object(gridfig.subprocess,'run',return_value=SimpleNamespace(stdout=version,returncode=0)):
                with self.assertRaises(gridfig.GridfigError):
                    gridfig.check_typst()

    def test_doctor_reports_a_missing_typst_without_a_traceback(self):
        output = io.StringIO()
        with mock.patch.object(gridfig.shutil,'which',return_value=None), contextlib.redirect_stdout(output):
            self.assertFalse(gridfig.doctor())
        self.assertIn('MISSING OR UNUSABLE',output.getvalue())
        self.assertIn('Pillow:',output.getvalue())


@unittest.skipUnless(shutil.which("typst"), "Typst is required for integration checks")
class CompileTests(unittest.TestCase):
    def setUp(self):
        self.config, self.assets = gridfig.read_project(gridfig.ROOT / "examples/comparison.json")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def build(self, config, assets=None, name="figure.pdf"):
        gridfig.stage(self.folder, config, assets if assets is not None else self.assets)
        output = self.folder / name
        gridfig.compile_figure(self.folder, output)
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        if shutil.which("pdfinfo"):
            info = subprocess.check_output(["pdfinfo", str(output)], text=True)
            self.assertRegex(info, r"Pages:\s+1\b")
        return output

    def test_all_sixteen_header_combinations_with_empty_cell(self):
        for enabled in itertools.product((False, True), repeat=4):
            config = copy.deepcopy(self.config)
            config["images"][0][1] = None
            headers = {"top": ["Input", "Baseline", {"typst": "*Ours* $lambda$"}],
                       "left": ["Coast", "Dunes"], "bottom": ["A", "B", "C"], "right": ["I", "II"]}
            config["headers"] = {side: headers[side] for side, on in zip(gridfig.SIDES, enabled) if on}
            config["layout"]["rotations"] = {"left": 90, "right": -90}
            config["layout"]["stroke_pt"] = 0.3
            with self.subTest(enabled=enabled):
                self.build(config)

    def test_single_cell_no_headers_and_fitting_modes(self):
        for fit in ("contain", "cover", "stretch"):
            config = {"version": 1, "images": [["images/coast-ours.png"]],
                      "layout": {"cell_width_mm": 20, "cell_height_mm": 12, "fit": fit, "margin_mm": 0}}
            with self.subTest(fit=fit):
                self.build(config)

    def test_zero_margin_and_fixed_header_heights_have_exact_pdf_dimensions(self):
        if not shutil.which("pdfinfo"):
            self.skipTest("Poppler pdfinfo is not available")
        config = copy.deepcopy(self.config)
        config["layout"].update(margin_mm=0, gap_mm=0, top_height_mm=12, bottom_height_mm=6)
        pdf = self.build(config)
        info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
        match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info)
        self.assertIsNotNone(match)
        self.assertAlmostEqual(float(match[1]) * 25.4 / 72, 124, places=2)
        self.assertAlmostEqual(float(match[2]) * 25.4 / 72, 94, places=2)

    def test_lossless_export_preserves_pixels_from_both_webp_encodings(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow is not installed")
        im = Image.open(io.BytesIO(self.assets["images/coast-ours.png"]))
        config = {"version": 1, "images": [["images/source.webp"]], "export": {"compression": "lossless"}}
        for lossless in (False, True):
            with self.subTest(webp_lossless=lossless):
                webp = io.BytesIO()
                im.save(webp, "WEBP", quality=75, lossless=lossless)
                self.build(config, {"images/source.webp": webp.getvalue()})
                rendered = json.loads((self.folder / "figure.json").read_text())
                encoded = Image.open(self.folder / rendered["images"][0][0]).convert("RGB")
                decoded = Image.open(io.BytesIO(webp.getvalue())).convert("RGB")
                self.assertEqual(encoded.size, decoded.size)
                self.assertEqual(encoded.tobytes(), decoded.tobytes())
                if lossless:
                    self.assertEqual(decoded.tobytes(), im.convert("RGB").tobytes())
                self.assertEqual((self.folder / "images/source.webp").read_bytes(), webp.getvalue())

    def test_jpeg_export_uses_pdf_jpeg_filter_without_resizing_and_keeps_original(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow is not installed")
        config = {"version": 1, "images": [["images/coast-ours.png"]], "export": {"compression": "jpeg", "jpeg_quality": 70}}
        pdf = self.build(config)
        self.assertEqual((self.folder / "images/coast-ours.png").read_bytes(), self.assets["images/coast-ours.png"])
        rendered = json.loads((self.folder / "figure.json").read_text())
        self.assertTrue(rendered["images"][0][0].endswith(".jpg"))
        self.assertEqual(rendered["export"]["compression"], "preserve")
        with Image.open(self.folder / rendered["images"][0][0]) as encoded_image:
            self.assertEqual(encoded_image.size, (1024, 1024))
        if shutil.which("pdfimages"):
            listing = subprocess.check_output(["pdfimages", "-list", str(pdf)], text=True)
            self.assertRegex(listing, r"1024\s+1024.*jpeg")
        archive = zipfile.ZipFile(io.BytesIO(gridfig.bundle(self.folder)))
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            archive.extractall(dest)
            gridfig.compile_figure(dest, dest / "rebuilt.pdf")
            self.assertTrue((dest / "rebuilt.pdf").read_bytes().startswith(b"%PDF"))

    def test_jpeg_transparency_flattens_onto_white(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow is not installed")
        source = io.BytesIO()
        Image.new("RGBA", (16, 16), (255, 0, 0, 0)).save(source, "PNG")
        encoded, suffix = gridfig.encode_raster(source.getvalue(), "jpeg", 95)
        self.assertEqual(suffix, ".jpg")
        self.assertEqual(Image.open(io.BytesIO(encoded)).getpixel((0, 0)), (255, 255, 255))

    def test_resolution_and_extracted_pixels_match_originals(self):
        if not shutil.which("pdfimages"):
            self.skipTest("Poppler pdfimages is not available")
        pdf = self.build(self.config)
        listing = subprocess.check_output(["pdfimages", "-list", str(pdf)], text=True)
        images = [line.split() for line in listing.splitlines() if re.match(r"\s*1\s+\d+\s+image\b", line)]
        self.assertEqual(len(images), 6)
        self.assertTrue(all(row[3:5] == ["1024", "1024"] for row in images))
        self.assertTrue(all(int(row[12]) >= 720 for row in images))
        try:
            from PIL import Image
        except ImportError:
            return  # Dimension check above remains useful without optional Pillow.
        subprocess.run(["pdfimages", "-png", str(pdf), str(self.folder / "extract")], check=True, capture_output=True)
        originals = {Image.open(io.BytesIO(blob)).convert("RGB").tobytes() for blob in self.assets.values()}
        extracted = {Image.open(path).convert("RGB").tobytes() for path in self.folder.glob("extract-*.png")}
        self.assertEqual(extracted, originals, "Embedded image pixels must match the originals exactly")

    def test_portable_project_rebuilds_with_identical_assets(self):
        self.build(self.config)
        archive = zipfile.ZipFile(io.BytesIO(gridfig.bundle(self.folder)))
        for name, blob in self.assets.items():
            self.assertEqual(archive.read(name), blob)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            archive.extractall(dest)
            config, assets = gridfig.read_project(dest / "figure.json")
            self.assertEqual(config, self.config)
            self.assertEqual(assets, self.assets)
            gridfig.compile_figure(dest, dest / "rebuilt.pdf")
            self.assertTrue((dest / "rebuilt.pdf").read_bytes().startswith(b"%PDF"))

    def test_svg_stays_vector(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40"><rect width="80" height="40" fill="#123456"/><circle cx="40" cy="20" r="12" fill="orange"/></svg>'
        pdf = self.build({"version": 1, "images": [["images/vector.svg"]]}, {"images/vector.svg": svg})
        if shutil.which("pdfimages"):
            listing = subprocess.check_output(["pdfimages", "-list", str(pdf)], text=True)
            self.assertNotRegex(listing, r"\n\s*1\s+\d+\s+image\b")

    def test_native_typst_interface(self):
        subprocess.run(["typst", "compile", "--root", str(gridfig.ROOT), str(gridfig.ROOT / "examples/native.typ"), str(self.folder / "native.pdf")], check=True, capture_output=True)

    def test_unused_tray_images_are_saved_but_not_embedded_in_pdf(self):
        config = {'version':1,'images':[['images/coast-ours.png']],'tray':['images/dunes-ours.png']}
        pdf = self.build(config)
        rendered = json.loads((self.folder/'figure.json').read_text())
        self.assertNotIn('tray',rendered)
        source = json.loads((self.folder/'source.json').read_text())
        self.assertEqual(source['tray'],config['tray'])
        self.assertEqual((self.folder/'images/dunes-ours.png').read_bytes(),self.assets['images/dunes-ours.png'])
        if shutil.which('pdfimages'):
            listing = subprocess.check_output(['pdfimages','-list',str(pdf)],text=True)
            rows = [line for line in listing.splitlines() if re.match(r'\s*1\s+\d+\s+image\b',line)]
            self.assertEqual(len(rows),1)

    def test_typst_errors_are_actionable(self):
        config = copy.deepcopy(self.config)
        config["headers"]["top"][0] = {"typst": "$definitely_unknown_symbol$"}
        gridfig.stage(self.folder, config, self.assets)
        with self.assertRaisesRegex(gridfig.GridfigError, "unknown variable"):
            gridfig.compile_figure(self.folder, self.folder / "bad.pdf")


@unittest.skipUnless(shutil.which("typst"), "Typst is required for API checks")
class EditorAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.server = gridfig.ThreadingHTTPServer(("127.0.0.1", 0), gridfig.Handler)
        except PermissionError:
            raise unittest.SkipTest("Sandbox prevents localhost binding; run this test outside the sandbox")
        cls.server.token = secrets.token_urlsafe(24)
        cls.server.render_lock = threading.Lock()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/{cls.server.token}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def fetch(self, route, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.url + route, data=data, headers=headers or ({"Content-Type": "application/json"} if data else {}))
        return urllib.request.urlopen(request, timeout=60)

    def test_demo_preview_and_export(self):
        project = json.load(self.fetch("api/demo"))
        rendered = json.load(self.fetch("api/render", project))
        self.assertTrue(base64.b64decode(rendered["preview"]).startswith(b"\x89PNG"))
        exported = json.load(self.fetch("api/export", project))
        self.assertTrue(base64.b64decode(exported["pdf"]).startswith(b"%PDF"))
        archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["project"])))
        self.assertIn("lib.typ", archive.namelist())
        for name, data in project["assets"].items():
            self.assertEqual(archive.read(name), base64.b64decode(data))

    def test_cross_origin_request_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.fetch("api/export", {}, {"Content-Type": "application/json", "Origin": "https://example.com"})
        self.assertEqual(caught.exception.code, 403)

    def test_invalid_project_returns_readable_error(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.fetch("api/render", {"config": {"version": 1, "images": []}, "assets": {}})
        self.assertEqual(caught.exception.code, 400)
        self.assertIn("rows", json.load(caught.exception)["error"])

    def test_preview_raster_and_exported_pdf_both_follow_page_margin(self):
        project = json.load(self.fetch("api/demo"))
        project["config"]["layout"].update(gap_mm=0, top_height_mm=12, bottom_height_mm=6)
        sizes = []
        for margin in (0, 10):
            project["config"]["layout"]["margin_mm"] = margin
            rendered = json.load(self.fetch("api/render", project))
            png = base64.b64decode(rendered["preview"])
            width, height = struct.unpack(">II", png[16:24])
            sizes.append((width, height))
            self.assertAlmostEqual(width, (124 + margin * 2) / 25.4 * 144, delta=1)
            self.assertAlmostEqual(height, (94 + margin * 2) / 25.4 * 144, delta=1)
            if shutil.which("pdfinfo"):
                exported = json.load(self.fetch("api/export", project))
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "figure.pdf"
                    path.write_bytes(base64.b64decode(exported["pdf"]))
                    info = subprocess.check_output(["pdfinfo", str(path)], text=True)
                    match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info)
                    self.assertIsNotNone(match)
                    self.assertAlmostEqual(width, float(match[1]) * 2, delta=1)
                    self.assertAlmostEqual(height, float(match[2]) * 2, delta=1)
        self.assertGreater(sizes[1][0], sizes[0][0])
        self.assertGreater(sizes[1][1], sizes[0][1])

    def check_staging_cleanup(self, route, project, fail=False):
        original = tempfile.TemporaryDirectory
        paths = []
        cleaned = threading.Event()
        @contextlib.contextmanager
        def tracked(*args, **kwargs):
            try:
                with original(*args, **kwargs) as folder:
                    paths.append(Path(folder))
                    yield folder
            finally:
                cleaned.set()
        with mock.patch.object(gridfig.tempfile, "TemporaryDirectory", side_effect=tracked):
            if fail:
                with self.assertRaises(urllib.error.HTTPError):
                    self.fetch(route, project)
            else:
                json.load(self.fetch(route, project))
            self.assertTrue(cleaned.wait(5), "Staging cleanup must finish after the request")
            self.assertTrue(paths)
            self.assertTrue(all(not path.exists() for path in paths))

    def test_render_and_export_remove_temporary_copies(self):
        project = json.load(self.fetch("api/demo"))
        for route in ("api/render", "api/export"):
            with self.subTest(route=route):
                self.check_staging_cleanup(route, project)

    def test_failed_compile_also_removes_temporary_copies(self):
        project = json.load(self.fetch("api/demo"))
        project["config"]["headers"]["top"][0] = {"typst": "$definitely_unknown_symbol$"}
        self.check_staging_cleanup("api/render", project, fail=True)


@unittest.skipUnless(shutil.which("node"), "Node is optional for editor model tests")
class EditorModelTests(unittest.TestCase):
    def test_units_geometry_and_folder_mapping(self):
        result = subprocess.run(["node", "--test", str(gridfig.ROOT / "tests/test_model.js")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
