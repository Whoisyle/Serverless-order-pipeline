from core import DeadLetterSummary, can_resubmit, extract_order_id, format_table


def _summary(**overrides):
    base = {
        "subscription": "validation",
        "topic": "orders",
        "message_id": "m1",
        "order_id": "ord-1",
        "delivery_count": 5,
        "dead_letter_reason": "MaxDeliveryCountExceeded",
        "dead_letter_error_description": None,
        "enqueued_time": None,
    }
    base.update(overrides)
    return DeadLetterSummary(**base)


def test_extract_order_id_from_valid_json_bytes():
    assert extract_order_id(b'{"orderId": "ord-42"}') == "ord-42"


def test_extract_order_id_from_valid_json_str():
    assert extract_order_id('{"orderId": "ord-42"}') == "ord-42"


def test_extract_order_id_missing_field():
    assert extract_order_id('{"customerId": "c1"}') is None


def test_extract_order_id_non_dict_json():
    assert extract_order_id("[1, 2, 3]") is None


def test_extract_order_id_malformed_json():
    assert extract_order_id("not json at all") is None


def test_extract_order_id_none_body():
    assert extract_order_id(None) is None


def test_extract_order_id_bad_unicode():
    assert extract_order_id(b"\xff\xfe\x00\x01") is None


def test_can_resubmit_with_order_id():
    assert can_resubmit(_summary(order_id="ord-1"))


def test_cannot_resubmit_without_order_id():
    assert not can_resubmit(_summary(order_id=None))


def test_format_table_empty():
    assert format_table([]) == "No dead-lettered messages found."


def test_format_table_has_header_and_row():
    table = format_table([_summary()])
    assert "SUBSCRIPTION" in table
    assert "ord-1" in table
    assert "validation" in table


def test_format_table_shows_unknown_for_missing_order_id():
    table = format_table([_summary(order_id=None)])
    assert "(unknown)" in table
