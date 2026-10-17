"""Install the official PostGIS bundle into this project's isolated PG18 runtime."""

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root.parent / "gridsignal-gb/.local/pgsql"
target = root / ".local/pgsql"
if not target.exists():
    shutil.copytree(source, target)
archive = root / ".local/postgis.zip"
url = "https://download.osgeo.org/postgis/windows/pg18/postgis-bundle-pg18-3.6.2x64.zip"
if not archive.exists():
    with urllib.request.urlopen(url, timeout=90) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
print(
    "PostGIS bundle SHA256",
    hashlib.sha256(archive.read_bytes()).hexdigest(),
    flush=True,
)
with zipfile.ZipFile(archive) as z:
    print(z.namelist()[:12], flush=True)
    for item in z.infolist():
        parts = Path(item.filename).parts
        while parts and parts[0] not in ("bin", "lib", "share"):
            parts = parts[1:]
        if not parts or item.is_dir():
            continue
        dest = target.joinpath(*parts).resolve()
        if not dest.is_relative_to(target.resolve()):
            raise ValueError("Unsafe archive member")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(item))
print("Isolated PostgreSQL/PostGIS files installed.", flush=True)
