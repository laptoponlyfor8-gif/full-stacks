import hashlib
import hmac
import json

import pytest
from app.models.enums import SocialPlatform
from app.models.enums import KeywordMatchType
from app.services.automation_engine import match_keyword
from app.services.meta_webhooks import (
    event_idempotency_key,
    parse_webhook_payload,
    verify_signature,
)


def test_signature_validation_is_constant_format_and_bound_to_raw_body() -> None:
    body = b'{"object":"instagram","entry":[]}'
    signature = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("app-secret", body, f"sha256={signature}")
    assert not verify_signature("wrong-secret", body, f"sha256={signature}")
    assert not verify_signature("app-secret", body + b" ", f"sha256={signature}")
    assert not verify_signature("app-secret", body, signature)


def test_supported_instagram_facebook_comment_and_dm_events_are_normalized() -> None:
    instagram = parse_webhook_payload(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig-account",
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "comment-1",
                                "text": " link ",
                                "media": {"id": "media-1"},
                                "from": {"id": "person-1"},
                                "timestamp": 1_800_000_000,
                            },
                        }
                    ],
                    "messaging": [
                        {
                            "sender": {"id": "person-2"},
                            "timestamp": 1_800_000_001,
                            "message": {"mid": "mid-1", "text": "hello"},
                        }
                    ],
                }
            ],
        }
    )
    facebook = parse_webhook_payload(
        {
            "object": "page",
            "entry": [
                {
                    "id": "page-1",
                    "changes": [
                        {
                            "field": "feed",
                            "value": {
                                "item": "comment",
                                "verb": "add",
                                "comment_id": "fb-comment-1",
                                "post_id": "page-1_post-1",
                                "message": "PRICE",
                                "from": {"id": "person-3"},
                                "created_time": 1_800_000_000,
                            },
                        }
                    ],
                }
            ],
        }
    )
    assert [(event["event_type"], event["platform"]) for event in instagram] == [
        ("comment", "instagram"),
        ("direct_message", "instagram"),
    ]
    assert instagram[0]["payload"]["media_id"] == "media-1"
    assert facebook[0]["payload"]["comment_id"] == "fb-comment-1"
    assert event_idempotency_key(instagram[0]) == event_idempotency_key(instagram[0])


def test_malformed_or_unrelated_payloads_do_not_produce_events() -> None:
    with pytest.raises(ValueError):
        parse_webhook_payload([])
    assert parse_webhook_payload({"object": "unknown", "entry": []}) == []
    assert parse_webhook_payload({"object": "instagram", "entry": [{"id": "x", "changes": "bad"}]}) == []


def test_keyword_matching_modes_are_casefolded_and_boundary_aware() -> None:
    assert match_keyword("GET the Link please", "link", KeywordMatchType.CONTAINS)
    assert match_keyword("Limited OFFER", "limited offer", KeywordMatchType.EXACT)
    assert match_keyword("Need product details now", "product details", KeywordMatchType.PHRASE)
    assert not match_keyword("product details", "product detail", KeywordMatchType.PHRASE)
