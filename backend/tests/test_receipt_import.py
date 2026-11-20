import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import httpx
import respx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings
from app.services import gmail_receipts
from app.services.receipts import Receipt


def test_stdio_mcp_imports_once_into_web_closet(client):
    async def import_through_mcp():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "app.mcp_server"],
            cwd=Path(__file__).resolve().parents[1],
            env={"DATABASE_URL": os.environ["DATABASE_URL"], "ANTHROPIC_API_KEY": ""},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {"list_closet", "import_purchase"}
            receipt = {"merchant": "Example Shop", "order_number": "#1234", "items": [
                {"name": "Navy test shirt", "category": "tops", "color": "navy", "quantity": 2},
            ]}
            result = await session.call_tool("import_purchase", {"receipt": receipt})
            assert not result.isError
            assert result.structuredContent["status"] == "imported"
            receipt.update(merchant="example   shop", order_number="1234")
            retry = await session.call_tool("import_purchase", {"receipt": receipt})
            assert not retry.isError
            assert retry.structuredContent["status"] == "already_imported"
            assert retry.structuredContent["item_ids"] == result.structuredContent["item_ids"]
            return set(result.structuredContent["item_ids"])

    ids = asyncio.run(import_through_mcp())
    items = [item for item in client.get("/api/closet").json() if item["name"] == "Navy test shirt"]
    assert len(items) == 2
    assert {item["id"] for item in items} == ids
    assert all(item["source"] == "receipt" and item["color"] == "navy" for item in items)


def test_gmail_sync_checks_only_receipt_label_and_persists_progress(client, monkeypatch, tmp_path):
    token = tmp_path / "gmail_token.json"
    token.touch()
    monkeypatch.setattr(get_settings(), "gmail_receipts_token_file", str(token))
    monkeypatch.setattr(gmail_receipts, "_access_token", lambda _: "fake-access-token")
    monkeypatch.setattr(gmail_receipts, "key_configured", lambda: True)
    calls = []

    def parse(**kwargs):
        message = json.loads(kwargs["messages"][0]["content"])
        calls.append(message["subject"])
        if "Canceled" in message["subject"]:
            receipt = None
        else:
            receipt = Receipt(merchant="Sample Shop", order_number="A-7", items=[
                {"name": "Olive test jacket", "category": "outerwear", "color": "olive"},
            ])
        return SimpleNamespace(parsed_output=SimpleNamespace(receipt=receipt))

    fake = SimpleNamespace(with_options=lambda **_: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    monkeypatch.setattr(gmail_receipts, "get_client", lambda: fake)

    def payload(subject, body):
        encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
        return {"payload": {"headers": [{"name": "Subject", "value": subject}], "mimeType": "text/html",
                            "body": {"data": encoded}}}

    base = gmail_receipts.GMAIL_URL
    with respx.mock(assert_all_called=True) as gmail:
        gmail.get(base + "labels").respond(json={"labels": [
            {"id": "label-1", "type": "user", "name": get_settings().gmail_receipts_label},
        ]})
        gmail.get(base + "profile").respond(json={"emailAddress": "shopper@example.test"})

        def list_messages(request: httpx.Request):
            assert request.url.params["labelIds"] == "label-1"
            assert request.url.params["q"] == "newer_than:14d"
            return httpx.Response(200, json={"messages": [{"id": value} for value in ("1", "2", "3")]})

        gmail.get(base + "messages").mock(side_effect=list_messages)
        confirmed = gmail.get(base + "messages/1").respond(json=payload("Order A-7", "<p>Olive test jacket</p>"))
        gmail.get(base + "messages/2").respond(json=payload("Canceled order A-8", "<p>Blue pants</p>"))
        gmail.get(base + "messages/3").respond(json=payload("Order A-7", "<p>Gift card</p>"))
        assert gmail_receipts.sync_gmail_receipts(Event()) == 1
        assert gmail_receipts.sync_gmail_receipts(Event()) == 0
        assert confirmed.call_count == 1

    assert len(calls) == 3
    added = [item for item in client.get("/api/closet").json() if item["source"] == "receipt"]
    assert [item["name"] for item in added] == ["Olive test jacket"]
