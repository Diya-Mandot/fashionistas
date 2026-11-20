import json
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import respx
from PIL import Image

from app.config import get_settings
from app.integrations import palette_client
from app.integrations.palette_client import PaletteAdvice
from app.tools import weather as weather_mod
from test_agent import _mock_open_meteo


@pytest.mark.parametrize("confidence", ["moderate", "low"])
def test_photo_plan_uses_research_and_keeps_photo_out_of_trace(client, monkeypatch, confidence):
    monkeypatch.setattr(get_settings(), "decisions_mode", "live")
    url = "https://rails-test.leo.llamapress.ai/fashionistas/palette-evidence.json"
    monkeypatch.setattr(get_settings(), "llamapress_palette_url", url)
    evidence_path = Path(palette_client.__file__).resolve().parents[1] / "data" / "palette-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["sources"][0]["finding"] += " Served by the test endpoint."

    def parse(**kwargs):
        assert kwargs["output_format"] is PaletteAdvice
        image, context = kwargs["messages"][0]["content"]
        assert image["source"]["type"] == "base64" and image["source"]["data"]
        data = json.loads(context["text"])
        assert data["preferred_colors"] == ["navy"]
        assert data["closet_colors"]
        assert "10.1177/20416695211053361" in data["research"][0]["url"]
        assert ("Served by the test endpoint." in data["research"][0]["finding"]) == (confidence == "moderate")
        return SimpleNamespace(parsed_output=PaletteAdvice(
            confidence=confidence, summary="The lighting may affect the visible colors.", colors=["Black"],
        ))

    fake = SimpleNamespace(with_options=lambda **_: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    monkeypatch.setattr(palette_client, "get_client", lambda: fake)

    photo = BytesIO()
    Image.new("RGB", (16, 16), "white").save(photo, "PNG")
    weather_mod._forecast_cache.clear()
    weather_mod._geo_cache.clear()
    with respx.mock(assert_all_called=False) as router:
        _mock_open_meteo(router, start=date.today().isoformat(), precip=0)
        remote = router.get(url)
        if confidence == "moderate":
            remote.respond(200, json=evidence)
        else:
            remote.respond(404)
        response = client.post("/api/stylist/plan/photo", data={"plan": json.dumps({
            "message": "Lunch in Seattle", "wait": True, "preferred_colors": ["Navy"],
        })}, files={"photo": ("my-portrait.png", photo.getvalue(), "image/png")})
        assert remote.call_count == 1
        assert not remote.calls.last.request.content

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    trace = response.json()["trace"]
    step = next(step for step in trace if step["tool"] == "personal_palette")
    assert step["source"] == "live"
    assert step["args"]["research_source"] == ("llamapress" if confidence == "moderate" else "bundled_fallback")
    assert step["result"]["confidence"] == confidence
    expected = ["black", "navy"] if confidence == "moderate" else ["navy"]
    assert step["result"]["colors_used_for_ranking"] == expected
    assert "my-portrait.png" not in json.dumps(trace)
    assert "base64" not in json.dumps(trace)
    scoring = next(step for step in trace if step["tool"] == "build_and_score_outfits" and step["status"] == "done")
    palette_score = scoring["decision"]["winner_scores"]["palette"]
    assert 0 <= palette_score <= 1
    assert scoring["result"]["winner_palette_bonus"] == round(0.08 * palette_score, 3)
