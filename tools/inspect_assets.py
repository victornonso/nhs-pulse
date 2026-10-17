import json
import httpx
import zipfile
import pandas as pd
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
m = json.loads(Path(".local/source-inspection.json").read_text())
selected = {
    "ae": next(x for x in m["ae"]["links"] if "September 2026 (CSV" in x["title"]),
    "beds": m["beds"]["links"][3],
    "diagnostics": m["diagnostics"]["links"][4],
    "mapping": m["ae"]["links"][0],
}
with httpx.Client(timeout=120, follow_redirects=True) as c:
    for key, asset in selected.items():
        path = Path(".local/raw") / asset["url"].split("/")[-1]
        if not path.exists():
            r = c.get(asset["url"])
            r.raise_for_status()
            path.write_bytes(r.content)
        print(key, asset["url"], "bytes", path.stat().st_size, flush=True)
        if path.suffix == ".csv":
            print(
                path.read_text(encoding="utf-8-sig", errors="replace")[:6000],
                flush=True,
            )
        elif path.suffix == ".zip":
            with zipfile.ZipFile(path) as z:
                print(z.namelist(), flush=True)
                print(
                    z.read(z.namelist()[0]).decode("utf-8-sig", errors="replace")[
                        :5000
                    ],
                    flush=True,
                )
        else:
            xl = pd.ExcelFile(path)
            print(xl.sheet_names, flush=True)
            for sheet in xl.sheet_names[:3]:
                print(
                    sheet,
                    pd.read_excel(path, sheet_name=sheet, header=None)
                    .head(13)
                    .to_string(index=False, header=False),
                    flush=True,
                )
Path(".local/selected-assets.json").write_text(json.dumps(selected, indent=2))
