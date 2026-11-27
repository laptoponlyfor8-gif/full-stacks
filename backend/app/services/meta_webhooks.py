import hashlib
import hmac
import json
from typing import Any

MAX_WEBHOOK_BYTES = 1_000_000


def verify_signature(app_secret: str, raw_body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[7:])


def parse_webhook_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
        raise ValueError("Malformed Meta webhook payload.")
    provider_object = payload.get("object")
    if provider_object not in {"instagram", "page"}:
        return []

    events: list[dict[str, Any]] = []
    for entry in payload["entry"]:
        if not isinstance(entry, dict):
            continue
        account_id = entry.get("id")
        if not isinstance(account_id, (str, int)) or not str(account_id):
            continue
        account_id = str(account_id)
        if provider_object == "instagram":
            changes = entry.get("changes", [])
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict) or not isinstance(change.get("value"), dict):
                        continue
                    value = change["value"]
                    field = change.get("field")
                    if field in {"comments", "live_comments"}:
                        comment_id = value.get("id")
                        text = value.get("text", "")
                        media = value.get("media")
                        actor = value.get("from")
                        if not _valid_id(comment_id) or not isinstance(text, str):
                            continue
                        media_id = media.get("id") if isinstance(media, dict) else None
                        actor_id = actor.get("id") if isinstance(actor, dict) else None
                        events.append(
                            {
                                "platform": "instagram",
                                "account_id": account_id,
                                "event_type": "comment",
                                "external_id": str(comment_id),
                                "payload": {
                                    "comment_id": str(comment_id),
                                    "text": text[:5000],
                                    "media_id": str(media_id) if _valid_id(media_id) else None,
                                    "actor_id": str(actor_id) if _valid_id(actor_id) else None,
                                    "timestamp": value.get("timestamp"),
                                    "is_live": field == "live_comments",
                                },
                            }
                        )
        else:
            changes = entry.get("changes", [])
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict) or change.get("field") != "feed":
                        continue
                    value = change.get("value")
                    if not isinstance(value, dict) or value.get("item") != "comment":
                        continue
                    comment_id = value.get("comment_id")
                    text = value.get("message", "")
                    if not _valid_id(comment_id) or not isinstance(text, str):
                        continue
                    actor = value.get("from")
                    actor_id = actor.get("id") if isinstance(actor, dict) else None
                    events.append(
                        {
                            "platform": "facebook",
                            "account_id": account_id,
                            "event_type": "comment",
                            "external_id": str(comment_id),
                            "payload": {
                                "comment_id": str(comment_id),
                                "text": text[:5000],
                                "media_id": str(value.get("post_id")) if _valid_id(value.get("post_id")) else None,
                                "actor_id": str(actor_id) if _valid_id(actor_id) else None,
                                "timestamp": value.get("created_time"),
                                "is_live": False,
                            },
                        }
                    )

        messaging = entry.get("messaging", [])
        if isinstance(messaging, list):
            for item in messaging:
                if not isinstance(item, dict):
                    continue
                message = item.get("message")
                sender = item.get("sender")
                if (
                    not isinstance(message, dict)
                    or not isinstance(sender, dict)
                    or message.get("is_echo") is True
                    or not isinstance(message.get("text"), str)
                    or not _valid_id(message.get("mid"))
                ):
                    continue
                events.append(
                    {
                        "platform": "instagram" if provider_object == "instagram" else "facebook",
                        "account_id": account_id,
                        "event_type": "direct_message",
                        "external_id": str(message["mid"]),
                        "payload": {
                            "message_id": str(message["mid"]),
                            "text": message["text"][:5000],
                            "actor_id": str(sender["id"]) if _valid_id(sender.get("id")) else None,
                            "timestamp": item.get("timestamp"),
                        },
                    }
                )
    return events


def event_idempotency_key(event: dict[str, Any]) -> str:
    raw = "\x1f".join(
        (event["platform"], event["account_id"], event["event_type"], event["external_id"])
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_id(value: Any) -> bool:
    return isinstance(value, (str, int)) and bool(str(value).strip()) and len(str(value)) <= 255


def decode_request(raw_body: bytes) -> dict[str, Any]:
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        raise ValueError("Meta webhook payload exceeds the allowed size.")
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Meta webhook JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Malformed Meta webhook payload.")
    return payload
