"""Check native icon resources in the built distribution."""

import sys
import plistlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.platform == "darwin":
    contents = root / "dist/NICTAnalogClock.app/Contents"
    with (contents / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    name = info["CFBundleIconFile"]
    path = contents / "Resources" / name
    if not path.suffix:
        path = path.with_suffix(".icns")
    assert path.read_bytes() == (root / "assets/app-icon.icns").read_bytes()
elif sys.platform == "win32":
    import pefile

    with pefile.PE(str(root / "dist/NICTAnalogClock.exe")) as pe:
        assert any(
            entry.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries
        )
else:
    raise RuntimeError("Native build required")
print("Native application icon resource verified")
