from __future__ import annotations

import re
import unicodedata


def normalize_region_name(value: str) -> str:
    normalized = _fold_region_text(value)
    for prefix in ("thanh pho ", "tinh ", "tp "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    for suffix in (" province", " city"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized


def _fold_region_text(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return " ".join(
        normalized.translate(str.maketrans({"-": " ", ".": " ", "_": " "})).split()
    )


# Current 34 province-level units under Decision 19/2025/QD-TTg. Values are
# representative Vietnamese cities used only when the provider cannot resolve
# the province name directly; they are not farm coordinates.
VIETNAM_PROVINCE_GEOCODE_QUERIES: dict[str, str] = {
    "ha noi": "Hanoi",
    "cao bang": "Cao Bang",
    "tuyen quang": "Tuyen Quang",
    "dien bien": "Dien Bien Phu",
    "lai chau": "Lai Chau",
    "son la": "Son La",
    "lao cai": "Lao Cai",
    "thai nguyen": "Thai Nguyen",
    "lang son": "Lang Son",
    "quang ninh": "Ha Long",
    "bac ninh": "Bac Ninh",
    "phu tho": "Viet Tri",
    "hai phong": "Hai Phong",
    "hung yen": "Hung Yen",
    "ninh binh": "Ninh Binh",
    "thanh hoa": "Thanh Hoa",
    "nghe an": "Vinh",
    "ha tinh": "Ha Tinh",
    "quang tri": "Dong Hoi",
    "hue": "Hue",
    "da nang": "Da Nang",
    "quang ngai": "Quang Ngai",
    "gia lai": "Quy Nhon",
    "dak lak": "Buon Ma Thuot",
    "khanh hoa": "Nha Trang",
    "lam dong": "Da Lat",
    "dong nai": "Bien Hoa",
    "ho chi minh": "Ho Chi Minh City",
    "tay ninh": "Tan An",
    "can tho": "Can Tho",
    "vinh long": "Vinh Long",
    "dong thap": "My Tho",
    "an giang": "Rach Gia",
    "ca mau": "Ca Mau",
}

# Profiles created before the July 2025 consolidation remain usable. Each old
# name resolves through the current province's representative weather point.
LEGACY_PROVINCE_ALIASES: dict[str, str] = {
    "ha giang": "tuyen quang",
    "yen bai": "lao cai",
    "bac kan": "thai nguyen",
    "vinh phuc": "phu tho",
    "hoa binh": "phu tho",
    "bac giang": "bac ninh",
    "thai binh": "hung yen",
    "hai duong": "hai phong",
    "ha nam": "ninh binh",
    "nam dinh": "ninh binh",
    "quang binh": "quang tri",
    "quang nam": "da nang",
    "kon tum": "quang ngai",
    "binh dinh": "gia lai",
    "phu yen": "dak lak",
    "ninh thuan": "khanh hoa",
    "dak nong": "lam dong",
    "binh thuan": "lam dong",
    "binh phuoc": "dong nai",
    "ba ria vung tau": "ho chi minh",
    "binh duong": "ho chi minh",
    "long an": "tay ninh",
    "soc trang": "can tho",
    "hau giang": "can tho",
    "ben tre": "vinh long",
    "tra vinh": "vinh long",
    "tien giang": "dong thap",
    "bac lieu": "ca mau",
    "kien giang": "an giang",
    "thua thien hue": "hue",
    "hcm": "ho chi minh",
    "tphcm": "ho chi minh",
    "sai gon": "ho chi minh",
}

# Weather must remain local even when an old province name belongs to a larger
# post-2025 administrative unit. Routing ``Bình Thuận`` to the current unit's
# representative point in Đà Lạt, for example, would produce the wrong climate.
LEGACY_WEATHER_GEOCODE_QUERIES: dict[str, str] = {
    "ha giang": "Ha Giang",
    "yen bai": "Yen Bai",
    "bac kan": "Bac Kan",
    "vinh phuc": "Vinh Yen",
    "hoa binh": "Hoa Binh",
    "bac giang": "Bac Giang",
    "thai binh": "Thai Binh",
    "hai duong": "Hai Duong",
    "ha nam": "Phu Ly",
    "nam dinh": "Nam Dinh",
    "quang binh": "Dong Hoi",
    "quang nam": "Tam Ky",
    "kon tum": "Kon Tum",
    "binh dinh": "Quy Nhon",
    "phu yen": "Tuy Hoa",
    "ninh thuan": "Phan Rang-Thap Cham",
    "dak nong": "Gia Nghia",
    "binh thuan": "Phan Thiet",
    "binh phuoc": "Dong Xoai",
    "ba ria vung tau": "Vung Tau",
    "binh duong": "Thu Dau Mot",
    "long an": "Tan An",
    "soc trang": "Soc Trang",
    "hau giang": "Vi Thanh",
    "ben tre": "Ben Tre",
    "tra vinh": "Tra Vinh",
    "tien giang": "My Tho",
    "bac lieu": "Bac Lieu",
    "kien giang": "Rach Gia",
    "thua thien hue": "Hue",
    "hcm": "Ho Chi Minh City",
    "tphcm": "Ho Chi Minh City",
    "sai gon": "Ho Chi Minh City",
}


def _weather_location_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for province_key, query in VIETNAM_PROVINCE_GEOCODE_QUERIES.items():
        aliases[province_key] = query
        aliases[normalize_region_name(query)] = query
    aliases.update(LEGACY_WEATHER_GEOCODE_QUERIES)
    return aliases


_WEATHER_LOCATION_ALIASES = _weather_location_aliases()

_LOCATION_REPLY_FILLERS = {
    "a",
    "ban",
    "ba",
    "bay",
    "chieu",
    "cho",
    "con",
    "dang",
    "dia",
    "diem",
    "giup",
    "gio",
    "hien",
    "hom",
    "la",
    "mai",
    "minh",
    "muon",
    "nay",
    "ngay",
    "nhe",
    "nong",
    "o",
    "pho",
    "sang",
    "tai",
    "thanh",
    "thi",
    "tinh",
    "toi",
    "tp",
    "trai",
    "truoc",
    "vay",
    "voi",
    "xem",
}


def _weather_location_matches(
    question: str,
) -> tuple[str, list[tuple[int, int, str]]]:
    normalized = _fold_region_text(question)
    matches: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    aliases = sorted(
        _WEATHER_LOCATION_ALIASES.items(),
        key=lambda item: (len(item[0].split()), len(item[0])),
        reverse=True,
    )
    for alias, query in aliases:
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        )
        for match in pattern.finditer(normalized):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            matches.append((span[0], span[1], query))
    return normalized, sorted(matches)


def weather_locations_from_question(question: str) -> list[str]:
    """Return explicit Vietnamese weather locations in mention order.

    Longer aliases reserve their span first, preventing ``Vĩnh`` from being
    interpreted separately inside ``Vĩnh Long``. Returned values are provider
    geocoding queries, not claims about the user's saved farm location.
    """
    _, matches = _weather_location_matches(question)
    ordered_queries = [query for _, _, query in matches]
    return list(dict.fromkeys(ordered_queries))


def is_weather_location_reply(question: str) -> bool:
    """Return true when a reply contains one location and harmless fillers only.

    This deliberately does not infer weather intent by itself. Callers must also
    verify that trusted recent conversation context is awaiting a weather
    location. The narrow shape prevents agricultural statements such as
    ``Tôi trồng cà phê ở Đà Lạt`` from being reclassified as weather requests.
    """
    normalized, matches = _weather_location_matches(question)
    if len({query for _, _, query in matches}) != 1:
        return False

    remaining = list(normalized)
    for start, end, _ in matches:
        remaining[start:end] = " " * (end - start)
    remaining_tokens = set(re.findall(r"[a-z0-9]+", "".join(remaining)))
    return remaining_tokens <= _LOCATION_REPLY_FILLERS


def is_vietnam_province(value: str | None) -> bool:
    return bool(value and province_geocode_fallback(value))


def province_geocode_fallback(value: str) -> str | None:
    key = normalize_region_name(value)
    return (
        VIETNAM_PROVINCE_GEOCODE_QUERIES.get(key)
        or LEGACY_WEATHER_GEOCODE_QUERIES.get(key)
    )
