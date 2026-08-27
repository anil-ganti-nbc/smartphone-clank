# Build with: python -m PyInstaller --noconfirm native/windows/SmartphoneClank.spec
import os
from pathlib import Path
from PyInstaller.building.build_main import Analysis, EXE, PYZ

ROOT = Path(SPECPATH).parents[1]
METADATA = Path(SPECPATH) / "build" / "metadata"
METADATA.mkdir(parents=True, exist_ok=True)
REVISION = METADATA / "revision.txt"
REVISION.write_text(os.environ.get("CLANK_BUILD_REVISION", "unknown-build") + "\n", encoding="utf-8")
a = Analysis(
    [str(ROOT / "native" / "windows" / "launcher.py")], pathex=[str(ROOT)],
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
# Onefile Windows build with no visible console; the dashboard itself
# remains the native-facing UI (mirrors the packaging shape used for the
# macOS field-test bundle, minus the macOS-only BUNDLE/.app step).
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name="Smartphone Clank",
    console=False,
)
