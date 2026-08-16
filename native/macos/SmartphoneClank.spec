# Build with: python -m PyInstaller --noconfirm native/macos/SmartphoneClank.spec
import os
from pathlib import Path
from PyInstaller.building.build_main import Analysis, EXE, PYZ, COLLECT, BUNDLE

ROOT = Path(SPECPATH).parents[1]
METADATA = Path(SPECPATH) / "build" / "metadata"
METADATA.mkdir(parents=True, exist_ok=True)
REVISION = METADATA / "revision.txt"
REVISION.write_text(os.environ.get("CLANK_BUILD_REVISION", "unknown-build") + "\n", encoding="utf-8")
a = Analysis(
    [str(ROOT / "native" / "macos" / "launcher.py")], pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "dashboard" / "templates"), "dashboard/templates"),
        (str(ROOT / "config"), "config"),
        (str(ROOT / "alembic"), "alembic"),
        (str(ROOT / "alembic.ini"), "."),
        (str(REVISION), "metadata"),
    ],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto"],
)
pyz = PYZ(a.pure)
# Keep a visible console for this Stage A field-test bundle so launch failures
# remain observable; the dashboard itself remains the native-facing UI.
exe = EXE(pyz, a.scripts, name="Smartphone Clank", console=True, exclude_binaries=True)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="Smartphone Clank")
app = BUNDLE(coll, name="Smartphone Clank.app", bundle_identifier="com.clank.smartphone.fieldtest")
