from io import BytesIO

from PIL import Image

from app.core.vision import guess_category, parse_label_suggestions


def _jpeg(color=(70, 100, 150)) -> bytes:
    im = Image.new("RGB", (400, 500), (235, 232, 225))
    im.paste(color, (100, 100, 300, 400))
    buf = BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_scan_autosaves_with_trace(client):
    res = client.post("/api/closet/scan", files={"file": ("rain_jacket.jpg", _jpeg(), "image/jpeg")})
    assert res.status_code == 200
    body = res.json()
    item = body["item"]
    assert item["source"] == "scan"
    assert item["category"] == "outerwear"
    assert item["waterproof"] is True  # "rain" in the filename, mock classifier
    kinds = [s["kind"] for s in body["trace"]]
    assert kinds == ["validation", "fallback", "decision", "final"]
    assert body["trace"][2]["source"] == "mock"
    assert any(i["id"] == item["id"] for i in client.get("/api/closet").json())


def test_scan_rejects_non_images(client):
    res = client.post("/api/closet/scan", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def test_scan_rejects_mislabeled_bytes(client):
    res = client.post("/api/closet/scan", files={"file": ("x.png", _jpeg(), "image/png")})
    assert res.status_code == 400


def test_label_parsing_and_category_guess():
    parsed = parse_label_suggestions("LEVI'S  Size: M  100% Cotton  Made in Mexico")
    assert parsed == {"size": "M", "material": "cotton", "brand": "Levi's"}
    assert guess_category("dress shoes") == "shoes"
    assert guess_category("shirt dress") == "dresses"
    assert guess_category("denim jacket") == "outerwear"


def test_vision_rest_parsing(monkeypatch):
    import asyncio

    import httpx
    import respx

    from app.config import get_settings
    from app.core import vision

    monkeypatch.setattr(get_settings(), "google_vision_api_key", "test-key")
    payload = {"responses": [{
        "webDetection": {"bestGuessLabels": [{"label": "denim jacket"}], "webEntities": [{"description": "Levi's", "score": 0.9}]},
        "labelAnnotations": [{"description": "Outerwear"}, {"description": "Denim"}],
        "textAnnotations": [{"description": "LEVI STRAUSS & CO. Levi's Size M 100% Cotton"}],
        "imagePropertiesAnnotation": {"dominantColors": {"colors": [
            {"color": {"red": 60, "green": 105, "blue": 175}, "pixelFraction": 0.6},
            {"color": {"red": 240, "green": 240, "blue": 236}, "pixelFraction": 0.3},
        ]}},
    }]}
    with respx.mock() as router:
        route = router.post(vision.VISION_URL).mock(return_value=httpx.Response(200, json=payload))
        v = asyncio.run(vision.GoogleVisionService().annotate(b"img"))
        assert route.calls[0].request.url.params["key"] == "test-key"
    assert v.best_guess == "denim jacket"
    assert v.ocr == {"size": "M", "material": "cotton", "brand": "Levi's"}
    assert v.dominant_colors[:2] == ["blue", "white"]


def test_vision_http_error_is_a_clean_fallback(monkeypatch):
    import asyncio

    import httpx
    import pytest
    import respx

    from app.config import get_settings
    from app.core import vision

    monkeypatch.setattr(get_settings(), "google_vision_api_key", "test-key")
    with respx.mock() as router:
        router.post(vision.VISION_URL).mock(return_value=httpx.Response(403, json={"error": {"message": "API not enabled"}}))
        with pytest.raises(vision.ProviderUnavailableError, match="403 API not enabled"):
            asyncio.run(vision.GoogleVisionService().annotate(b"img"))
