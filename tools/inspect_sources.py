import httpx
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

pages = {
    "ae": "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2026-27/",
    "beds": "https://www.england.nhs.uk/statistics/statistical-work-areas/bed-availability-and-occupancy/bed-data-overnight/",
    "diagnostics": "https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/monthly-diagnostics-data-2026-27/",
}
manifest = {}
with httpx.Client(timeout=90, follow_redirects=True) as c:
    for key, url in pages.items():
        r = c.get(url)
        r.raise_for_status()
        Path(f".local/{key}-page.html").write_text(r.text, encoding="utf-8")
        soup = BeautifulSoup(r.text, "html.parser")
        links = [
            {
                "title": a.get_text(" ", strip=True),
                "url": urljoin(url, a.get("href", "")),
            }
            for a in soup.select("#main-content a[href]")
            if re.search(r"\.(csv|zip|xlsx?|pdf)(?:$|[?#])", a.get("href", ""), re.I)
        ]
        manifest[key] = {
            "page": url,
            "links": links,
            "text": soup.select_one("#main-content").get_text(" ", strip=True),
        }
        print(key, json.dumps(links[:12]))
Path(".local/source-inspection.json").write_text(
    json.dumps(manifest, indent=2), encoding="utf-8"
)
