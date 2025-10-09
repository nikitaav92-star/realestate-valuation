import pytest

from etl.collector_cian.mapper import extract_offers, to_listing, to_price


def test_extract_offers_prefers_serialized_path():
    offer = {"offerId": 1, "price": {"value": 10}}
    response = {"data": {"offersSerialized": [offer]}}
    result = extract_offers(response)
    assert result == [offer]

def test_extract_offers_handles_items_path():
    offer = {"id": 2}
    response = {"data": {"items": [offer]}}
    assert extract_offers(response) == [offer]


def test_extract_offers_handles_missing_paths():
    response = {"unexpected": {}, "offersSerialized": []}
    assert extract_offers(response) == []


def test_to_listing_and_price_mapping():
    offer = {
        "offerId": 42,
        "seoUrl": "https://example/listing",
        "region": 77,
        "operationName": "sale",
        "roomsCount": 2,
        "spaceTotal": 45.5,
        "floor": 3,
        "address": "Test street",
        "sellerName": "owner",
        "price": {"value": 12345678},
    }
    listing = to_listing(offer)
    price = to_price(offer)

    assert listing.id == 42
    assert listing.url.endswith("listing")
    assert listing.region == 77
    assert listing.rooms == 2
    assert pytest.approx(listing.area_total, rel=1e-4) == 45.5
    assert listing.address == "Test street"
    assert listing.seller_type == "owner"

    assert price.id == 42
    assert price.price == pytest.approx(12345678)


def test_to_price_handles_scalar():
    offer = {"id": 7, "price": 9900000}
    assert to_price(offer).price == pytest.approx(9900000)
