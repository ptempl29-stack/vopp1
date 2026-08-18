import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "test")

from routers import claims


class FakeClaimPackets:
    def __init__(self, claim):
        self.claim = claim
        self.deleted = False
        self.update = None

    async def find_one(self, *_args, **_kwargs):
        return self.claim

    async def delete_one(self, *_args, **_kwargs):
        self.deleted = True

    async def update_one(self, _query, update):
        self.update = update


class FakeDb:
    def __init__(self, claim):
        self.claim_packets = FakeClaimPackets(claim)


async def no_audit(*_args, **_kwargs):
    return None


def test_claim_record_is_deleted_even_when_storage_cleanup_fails(monkeypatch):
    fake = FakeDb({
        "id": "claim-1",
        "items": [{"source": "invoice", "storage_path": "missing.pdf"}],
    })
    monkeypatch.setattr(claims, "db", fake)
    monkeypatch.setattr(claims, "log_audit", no_audit)

    def failing_cleanup(_path):
        assert fake.claim_packets.deleted is True
        raise FileNotFoundError("already missing")

    monkeypatch.setattr(claims, "delete_object", failing_cleanup)

    result = asyncio.run(claims.delete_claim("claim-1", user={"name": "Admin"}))

    assert fake.claim_packets.deleted is True
    assert result == {"ok": True, "cleanup_pending": 1}


def test_removed_item_is_suppressed_before_failed_storage_cleanup(monkeypatch):
    item = {
        "id": "item-1", "source": "invoice", "invoice_id": "invoice-64",
        "storage_path": "missing.pdf",
    }
    fake = FakeDb({"id": "claim-1", "items": [item]})
    monkeypatch.setattr(claims, "db", fake)

    async def claim_response(_claim_id):
        return {"id": "claim-1", "items": []}

    monkeypatch.setattr(claims, "_claim_response", claim_response)

    def failing_cleanup(_path):
        assert fake.claim_packets.update["$pull"] == {"items": {"id": "item-1"}}
        assert fake.claim_packets.update["$addToSet"] == {
            "excluded_document_keys": "invoice:invoice-64",
        }
        raise FileNotFoundError("already missing")

    monkeypatch.setattr(claims, "delete_object", failing_cleanup)

    result = asyncio.run(claims.remove_item("claim-1", "item-1", user={"name": "Admin"}))

    assert result["items"] == []
    assert result["cleanup_pending"] == 1
