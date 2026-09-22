from app.core.phone_masking import mask_phone


def test_mask_phone_keeps_only_last_four_digits():
    assert mask_phone("5543999998888") == "***8888"


def test_mask_phone_strips_non_digit_characters_first():
    assert mask_phone("+55 (43) 99999-8888") == "***8888"


def test_mask_phone_masks_entirely_when_four_digits_or_fewer():
    assert mask_phone("123") == "***"


def test_mask_phone_returns_none_for_falsy_input():
    assert mask_phone(None) is None
    assert mask_phone("") is None
