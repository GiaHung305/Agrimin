import pytest
from pydantic import ValidationError

from app.api.routes.assistant import FarmProfileRequest


def test_farm_profile_normalizes_text_fields():
    request = FarmProfileRequest(
        name="  Nông   trại A  ",
        province="  Lâm   Đồng ",
        area_ha=2.5,
        farming_style="  Hữu   cơ  ",
    )

    assert request.name == "Nông trại A"
    assert request.province == "Lâm Đồng"
    assert request.farming_style == "Hữu cơ"


def test_farm_profile_converts_blank_optional_text_to_none():
    request = FarmProfileRequest(province="   ", farming_style="\t")

    assert request.province is None
    assert request.farming_style is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": "   "}, "name"),
        ({"area_ha": 0}, "area_ha"),
        ({"area_ha": -1}, "area_ha"),
    ],
)
def test_farm_profile_rejects_values_that_cannot_describe_a_farm(payload, field):
    with pytest.raises(ValidationError) as error:
        FarmProfileRequest(**payload)

    assert field in str(error.value)
