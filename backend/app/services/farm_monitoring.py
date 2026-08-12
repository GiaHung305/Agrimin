from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.vietnam_regions import is_vietnam_province
from app.workflow.confidence import compute_weather_risk_confidence


LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SUPPORTED_FREQUENCIES = (6, 12, 24)
SUPPORTED_NOTIFICATION_SCOPES = ("in_app", "push_and_in_app")

# Kept as compatibility aliases for existing tomato schedules and reports.
POLICY_VERSION = "tomato-moisture-risk-v1"
REMINDER_TYPE = "tomato_disease_risk"
RISK_TYPE = "tomato_foliar_disease_weather_risk"

OPENWEATHER_SOURCE = "https://openweathermap.org/api/forecast5"
FAO_DRAINAGE_SOURCE = "https://www.fao.org/4/r4082e/r4082e07.htm"
FAO_HEAT_SOURCE = (
    "https://www.fao.org/climate-change/news/news-detail/"
    "extreme-heat-in-an-el-ni%C3%B1o-year--how-agrifood-systems-can-prepare/en"
)
IRRI_WATER_SOURCE = (
    "https://www.knowledgebank.irri.org/step-by-step-production/growth/"
    "water-management"
)
FAO_VEGETABLE_WATER_SOURCE = "https://www.fao.org/4/s2022e/s2022e07.htm"
FAO_ONION_SOURCE = (
    "https://www.fao.org/land-water/databases-and-software/"
    "crop-information/onion/fr/"
)


def local_now_naive() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def _normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


@dataclass(frozen=True)
class MonitoringPolicy:
    key: str
    version: str
    reminder_type: str
    risk_type: str
    crop_label: str
    mode: str
    alert_title: str
    task_title: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class DiseaseRiskAssessment:
    forecast_date: date
    risk_level: str
    confidence: float
    inputs: dict[str, Any]
    reasons: tuple[str, ...]


_CROP_ALIASES = {
    "tomato": {"ca chua", "tomato"},
    "rice": {"lua", "rice", "paddy"},
    "coffee": {"ca phe", "coffee"},
    "pepper": {"ho tieu", "tieu", "pepper", "black pepper"},
    "durian": {"sau rieng", "durian"},
    "chili": {"ot", "chili", "chilli"},
    "maize": {"ngo", "bap", "maize", "corn"},
    "cassava": {"san", "khoai mi", "cassava"},
    "banana": {"chuoi", "banana"},
    "mango": {"xoai", "mango"},
    "dragon_fruit": {"thanh long", "dragon fruit"},
    "citrus": {"cam", "quyt", "buoi", "chanh", "citrus"},
}

# The registry is intentionally data-driven: every entry gets a stable policy
# version and bilingual aliases, while thresholds remain group-level weather
# watches rather than unsupported crop-disease diagnoses.
VEGETABLE_POLICY_SPECS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # Leafy vegetables
    "mustard_greens": ("cải xanh", "leafy_vegetable", ("cai xanh", "cai be xanh", "mustard greens")),
    "choy_sum": ("cải ngọt", "leafy_vegetable", ("cai ngot", "choy sum", "choi sum")),
    "bok_choy": ("cải thìa", "leafy_vegetable", ("cai thia", "cai chip", "bok choy", "pak choi")),
    "chinese_cabbage": ("cải thảo", "brassica_vegetable", ("cai thao", "chinese cabbage", "napa cabbage")),
    "cabbage": ("bắp cải", "brassica_vegetable", ("bap cai", "cabbage")),
    "lettuce": ("xà lách", "leafy_vegetable", ("xa lach", "lettuce")),
    "water_spinach": ("rau muống", "leafy_vegetable", ("rau muong", "water spinach", "morning glory")),
    "malabar_spinach": ("mồng tơi", "leafy_vegetable", ("mong toi", "malabar spinach")),
    "amaranth": ("rau dền", "leafy_vegetable", ("rau den", "amaranth greens", "amaranth")),
    "spinach": ("cải bó xôi", "leafy_vegetable", ("cai bo xoi", "rau bina", "spinach")),
    "kale": ("cải xoăn", "leafy_vegetable", ("cai xoan", "kale")),
    "watercress": ("cải xoong", "leafy_vegetable", ("cai xoong", "xa lach xoong", "watercress")),
    "chard": ("cải cầu vồng", "leafy_vegetable", ("cai cau vong", "chard", "swiss chard")),
    "chrysanthemum_greens": ("cải cúc", "leafy_vegetable", ("cai cuc", "tan o", "chrysanthemum greens")),
    "celery": ("cần tây", "leafy_vegetable", ("can tay", "celery")),
    "jute_mallow": ("rau đay", "leafy_vegetable", ("rau day", "jute mallow")),
    "katuk": ("rau ngót", "leafy_vegetable", ("rau ngot", "katuk", "sweet leaf")),
    "pennywort": ("rau má", "leafy_vegetable", ("rau ma", "pennywort", "gotu kola")),
    "purslane": ("rau sam", "leafy_vegetable", ("rau sam", "purslane")),
    # Brassicas, stems and flowers
    "broccoli": ("bông cải xanh", "brassica_vegetable", ("bong cai xanh", "sup lo xanh", "broccoli")),
    "cauliflower": ("bông cải trắng", "brassica_vegetable", ("bong cai trang", "sup lo trang", "cauliflower")),
    "kohlrabi": ("su hào", "brassica_vegetable", ("su hao", "kohlrabi")),
    "brussels_sprouts": ("cải Brussels", "brassica_vegetable", ("cai brussels", "brussels sprouts")),
    "asparagus": ("măng tây", "stem_flower_vegetable", ("mang tay", "asparagus")),
    "artichoke": ("atisô", "stem_flower_vegetable", ("atiso", "artichoke")),
    "taro_stem": ("dọc mùng", "stem_flower_vegetable", ("doc mung", "taro stem")),
    # Fruiting vegetables and cucurbits
    "eggplant": ("cà tím", "fruiting_vegetable", ("ca tim", "ca phao", "eggplant", "aubergine")),
    "bell_pepper": ("ớt chuông", "fruiting_vegetable", ("ot chuong", "bell pepper", "capsicum")),
    "okra": ("đậu bắp", "fruiting_vegetable", ("dau bap", "okra", "lady finger")),
    "cucumber": ("dưa leo", "cucurbit_vegetable", ("dua leo", "dua chuot", "cucumber")),
    "bitter_melon": ("khổ qua", "cucurbit_vegetable", ("kho qua", "muop dang", "bitter melon", "bitter gourd")),
    "pumpkin": ("bí đỏ", "cucurbit_vegetable", ("bi do", "bi ngo", "pumpkin")),
    "winter_melon": ("bí đao", "cucurbit_vegetable", ("bi dao", "bi xanh", "winter melon", "wax gourd")),
    "zucchini": ("bí ngòi", "cucurbit_vegetable", ("bi ngoi", "zucchini", "courgette")),
    "luffa": ("mướp", "cucurbit_vegetable", ("muop", "muop huong", "luffa", "loofah")),
    "bottle_gourd": ("bầu", "cucurbit_vegetable", ("bau", "bottle gourd", "calabash")),
    "chayote": ("su su", "cucurbit_vegetable", ("su su", "chayote")),
    "melon": ("dưa lưới", "cucurbit_vegetable", ("dua luoi", "melon", "cantaloupe")),
    "watermelon": ("dưa hấu", "cucurbit_vegetable", ("dua hau", "watermelon")),
    "sweet_corn": ("ngô ngọt", "fruiting_vegetable", ("ngo ngot", "bap ngot", "sweet corn")),
    # Legumes
    "yardlong_bean": ("đậu đũa", "legume_vegetable", ("dau dua", "yardlong bean", "long bean")),
    "green_bean": ("đậu cô ve", "legume_vegetable", ("dau co ve", "dau que", "green bean", "string bean")),
    "pea": ("đậu Hà Lan", "legume_vegetable", ("dau ha lan", "pea", "green pea")),
    "soybean": ("đậu nành", "legume_vegetable", ("dau nanh", "dau tuong", "soybean")),
    "mung_bean": ("đậu xanh", "legume_vegetable", ("dau xanh", "mung bean")),
    "peanut": ("đậu phộng", "legume_vegetable", ("dau phong", "lac", "peanut", "groundnut")),
    "winged_bean": ("đậu rồng", "legume_vegetable", ("dau rong", "winged bean")),
    # Roots, tubers and alliums
    "carrot": ("cà rốt", "root_vegetable", ("ca rot", "carrot")),
    "radish": ("củ cải trắng", "root_vegetable", ("cu cai", "cu cai trang", "radish", "daikon")),
    "turnip": ("củ cải tròn", "root_vegetable", ("cu cai tron", "turnip")),
    "beetroot": ("củ dền", "root_vegetable", ("cu den", "beet", "beetroot")),
    "potato": ("khoai tây", "tuber_vegetable", ("khoai tay", "potato")),
    "sweet_potato": ("khoai lang", "tuber_vegetable", ("khoai lang", "sweet potato")),
    "taro": ("khoai môn", "tuber_vegetable", ("khoai mon", "khoai so", "taro")),
    "yam": ("khoai từ", "tuber_vegetable", ("khoai tu", "khoai mo", "yam")),
    "jicama": ("củ đậu", "root_vegetable", ("cu dau", "cu san", "jicama")),
    "lotus_root": ("củ sen", "root_vegetable", ("cu sen", "ngo sen", "lotus root")),
    "onion": ("hành tây", "allium_vegetable", ("hanh tay", "onion")),
    "shallot": ("hành tím", "allium_vegetable", ("hanh tim", "shallot")),
    "garlic": ("tỏi", "allium_vegetable", ("toi", "garlic")),
    "spring_onion": ("hành lá", "allium_vegetable", ("hanh la", "spring onion", "green onion", "scallion")),
    "leek": ("tỏi tây", "allium_vegetable", ("toi tay", "leek")),
    "chives": ("hẹ", "allium_vegetable", ("he", "chives")),
    # Culinary herbs and rhizomes
    "coriander": ("rau mùi", "herb_vegetable", ("rau mui", "ngo ri", "coriander", "cilantro")),
    "basil": ("húng quế", "herb_vegetable", ("hung que", "basil")),
    "mint": ("húng lủi", "herb_vegetable", ("hung lui", "mint")),
    "perilla": ("tía tô", "herb_vegetable", ("tia to", "perilla")),
    "vietnamese_coriander": ("rau răm", "herb_vegetable", ("rau ram", "vietnamese coriander")),
    "dill": ("thì là", "herb_vegetable", ("thi la", "dill")),
    "lemongrass": ("sả", "herb_vegetable", ("sa", "lemongrass")),
    "parsley": ("ngò tây", "herb_vegetable", ("ngo tay", "parsley")),
    "marjoram": ("kinh giới", "herb_vegetable", ("kinh gioi", "vietnamese balm")),
    "culantro": ("ngò gai", "herb_vegetable", ("ngo gai", "mui tau", "culantro")),
    "fish_mint": ("diếp cá", "herb_vegetable", ("diep ca", "fish mint")),
    "wild_betel": ("lá lốt", "herb_vegetable", ("la lot", "wild betel")),
    "ginger": ("gừng", "rhizome_vegetable", ("gung", "ginger")),
    "turmeric": ("nghệ", "rhizome_vegetable", ("nghe", "turmeric")),
    "galangal": ("riềng", "rhizome_vegetable", ("rieng", "galangal")),
}

for _key, (_, _, _aliases) in VEGETABLE_POLICY_SPECS.items():
    _CROP_ALIASES[_key] = set(_aliases)


VEGETABLE_MODES = {
    "leafy_vegetable",
    "brassica_vegetable",
    "stem_flower_vegetable",
    "fruiting_vegetable",
    "cucurbit_vegetable",
    "legume_vegetable",
    "root_vegetable",
    "tuber_vegetable",
    "allium_vegetable",
    "herb_vegetable",
    "rhizome_vegetable",
}
SUPPORTED_VEGETABLE_POLICY_KEYS = frozenset(
    {"tomato", "chili", *VEGETABLE_POLICY_SPECS}
)
MOISTURE_WATCH_MODES = {"moisture", "rice", *VEGETABLE_MODES}
HEAT_WATCH_MODES = {"heat_and_moisture", "weather", *VEGETABLE_MODES}


def _policy(
    key: str,
    crop_label: str,
    mode: str,
    *,
    version: str | None = None,
    reminder_type: str | None = None,
    risk_type: str | None = None,
) -> MonitoringPolicy:
    sources = [
        OPENWEATHER_SOURCE,
        IRRI_WATER_SOURCE if mode == "rice" else FAO_DRAINAGE_SOURCE,
    ]
    if mode in HEAT_WATCH_MODES:
        sources.append(FAO_HEAT_SOURCE)
    if mode in VEGETABLE_MODES:
        sources.append(FAO_VEGETABLE_WATER_SOURCE)
    if mode == "allium_vegetable":
        sources.append(FAO_ONION_SOURCE)
    return MonitoringPolicy(
        key=key,
        version=version or f"{key}-weather-watch-v1",
        reminder_type=reminder_type or f"{key}_weather_watch",
        risk_type=risk_type or f"{key}_weather_stress_risk",
        crop_label=crop_label,
        mode=mode,
        alert_title=f"Cần kiểm tra {crop_label} do điều kiện thời tiết",
        task_title=f"Kiểm tra {crop_label} tại ruộng",
        sources=tuple(dict.fromkeys(sources)),
    )


POLICIES = {
    "tomato": _policy(
        "tomato",
        "cà chua",
        "fruiting_vegetable",
        version=POLICY_VERSION,
        reminder_type=REMINDER_TYPE,
        risk_type=RISK_TYPE,
    ),
    "rice": _policy("rice", "lúa", "rice"),
    "coffee": _policy("coffee", "cà phê", "heat_and_moisture"),
    "pepper": _policy("pepper", "hồ tiêu", "moisture"),
    "durian": _policy("durian", "sầu riêng", "moisture"),
    "chili": _policy("chili", "ớt", "fruiting_vegetable"),
    "maize": _policy("maize", "ngô", "heat_and_moisture"),
    "cassava": _policy("cassava", "sắn", "weather"),
    "banana": _policy("banana", "chuối", "weather"),
    "mango": _policy("mango", "xoài", "weather"),
    "dragon_fruit": _policy("dragon_fruit", "thanh long", "weather"),
    "citrus": _policy("citrus", "cây có múi", "weather"),
}

for _key, (_label, _mode, _) in VEGETABLE_POLICY_SPECS.items():
    POLICIES[_key] = _policy(_key, _label, _mode)


def resolve_monitoring_policy(crop: str | None) -> MonitoringPolicy:
    normalized = _normalized(crop or "").strip()
    for key, aliases in _CROP_ALIASES.items():
        if normalized in aliases:
            return POLICIES[key]
    label = (crop or "cây trồng").strip() or "cây trồng"
    return _policy("generic", label, "weather")


def is_supported_crop(crop: str | None) -> bool:
    """Every named crop gets a safe generic weather-watch fallback."""
    return bool(crop and crop.strip())


def is_supported_region(province: str | None) -> bool:
    """Accept all 34 current province-level units in Vietnam."""
    return is_vietnam_province(province)


def assess_weather_risk(
    policy: MonitoringPolicy, day: dict[str, Any]
) -> DiseaseRiskAssessment:
    """Assess weather stress only; this does not diagnose crop disease."""
    forecast_date = date.fromisoformat(str(day["date"]))
    rain_probability = _optional_float(day.get("rain_probability"))
    rain_mm = _optional_float(day.get("rain_mm"))
    humidity = _optional_float(day.get("humidity_max", day.get("humidity")))
    temp = _optional_float(day.get("temp"))
    temp_max = _optional_float(day.get("temp_max", temp))

    rain_probability_value = min(max(rain_probability or 0.0, 0.0), 1.0)
    rain_mm_value = max(rain_mm or 0.0, 0.0)
    humidity_value = min(max(humidity or 0.0, 0.0), 100.0)
    temp_max_value = temp_max if temp_max is not None else -100.0
    reasons: list[str] = []

    heavy_rain = rain_mm_value >= 50 or rain_probability_value >= 0.85
    moisture_combo = rain_probability_value >= 0.5 and humidity_value >= 85
    extreme_heat = temp_max_value >= 38
    elevated_heat = temp_max_value >= 35

    if heavy_rain:
        risk_level = "high"
        reasons.append(
            "daily_rain_at_least_50_mm"
            if rain_mm_value >= 50
            else "rain_probability_at_least_0_85"
        )
        threshold_margin = max(
            (rain_mm_value - 50) / 50,
            rain_probability_value - 0.85,
        )
    elif policy.mode in MOISTURE_WATCH_MODES and moisture_combo:
        risk_level = "high"
        reasons.extend(
            ("rain_probability_at_least_0_5", "humidity_at_least_85")
        )
        threshold_margin = min(
            rain_probability_value - 0.5, (humidity_value - 85) / 15
        )
    elif policy.mode in HEAT_WATCH_MODES and extreme_heat:
        risk_level = "high"
        reasons.append("maximum_temperature_at_least_38_c")
        threshold_margin = (temp_max_value - 38) / 10
    elif (
        rain_mm_value >= 25
        or rain_probability_value >= 0.6
        or humidity_value >= 80
        or (
            policy.mode in HEAT_WATCH_MODES and elevated_heat
        )
    ):
        risk_level = "medium"
        if rain_mm_value >= 25:
            reasons.append("daily_rain_at_least_25_mm")
        elif rain_probability_value >= 0.6:
            reasons.append("rain_probability_at_least_0_6")
        elif humidity_value >= 80:
            reasons.append("humidity_at_least_80")
        else:
            reasons.append("maximum_temperature_at_least_35_c")
        threshold_margin = max(
            (rain_mm_value - 25) / 50,
            rain_probability_value - 0.6,
            (humidity_value - 80) / 20,
            (temp_max_value - 35) / 10 if elevated_heat else 0,
        )
    else:
        risk_level = "low"
        reasons.append("weather_watch_threshold_not_reached")
        threshold_margin = max(
            (25 - rain_mm_value) / 50,
            0.6 - rain_probability_value,
            (80 - humidity_value) / 100,
        )

    available = sum(
        value is not None
        for value in (rain_probability, rain_mm, humidity, temp_max)
    )
    confidence = compute_weather_risk_confidence(
        available_signals=available,
        total_signals=4,
        threshold_margin=threshold_margin,
    )
    return DiseaseRiskAssessment(
        forecast_date=forecast_date,
        risk_level=risk_level,
        confidence=confidence,
        inputs={
            "rain_probability": rain_probability,
            "rain_mm": rain_mm,
            "humidity": humidity,
            "temp_c": temp,
            "temp_max_c": temp_max,
            "description": day.get("description"),
            "policy_key": policy.key,
            "policy_category": policy.mode,
            "policy_sources": list(policy.sources),
        },
        reasons=tuple(reasons),
    )


def assess_tomato_weather_risk(day: dict[str, Any]) -> DiseaseRiskAssessment:
    return assess_weather_risk(POLICIES["tomato"], day)


def highest_risk_assessment(
    forecast: list[dict[str, Any]], policy: MonitoringPolicy | None = None
) -> DiseaseRiskAssessment:
    if not forecast:
        raise ValueError("weather_forecast_empty")
    active_policy = policy or POLICIES["tomato"]
    assessments = [assess_weather_risk(active_policy, day) for day in forecast]
    rank = {"low": 0, "medium": 1, "high": 2}
    return max(
        assessments,
        key=lambda item: (
            rank[item.risk_level],
            item.confidence,
            -item.forecast_date.toordinal(),
        ),
    )


def schedule_run_key(schedule_id: object, scheduled_for: datetime) -> str:
    return f"farm-monitor:{schedule_id}:{scheduled_for.isoformat(timespec='minutes')}"


def recommendation_dedupe_key(
    schedule_id: object,
    forecast_date: date,
    policy_version: str = POLICY_VERSION,
) -> str:
    return f"farm-risk:{schedule_id}:{forecast_date.isoformat()}:{policy_version}"


def prediction_expiry(now: datetime, frequency_hours: int) -> datetime:
    return now + timedelta(hours=max(6, frequency_hours))


def build_recommendation_body(
    *,
    province: str,
    assessment: DiseaseRiskAssessment,
    policy: MonitoringPolicy | None = None,
) -> str:
    active_policy = policy or POLICIES["tomato"]
    rain_probability = assessment.inputs.get("rain_probability")
    rain_mm = assessment.inputs.get("rain_mm")
    humidity = assessment.inputs.get("humidity")
    temp_max = assessment.inputs.get("temp_max_c")
    signals = []
    if rain_probability is not None:
        signals.append(f"khả năng mưa {round(float(rain_probability) * 100)}%")
    if rain_mm is not None:
        signals.append(f"tổng mưa dự báo {round(float(rain_mm), 1)} mm")
    if humidity is not None:
        signals.append(f"độ ẩm cao nhất {round(float(humidity))}%")
    if temp_max is not None:
        signals.append(f"nhiệt độ cao nhất {round(float(temp_max), 1)}°C")
    signal_text = ", ".join(signals) or "điều kiện thời tiết đáng chú ý"
    if active_policy.mode == "rice":
        action = "Kiểm tra mực nước và khả năng thoát nước của ruộng"
    elif active_policy.mode in {"root_vegetable", "tuber_vegetable", "allium_vegetable", "rhizome_vegetable"}:
        action = "Kiểm tra độ ẩm luống, vùng rễ/củ và khả năng thoát nước"
    elif active_policy.mode in {"leafy_vegetable", "brassica_vegetable", "herb_vegetable"}:
        action = "Kiểm tra độ ẩm đất, tình trạng lá, che nắng và thoát nước"
    elif active_policy.mode in {"fruiting_vegetable", "cucurbit_vegetable", "legume_vegetable"}:
        action = "Kiểm tra tán cây, giàn/quả, độ ẩm đất và khả năng thoát nước"
    else:
        action = "Kiểm tra tình trạng cây và khả năng thoát nước tại ruộng"
    return (
        f"Dự báo tại {province} ngày {assessment.forecast_date.isoformat()} có "
        f"{signal_text}. {action}. Đây là cảnh báo điều kiện thời tiết, không "
        "phải chẩn đoán bệnh hay chỉ định sử dụng hóa chất."
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
