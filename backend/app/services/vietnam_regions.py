from __future__ import annotations

import unicodedata


def normalize_region_name(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    normalized = " ".join(
        normalized.translate(str.maketrans({"-": " ", ".": " ", "_": " "})).split()
    )
    for prefix in ("thanh pho ", "tinh ", "tp "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    for suffix in (" province", " city"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized


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


def is_vietnam_province(value: str | None) -> bool:
    return bool(value and province_geocode_fallback(value))


def province_geocode_fallback(value: str) -> str | None:
    key = normalize_region_name(value)
    current_key = LEGACY_PROVINCE_ALIASES.get(key, key)
    return VIETNAM_PROVINCE_GEOCODE_QUERIES.get(current_key)
