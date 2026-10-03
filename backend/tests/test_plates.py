import pytest

from app.core.plates import normalize_plate, valid_plate


@pytest.mark.parametrize(
    "raw, expected",
    [(" tn 09-ab 1234 ", "TN09AB1234"), ("TN O9 AB I234", "TNO9ABI234"), ("tn09ab!1234", "TN09AB!1234")],
)
def test_normalization_preserves_ambiguity(raw, expected):
    assert normalize_plate(raw) == expected


@pytest.mark.parametrize("plate", ["TN09AB1234", "DL1CAB1234", "KA03MN7890", "22BH1234AA"])
def test_valid_plate(plate):
    assert valid_plate(plate)


@pytest.mark.parametrize("plate", ["", "TNO9ABI234", "ZZ09AB1234", "TN09AB123", "TN09AB!1234"])
def test_invalid_plate(plate):
    assert not valid_plate(plate)
