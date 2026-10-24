import asyncio
import json
from io import BytesIO

import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.core.vision import normalize_photo
from app.db import get_session
from app.integrations.common import AdapterError, AdapterResult
from app.integrations.decisions_adapter import DecisionsClient, ItemClassification, TAXONOMIES, Tag
from app.integrations.vision_client import BoundingBox, DetectedGarment, GarmentDetection, VisionClient
from app.main import app
from app.models import ClosetScanRecord, WardrobeItem
from app.routers.scan import get_scan_service
from app.services.scanning import ScanService


def photo(color="blue", **kwargs):
    stream = BytesIO()
    Image.new("RGB", (200, 100), color).save(stream, format="JPEG", **kwargs)
    return stream.getvalue()


def garment(index=0, **overrides):
    values = {"name": f"Blue shirt {index}", "description": "A blue short-sleeved shirt.", "label_text": None,
              "confidence": 0.95, "box": BoundingBox(x_min=index * 0.5, y_min=0, x_max=(index + 1) * 0.5, y_max=1)}
    return DetectedGarment(**{**values, **overrides})


class FakeVision:
    def __init__(self, items=None):
        self.items = [garment(), garment(1)] if items is None else items
        self.calls = 0

    async def detect_items(self, image_url):
        self.calls += 1
        assert image_url.startswith("data:image/jpeg;base64,")
        return AdapterResult(data=GarmentDetection(items=self.items, has_more_items=False, warnings=[]), source="live")


class FakeDecisions:
    def __init__(self, *, category="tops", fail_on=None):
        self.calls = 0
        self.category = category
        self.fail_on = fail_on

    async def classify_item(self, description, *, image_url):
        self.calls += 1
        if self.calls == self.fail_on:
            raise AdapterError("Decisions call failed.")
        values = {"category": self.category, "style": "casual", "formality": "casual", "season": "summer",
                  "material": "cotton", "color": "blue"}
        return AdapterResult(data=ItemClassification(tags={name: Tag(value=value, confidence=0.95) for name, value in values.items()},
                                                    needs_review=False), source="live")


@pytest.fixture
def setup_scan(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    settings = Settings(_env_file=None, scan_uploads_dir=tmp_path / "uploads", api_recordings_path=tmp_path / "calls.jsonl")
    vision = FakeVision()
    decisions = FakeDecisions()
    service = ScanService(settings, vision=vision, decisions=decisions)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_scan_service] = lambda: service
    try:
        yield TestClient(app), service, engine, vision, decisions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def upload(client, content=None, key=None):
    return client.post("/api/scan", files={"file": ("../../private-file.jpg", photo() if content is None else content, "image/jpeg")},
                       headers={"Idempotency-Key": key} if key else {})


def test_batch_scan_saves_existing_closet_rows_and_metadata(setup_scan):
    client, service, engine, vision, decisions = setup_scan
    response = upload(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "needs_review"
    assert len(result["items"]) == 2
    assert vision.calls == 1 and decisions.calls == 2
    for item in result["items"]:
        assert item["id"].startswith("itm_")
        assert item["category"] == "tops" and item["source"] == "scan"
        assert item["material"] is None  # A photograph cannot verify cotton without a label.
        assert item["waterproof"] is False
        assert item["scan_meta"]["waterproof_verified"] is False
        assert item["scan_meta"]["tags"]["material"]["value"] == "unknown"
        assert "private-file" not in item["image_url"]
        image_path = service.settings.scan_uploads_dir / item["image_url"].split("/")[-1]
        with Image.open(image_path) as image:
            assert image.size == (100, 100)
            assert not image.getexif()
    with Session(engine) as session:
        assert len(session.exec(select(WardrobeItem)).all()) == 2
        assert len(session.exec(select(ClosetScanRecord)).all()) == 1
    assert len(client.get("/api/closet").json()) == 2
    assert client.get(f"/api/scan/{result['id']}").json() == result


def test_idempotency_returns_original_without_repeating_models(setup_scan):
    client, _, _, vision, decisions = setup_scan
    first = upload(client, key="retry-key-001")
    second = upload(client, key="retry-key-001")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert vision.calls == 1 and decisions.calls == 2
    mismatch = upload(client, photo("red"), key="retry-key-001")
    assert mismatch.status_code == 409
    assert vision.calls == 1


def test_undo_removes_only_batch_rows_and_files_and_is_repeatable(setup_scan):
    client, service, engine, _, _ = setup_scan
    with Session(engine) as session:
        manual = WardrobeItem(name="Keep this", category="tops", source="manual")
        session.add(manual)
        session.commit()
    result = upload(client, key="undo-key-001").json()
    assert len(list(service.settings.scan_uploads_dir.glob("*.jpg"))) == 2
    undo = client.post(f"/api/scan/{result['id']}/undo")
    assert undo.status_code == 200 and undo.json()["status"] == "undone"
    assert undo.json()["items"] == []
    assert list(service.settings.scan_uploads_dir.glob("*.jpg")) == []
    assert [item["name"] for item in client.get("/api/closet").json()] == ["Keep this"]
    assert client.post(f"/api/scan/{result['id']}/undo").json() == undo.json()
    assert upload(client, key="undo-key-001").json()["status"] == "undone"
    with Session(engine) as session:
        assert len(session.exec(select(WardrobeItem)).all()) == 1


@pytest.mark.parametrize("content", [b"", b"not an image", b"<svg><script/></svg>", b"GIF89a-invalid"])
def test_invalid_photo_fails_before_models(setup_scan, content):
    client, _, engine, vision, decisions = setup_scan
    assert upload(client, content).status_code == 422
    assert vision.calls == decisions.calls == 0
    with Session(engine) as session:
        assert session.exec(select(ClosetScanRecord)).all() == []


def test_size_and_pixel_limits_before_models(setup_scan):
    client, service, _, vision, _ = setup_scan
    service.settings.scan_max_image_bytes = 10
    assert upload(client).status_code == 413
    service.settings.scan_max_image_bytes = 1024 * 1024
    service.settings.scan_max_image_pixels = 10
    assert upload(client).status_code == 422
    assert vision.calls == 0


def test_orientation_and_metadata_are_normalized():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private camera metadata"
    image = normalize_photo(photo(exif=exif), Settings(_env_file=None))
    assert image.size == (100, 200)
    assert not image.getexif()
    assert not image.info


@pytest.mark.parametrize("image_format", ["PNG", "WEBP", "HEIF"])
def test_supported_image_formats_decode(image_format):
    stream = BytesIO()
    Image.new("RGB", (40, 30), "green").save(stream, format=image_format)
    image = normalize_photo(stream.getvalue(), Settings(_env_file=None))
    assert image.size == (40, 30) and image.mode == "RGB"


def test_animated_png_is_rejected_before_models(setup_scan):
    client, _, _, vision, _ = setup_scan
    stream = BytesIO()
    Image.new("RGB", (40, 30), "blue").save(stream, format="PNG", save_all=True,
        append_images=[Image.new("RGB", (40, 30), "red")], duration=100, loop=0)
    assert upload(client, stream.getvalue()).status_code == 422
    assert vision.calls == 0


def test_model_failure_does_not_save_partial_batch(setup_scan):
    client, service, engine, _, decisions = setup_scan
    decisions.fail_on = 2
    response = upload(client)
    assert response.status_code == 502
    assert decisions.calls == 2
    assert list(service.settings.scan_uploads_dir.glob("*")) == []
    with Session(engine) as session:
        assert session.exec(select(WardrobeItem)).all() == []
        assert session.exec(select(ClosetScanRecord)).all() == []


def test_database_failure_rolls_back_batch_and_removes_images(setup_scan, monkeypatch):
    client, service, engine, _, _ = setup_scan
    def fail_commit(session):
        raise SQLAlchemyError("simulated storage failure")
    monkeypatch.setattr(Session, "commit", fail_commit)
    response = upload(client)
    assert response.status_code == 500
    assert list(service.settings.scan_uploads_dir.glob("*")) == []
    with Session(engine) as session:
        assert session.exec(select(WardrobeItem)).all() == []
        assert session.exec(select(ClosetScanRecord)).all() == []


def test_unknown_category_is_not_saved_as_a_guessed_top(setup_scan):
    client, service, engine, _, decisions = setup_scan
    decisions.category = "unknown"
    result = upload(client).json()
    assert result["status"] == "needs_review"
    assert result["items"] == [] and len(result["issues"]) == 2
    assert list(service.settings.scan_uploads_dir.glob("*")) == []


def test_duplicate_regions_and_uncertain_detections_are_skipped(setup_scan):
    client, _, _, vision, decisions = setup_scan
    vision.items = [garment(), garment(), garment(1, confidence=0.2)]
    result = upload(client).json()
    assert len(result["items"]) == 1
    assert len(result["issues"]) == 2
    assert decisions.calls == 1


def test_readable_material_label_allows_material_tag(setup_scan):
    client, _, _, vision, _ = setup_scan
    vision.items = [garment(label_text="100% cotton")]
    result = upload(client).json()
    assert result["items"][0]["material"] == "cotton"


def test_unrelated_label_does_not_verify_guessed_material(setup_scan):
    client, _, _, vision, _ = setup_scan
    vision.items = [garment(label_text="Wash at 30 degrees")]
    result = upload(client).json()
    assert result["items"][0]["material"] is None


def test_reset_clears_scan_records_retry_keys_and_images(setup_scan, monkeypatch):
    client, service, engine, vision, _ = setup_scan
    monkeypatch.setattr("app.routers.dev.get_settings", lambda: service.settings)
    first = upload(client, key="reset-key-001").json()
    assert client.post("/api/dev/reset").json() == {"items": 28, "warnings": []}
    assert list(service.settings.scan_uploads_dir.glob("*.jpg")) == []
    with Session(engine) as session:
        assert session.exec(select(ClosetScanRecord)).all() == []
    assert client.get(f"/api/scan/{first['id']}").status_code == 404
    second = upload(client, key="reset-key-001").json()
    assert second["id"] != first["id"]
    assert vision.calls == 2


def test_empty_photo_detection_saves_no_closet_items(setup_scan):
    client, _, _, vision, decisions = setup_scan
    vision.items = []
    result = upload(client).json()
    assert result["status"] == "empty" and result["items"] == []
    assert decisions.calls == 0 and result["warnings"]


def test_mock_scan_is_explicit_and_saves_nothing(setup_scan):
    client, service, _, _, _ = setup_scan
    service.settings.scan_vision_mode = "mock"
    service.vision = VisionClient(service.settings)
    response = upload(client)
    assert response.status_code == 200
    assert response.json()["status"] == "mock"
    assert response.json()["items"] == []
    assert response.json()["sources"] == {"vision": "mock"}
    assert list(service.settings.scan_uploads_dir.glob("*")) == []


def test_timeout_does_not_save_items(setup_scan):
    client, service, engine, vision, _ = setup_scan
    async def delayed(image_url):
        await asyncio.sleep(1)
    vision.detect_items = delayed
    service.settings.scan_timeout_seconds = 0.01
    assert upload(client).status_code == 504
    with Session(engine) as session:
        assert session.exec(select(WardrobeItem)).all() == []


def test_missing_scan_and_bad_idempotency_key(setup_scan):
    client, _, _, vision, _ = setup_scan
    assert client.get("/api/scan/unknown").status_code == 404
    assert client.post("/api/scan/unknown/undo").status_code == 404
    assert upload(client, key="../bad-key").status_code == 422
    assert vision.calls == 0


def _model_response(data=None, *, refusal=False):
    content = {"type": "refusal", "refusal": "Cannot analyze this image."} if refusal else {
        "type": "output_text", "text": json.dumps(data), "annotations": []}
    return {"id": "resp_scan", "object": "response", "created_at": 1, "status": "completed", "model": "gpt-6-astra",
            "output": [{"id": "msg_scan", "type": "message", "role": "assistant", "status": "completed", "content": [content]}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}


def test_actual_sdk_photo_detection_decisions_save_and_replay(setup_scan):
    _, service, engine, _, _ = setup_scan
    async def run():
        requests = []
        def respond(req):
            body = json.loads(req.content)
            requests.append(req.url.path)
            if req.url.path == "/v1/responses":
                assert body["store"] is False
                assert body["input"][0]["content"][0]["image_url"].startswith("data:image/jpeg;base64,")
                assert body["text"]["format"]["type"] == "json_schema"
                return httpx2.Response(200, json=_model_response(GarmentDetection(
                    items=[garment(), garment(1)], has_more_items=False, warnings=[]).model_dump()))
            assert req.url.path == "/v1/decisions"
            assert len(body["questions"]) == len(TAXONOMIES)
            assert body["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
            values = {"category": "tops", "style": "casual", "formality": "casual", "season": "summer", "material": "cotton", "color": "blue"}
            return httpx2.Response(200, json={"model": "gpt-6-luna", "answers": [
                {"type": "choice", "name": name, "choice": value, "confidence": 0.99, "probabilities": []}
                for name, value in values.items()], "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})

        async with AsyncOpenAI(api_key="test-private-key", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond))) as api:
            service.vision = VisionClient(service.settings, api)
            service.decisions = DecisionsClient(service.settings, api)
            with Session(engine) as session:
                live = await service.scan(photo(), session, request_key="real-sdk-test")
                assert len(live.items) == 2
                assert set(live.sources.values()) == {"live"}
                service.settings.scan_vision_mode = "replay"
                service.settings.decisions_mode = "replay"
                replay = await service.scan(photo(), session, request_key="replay-sdk-test")
                assert len(replay.items) == 2
                assert set(replay.sources.values()) == {"replay"}
                assert len(session.exec(select(WardrobeItem)).all()) == 4
        assert requests == ["/v1/responses", "/v1/decisions", "/v1/decisions"]
        recorded = service.settings.api_recordings_path.read_text()
        assert "data:image" not in recorded and "test-private-key" not in recorded
        assert "private-file" not in recorded
    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["refusal", "bbox", "too_many", "permission"])
def test_vision_provider_failure_is_not_a_successful_scan(setup_scan, invalid):
    _, service, engine, _, _ = setup_scan
    async def run():
        data = GarmentDetection(items=[garment()], has_more_items=False, warnings=[]).model_dump()
        if invalid == "bbox":
            data["items"][0]["box"]["x_max"] = 1.5
        elif invalid == "too_many":
            data["items"] *= 9
        def respond(req):
            if invalid == "permission":
                return httpx2.Response(403, json={"error": {"message": "private-provider-message", "type": "permission_error"}})
            return httpx2.Response(200, json=_model_response(data, refusal=invalid == "refusal"))
        async with AsyncOpenAI(api_key="test", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond))) as api:
            service.vision = VisionClient(service.settings, api)
            with Session(engine) as session:
                with pytest.raises(AdapterError) as exc:
                    await service.scan(photo(), session)
                assert "private-provider-message" not in str(exc.value)
                assert session.exec(select(WardrobeItem)).all() == []
                assert session.exec(select(ClosetScanRecord)).all() == []
        assert list(service.settings.scan_uploads_dir.glob("*")) == []
    asyncio.run(run())
