import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

AE = "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/"
BEDS = "https://www.england.nhs.uk/statistics/statistical-work-areas/bed-availability-and-occupancy/"
DX = "https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/"
SOURCES = {
    "ae": {
        "name": "A&E attendances and emergency admissions",
        "page": AE,
        "cadence": "monthly",
        "family": "ae",
    },
    "beds_overnight": {
        "name": "KH03 overnight beds",
        "page": BEDS + "bed-data-overnight/",
        "cadence": "quarterly",
        "family": "beds",
    },
    "beds_day": {
        "name": "KH03 day-only beds",
        "page": BEDS + "bed-data-day-only/",
        "cadence": "quarterly",
        "family": "beds",
    },
    "diagnostics": {
        "name": "Diagnostic waiting times and activity",
        "page": DX,
        "cadence": "monthly",
        "family": "diagnostics",
    },
    "ods": {
        "name": "NHS Organisation Data Service",
        "page": "https://directory.spineservices.nhs.uk/ORD/2-0-0/",
        "cadence": "daily",
        "family": "metadata",
    },
    "boundaries": {
        "name": "ONS NHS geography boundaries",
        "page": "https://www.data.gov.uk/dataset/3735c4be-8ae8-43a3-8a7c-40fec660e6e5/integrated-care-boards-april-2026-boundaries-en-bsc",
        "cadence": "metadata",
        "family": "metadata",
    },
    "uec": {
        "name": "UEC situation reports",
        "page": "https://www.england.nhs.uk/statistics/statistical-work-areas/uec-sitrep/",
        "cadence": "seasonal",
        "family": "optional",
        "enabled": False,
    },
}


def annual_page(source, year):
    fiscal = f"{year}-{str(year + 1)[-2:]}"
    return (
        (AE + f"ae-attendances-and-emergency-admissions-{fiscal}/")
        if source == "ae"
        else DX + f"monthly-diagnostics-data-{fiscal}/"
    )


def allowed_url(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in (
        "www.england.nhs.uk",
        "www.digital.nhs.uk",
        "digital.nhs.uk",
        "directory.spineservices.nhs.uk",
        "services1.arcgis.com",
        "www.arcgis.com",
        "geoportal.statistics.gov.uk",
        "www.data.gov.uk",
    )


def links(html, page, source):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-content")
    if main is None:
        raise ValueError(
            "Official publication page is unavailable or its HTML contract changed"
        )
    found = []
    for a in main.select("a[href]"):
        title = a.get_text(" ", strip=True)
        url = urljoin(page, a["href"])
        wanted = (
            (
                source == "ae"
                and "Monthly A&E" in title
                and re.search(r"\.csv(?:$|\?)", url, re.I)
            )
            or (
                source.startswith("beds")
                and "Quarter" in title
                and re.search(r"\.xlsx?(?:$|\?)", url, re.I)
            )
            or (
                source == "diagnostics"
                and "CSV Extract" in title
                and url.lower().endswith(".zip")
            )
        )
        if wanted and allowed_url(url) and url not in [i["url"] for i in found]:
            companion = None
            if source in ("ae", "diagnostics"):
                from pipelines.adapters.nhs import month

                try:
                    period = month(title)
                except ValueError:
                    period = None
                for other in main.select("a[href]"):
                    label = other.get_text(" ", strip=True)
                    candidate = urljoin(page, other["href"])
                    if not re.search(r"\.xlsx?$", candidate, re.I):
                        continue
                    if source == "ae" and not label.startswith("Monthly A&E"):
                        continue
                    if source == "diagnostics" and not label.startswith("Provider"):
                        continue
                    try:
                        if period and month(label) == period:
                            companion = candidate
                            break
                    except ValueError:
                        pass
            found.append(
                {"url": url, "title": title, "page": page, "companion": companion}
            )
    return found, main.get_text(" ", strip=True)


def fetch_page(client, page, source, headers=None):
    # NHS England publishes the same page content through its public CMS API.
    # Prefer that structured contract to delivery-specific HTML wrappers.
    slug = urlparse(page).path.rstrip("/").rsplit("/", 1)[-1]
    response = client.get(
        "https://www.england.nhs.uk/statistics/wp-json/wp/v2/pages",
        params={"slug": slug, "_fields": "id,link,content.rendered,modified_gmt"},
        headers=headers or {},
    )
    if response.status_code == 304:
        return response, [], "No new page content"
    response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ValueError("Publication page exceeds size limit")
    if "application/json" not in response.headers.get("content-type", ""):
        raise ValueError("Official publication API did not return JSON")
    matches = [
        p for p in response.json() if p.get("link", "").rstrip("/") == page.rstrip("/")
    ]
    if len(matches) != 1:
        raise ValueError("Official publication API returned no unique canonical page")
    html = '<div id="main-content">' + matches[0]["content"]["rendered"] + "</div>"
    assets, description = links(html, page, source)
    return response, assets, description
