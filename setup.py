"""Bundle the canonical source assets into wheels without maintaining duplicate files."""
from pathlib import Path
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithAssets(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        target = Path(self.build_lib) / "gridfig_assets"
        for name in ("web", "examples", "docs"):
            shutil.copytree(root / name, target / name, dirs_exist_ok=True)
        for name in ("lib.typ", "figure.typ", "QUICKSTART.md", "README.md"):
            shutil.copyfile(root / name, target / name)


setup(cmdclass={"build_py": BuildWithAssets})
