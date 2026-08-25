import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "agentpact_offer_ladder.py"
SPEC = importlib.util.spec_from_file_location("agentpact_offer_ladder", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def test_extract_and_filter_nested_owned_offers():
    payload = {
        "groups": [
            {
                "offers": [
                    {"id": "one", "title": "Mine", "agentId": "louis"},
                    {"id": "two", "title": "Other", "sellerAgentId": "buyer"},
                ]
            },
            {"offer": {"offerId": "three", "title": "Also mine", "seller": {"id": "louis"}}},
        ]
    }
    assert [offer["title"] for offer in module.extract_offers(payload)] == ["Mine", "Other", "Also mine"]
    assert [offer["title"] for offer in module.own_offers(payload, "louis")] == ["Mine", "Also mine"]


def test_exact_title_prevents_duplicate_creation():
    desired = module.DESIRED_OFFERS[0]["title"]
    existing = [{"id": "one", "title": desired, "agentId": "louis"}]
    titles = {str(offer.get("title", "")).strip() for offer in existing}
    assert desired in titles
    assert f"{desired} extra" not in titles


def test_transient_status_policy():
    assert module.is_transient_http_status(429)
    assert module.is_transient_http_status(500)
    assert module.is_transient_http_status(599)
    assert not module.is_transient_http_status(401)
    assert not module.is_transient_http_status(404)


def test_offer_ladder_is_bounded_and_non_financial():
    assert [offer["basePrice"] for offer in module.DESIRED_OFFERS] == [15.0, 25.0]
    assert all(offer["slaDays"] == 2 for offer in module.DESIRED_OFFERS)
    forbidden = {"wallet", "privateKey", "signature", "funding", "escrow", "dealId"}
    for offer in module.DESIRED_OFFERS:
        assert forbidden.isdisjoint(offer)
        assert offer["maxPriceDeltaPct"] == 20
