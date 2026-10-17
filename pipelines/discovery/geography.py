"""Official ONS geometry and period-bound NHS provider assignments."""

import json
import hashlib
import io
import time
from datetime import date
import httpx
import pandas as pd
from sqlalchemy import text
from apps.api.database import transaction, records
from apps.api.settings import settings

ICB = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Integrated_Care_Boards_April_2026_Boundaries_EN_BSC/FeatureServer/0"
REGION = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/NHS_England_Regions_January_2024_EN_BGC/FeatureServer/0"
MAPPING = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/06/System-Mapping-Apr-26.xls"
LICENCE = "Open Government Licence v3.0; contains OS and ONS data © Crown copyright and database right 2026"


def archive(source, url, body, fmt):
    sha = hashlib.sha256(body).hexdigest()
    p = settings.raw_storage / sha[:2] / sha
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(body)
    with transaction() as c:
        c.execute(
            text(
                "INSERT INTO raw.asset(source_id,official_url,content_sha256,storage_uri,file_format,content) VALUES(:s,:u,:sha,:p,:f,:b) ON CONFLICT DO NOTHING"
            ),
            {
                "s": source,
                "u": url,
                "sha": sha,
                "p": str(p.relative_to(settings.raw_storage)),
                "f": fmt,
                "b": body,
            },
        )
    return sha


def load():
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for kind, url, valid, code, name in [
            ("icb_boundary", ICB, date(2026, 4, 1), "ICB26CD", "ICB26NM"),
            ("nhs_region_boundary", REGION, date(2024, 1, 1), "NHSER24CD", "NHSER24NM"),
        ]:
            response = client.get(
                url + "/query",
                params={
                    "where": "1=1",
                    "outFields": "*",
                    "outSR": "4326",
                    "f": "geojson",
                },
            )
            response.raise_for_status()
            data = response.json()
            if "features" not in data or not data["features"]:
                raise ValueError("ONS geometry response has no features")
            archive("boundaries", str(response.url), response.content, "geojson")
            with transaction() as c:
                for f in data["features"]:
                    props = f["properties"]
                    if code not in props or name not in props:
                        raise ValueError(
                            "Official geometry identifier contract changed"
                        )
                    c.execute(
                        text(
                            f"INSERT INTO geo.{kind}(code,name,valid_from,geom,source_url,licence) VALUES(:c,:n,:v,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326)),:u,:l) ON CONFLICT DO NOTHING"
                        ),
                        {
                            "c": props[code],
                            "n": props[name],
                            "v": valid,
                            "g": json.dumps(f["geometry"]),
                            "u": url,
                            "l": LICENCE,
                        },
                    )
                print(kind, len(data["features"]), flush=True)
        r = client.get(MAPPING)
        r.raise_for_status()
        archive("ods", MAPPING, r.content, "xls")
        frame = pd.read_excel(io.BytesIO(r.content), sheet_name="ICB Mapping", header=7)
        with transaction() as c:
            for _, row in frame.iterrows():
                code = str(row.iloc[1]).strip()
                parent = str(row.iloc[3]).strip()
                name = str(row.iloc[4]).strip()
                if code in ("nan", "") or parent in ("nan", ""):
                    continue
                c.execute(
                    text(
                        "INSERT INTO ref.organisation_relationship(provider_code,parent_code,parent_name,relationship,valid_from,official_url) VALUES(:c,:p,:n,'ICB','2026-04-01',:u) ON CONFLICT DO NOTHING"
                    ),
                    {"c": code, "p": parent, "n": name, "u": MAPPING},
                )
            c.execute(
                text(
                    "UPDATE ops.source SET last_checked=now(),last_ingested=now(),status='published' WHERE id IN ('boundaries','ods')"
                )
            )
        print("Effective provider/ICB mapping loaded", flush=True)


def enrich_ods(limit=20):
    """Legal identity is metadata, never used to invent earlier ICB membership."""
    with transaction() as c:
        orgs = records(
            c,
            "SELECT DISTINCT code FROM ref.organisation WHERE status='Published' AND code<>'TOTAL' ORDER BY code LIMIT :n",
            {"n": limit},
        )
    with httpx.Client(timeout=40, headers={"Accept": "application/json"}) as client:
        for org in orgs:
            url = (
                "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations/"
                + org["code"]
            )
            r = client.get(url)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            j = r.json().get("Organisation", {})
            archive("ods", url, r.content, "json")
            if not j:
                continue
            with transaction() as c:
                c.execute(
                    text(
                        "UPDATE ref.organisation SET ods=cast(:j as jsonb),status=:s WHERE code=:c"
                    ),
                    {
                        "j": json.dumps(j),
                        "s": j.get("Status", "Verified"),
                        "c": org["code"],
                    },
                )
            time.sleep(0.25)
    print("ODS legal metadata checked", len(orgs), flush=True)


if __name__ == "__main__":
    load()
    enrich_ods()
