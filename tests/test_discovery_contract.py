import httpx
import pytest
from pipelines.discovery.sources import fetch_page, AE


def test_cms_discovery_requires_canonical_page_and_official_asset():
    page = AE + "ae-attendances-and-emergency-admissions-2026-27/"
    content = '<a href="https://www.england.nhs.uk/statistics/file.csv">Monthly A&E September 2026</a><a href="https://evil.example/file.csv">Monthly A&E September 2026</a>'

    def handler(request):
        assert (
            request.url.params["slug"]
            == "ae-attendances-and-emergency-admissions-2026-27"
        )
        return httpx.Response(
            200, json=[{"link": page, "content": {"rendered": content}}]
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _, assets, _ = fetch_page(client, page, "ae")
    assert len(assets) == 1
    assert assets[0]["url"].startswith("https://www.england.nhs.uk/")


def test_cms_discovery_rejects_mismatched_canonical_page():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=[{"link": "https://evil.example"}])
        )
    ) as client:
        with pytest.raises(ValueError, match="canonical"):
            fetch_page(client, AE, "ae")
