from app.core.phone_validation import is_valid_brazilian_mobile, normalize_brazilian_mobile


def test_normalize_adds_country_code_to_local_number():
    assert normalize_brazilian_mobile("(11) 91234-5678") == "5511912345678"


def test_normalize_keeps_existing_country_code():
    assert normalize_brazilian_mobile("+55 (11) 91234-5678") == "5511912345678"


def test_is_valid_accepts_well_formed_mobile():
    assert is_valid_brazilian_mobile("5511912345678") is True


def test_is_valid_rejects_missing_country_code():
    assert is_valid_brazilian_mobile("11912345678") is False


def test_is_valid_rejects_invalid_ddd():
    assert is_valid_brazilian_mobile("5500912345678") is False


def test_is_valid_rejects_landline_format_missing_leading_nine():
    assert is_valid_brazilian_mobile("5511812345678") is False


def test_is_valid_rejects_wrong_length():
    assert is_valid_brazilian_mobile("551191234567") is False
