import time
import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8020", timeout=60) as c:
        for _ in range(30):
            try:
                if c.get("/health/ready").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        for screen in (
            "overview",
            "emergency",
            "capacity",
            "trusts",
            "geography",
            "forecasting",
            "analyst",
            "operations",
        ):
            r = c.get("/api/v1/workspace/" + screen)
            r.raise_for_status()
            assert r.json()["screen"] == screen
            print(screen, "OK")
        assert c.get("/api/v1/workspace/overview?period=2026-99").status_code == 422
        assert (
            c.post("/api/v1/operations/discover", json={"source": "ae"}).status_code
            == 403
        )
        assert (
            c.post(
                "/api/v1/analyst/ask",
                json={"question": "Show activity"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )
        r = c.get("/api/v1/export/emergency?region=NHS%20ENGLAND%20LONDON")
        r.raise_for_status()
        assert "release_provenance" in r.text
        print("Filtering, export and privilege boundary OK")


if __name__ == "__main__":
    main()
