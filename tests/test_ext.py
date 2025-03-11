from acoustid_ext.fingerprint import add_numbers


def test_add_numbers() -> None:
    assert add_numbers(1, 2) == 3
