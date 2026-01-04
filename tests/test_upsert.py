from decimal import Decimal

import pytest

from etl.models import Listing
from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed


@pytest.fixture(scope="module")
def db_conn():
    conn = get_db_connection()
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("TRUNCATE listing_prices")
        cur.execute("TRUNCATE listings CASCADE")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _fetch_listing(conn, listing_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT url, rooms, first_seen, last_seen, is_active FROM listings WHERE id = %s",
            (listing_id,),
        )
        return cur.fetchone()


def _count_prices(conn, listing_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), MAX(price) FROM listing_prices WHERE id = %s",
            (listing_id,),
        )
        return cur.fetchone()


def test_upsert_listing_updates_last_seen(db_conn):
    listing = Listing(
        id=1001,
        url="https://example/1001",
        region=77,
        deal_type="sale",
        rooms=2,
        area_total=40.0,
        floor=5,
        address="Test address",
        seller_type="owner",
    )

    upsert_listing(db_conn, listing)
    row1 = _fetch_listing(db_conn, listing.id)
    assert row1 is not None
    first_seen_1, last_seen_1 = row1[2], row1[3]
    assert first_seen_1 == last_seen_1
    assert row1[4] is True

    updated_listing = listing.model_copy(update={"rooms": 3, "url": "https://example/1001-upd"})
    upsert_listing(db_conn, updated_listing)
    row2 = _fetch_listing(db_conn, listing.id)
    assert row2[0] == "https://example/1001-upd"
    assert row2[1] == 3
    assert row2[2] == first_seen_1
    assert row2[3] >= last_seen_1
    assert row2[4] is True

    db_conn.commit()


def test_upsert_price_inserts_only_on_change(db_conn):
    listing_id = 1002
    listing = Listing(
        id=listing_id,
        url="https://example/1002",
        region=77,
        deal_type="sale",
        rooms=1,
        area_total=25.0,
        floor=2,
        address="Another",
        seller_type="agent",
    )
    upsert_listing(db_conn, listing)

    inserted_first = upsert_price_if_changed(db_conn, listing_id, 9_900_000)
    inserted_again = upsert_price_if_changed(db_conn, listing_id, 9_900_000)
    inserted_second = upsert_price_if_changed(db_conn, listing_id, 10_100_000)

    count, max_price = _count_prices(db_conn, listing_id)
    assert inserted_first is True
    assert inserted_again is False
    assert inserted_second is True
    assert count == 2
    assert max_price == Decimal("10100000")

    db_conn.commit()
