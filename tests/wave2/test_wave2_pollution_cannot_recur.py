"""
Wave 2 pollution regression — release-blocking, permanent.

Proves every Wave 2 validator (collectors/wave2/<oem>/model_validator.py)
rejects a hostile corpus (promotional sentences, navigation labels,
accessories, earbuds, watches, tablets, laptops, chargers, cases, bundles,
trade-in offers, financing text, SEO headings, legal/footer text) while
still accepting genuine phone model names for that OEM.

Same shape as tests/wave1/test_pollution_cannot_recur.py — this is that
file's Wave 2 counterpart, not a replacement.

Special cases called out by the Wave 2 mission:
  - ASUS must reject PC hardware (laptops/motherboards/GPUs/monitors/routers).
  - Vivo must not silently treat iQOO identity as Vivo.
  - Motorola must reject accessories and Lenovo PC products.
  - Oppo/Realme must reject promotional/SEO copy.
  - Honor must reject laptops/tablets/wearables.
"""

from __future__ import annotations

from collectors.wave1.validator import VALID
from collectors.wave2.asus.model_validator import validate as validate_asus
from collectors.wave2.honor.model_validator import validate as validate_honor
from collectors.wave2.motorola.model_validator import validate as validate_motorola
from collectors.wave2.oppo.model_validator import validate as validate_oppo
from collectors.wave2.realme.model_validator import validate as validate_realme
from collectors.wave2.vivo.model_validator import validate as validate_vivo

VALIDATORS = {
    "motorola": validate_motorola,
    "honor": validate_honor,
    "oppo": validate_oppo,
    "vivo": validate_vivo,
    "realme": validate_realme,
    "asus": validate_asus,
}

# Shared hostile shapes every OEM validator must reject regardless of brand
# vocabulary — navigation chrome, cookie banners, promo copy, financing
# text, generic bundles/cases/chargers, and obviously-not-a-phone strings.
_SHARED_HOSTILE = [
    "Skip to main content",
    "Shop the collection",
    "Compare all accessories",
    "We use cookies to enhance your experience",
    "By continuing to browse this site you agree to our use of cookies",
    "Sign up for our newsletter and save 10%",
    "Trade in your current phone and receive an instant discount",
    "0% APR financing available on select accessories",
    "Free case with every purchase, while supplies last",
    "65W fast charger sold separately",
    "Silicone case with MagSafe compatibility",
    "Learn more",
    "Buy now",
    "",
    "x" * 60,  # too long
]

# OEM-specific hostile corpora, covering the mission's named special cases.
_HOSTILE = {
    "motorola": _SHARED_HOSTILE + [
        "Motorola Edge Charger 68W TurboPower",
        "Moto Buds+ wireless earbuds",
        "Moto Watch 100",
        "Moto Tab G70",
        "ThinkPad X1 Carbon",          # Lenovo PC product, not a phone
        "Lenovo Yoga 9i 2-in-1 laptop",
        "Motorola Edge silicone case",
        "Moto",
    ],
    "honor": _SHARED_HOSTILE + [
        "Honor MagicBook Art 14",       # laptop
        "Honor Pad 9",                  # tablet
        "Honor Watch GS 5",             # wearable
        "Honor Choice Earbuds X5",      # audio
        "Honor Router 3",
        "Honor",
    ],
    "oppo": _SHARED_HOSTILE + [
        "Experience blazing-fast charging with OPPO SuperVOOC",
        "OPPO Enco Air4 earbuds",
        "OPPO Pad 3",
        "OPPO Watch X2",
        "OPPO SuperVOOC charger 80W",
        "Find",
        "Reno",
        "A",
    ],
    "vivo": _SHARED_HOSTILE + [
        "iQOO 13",                       # separate brand/domain, not Vivo
        "iQOO Neo 10",
        "vivo Pad 3",
        "vivo TWS 3",
        "vivo Watch 3",
        "V",
        "X",
    ],
    "realme": _SHARED_HOSTILE + [
        "realme Buds Air 6",
        "realme Pad 2",
        "realme Watch 3",
        "The all-new realme experience is designed so you can focus on every single day",
        "realme power bank 20000mAh",
        "realme",
    ],
    "asus": _SHARED_HOSTILE + [
        "ASUS ROG Strix G16 gaming laptop",
        "ASUS Crosshair X870E motherboard",
        "ASUS GeForce RTX 4080 graphics card",
        "ASUS ProArt Display monitor",
        "ASUS ZenWiFi router",
        "ASUS VivoBook 15",
        "ASUS TUF Gaming keyboard",
        "Zenfone",
        "ROG Phone",
    ],
}

# Genuine phone model names each validator must still accept — a validator
# that rejects these too would be useless, not safe (same principle as
# tests/wave1/test_pollution_cannot_recur.py's KNOWN_GOOD set).
_VALID_EXAMPLES = {
    "motorola": ["Razr", "Razr Plus 2026", "Edge 2026", "Moto G Power 2026", "Moto G Stylus 5G Gen 4"],
    "honor": ["Honor Magic V6", "Honor Magic8 Pro", "Honor 600", "Honor 600 Pro"],
    "oppo": ["Find X9 Ultra", "Find N6", "Reno16 Pro", "A6 Pro 5G"],
    "vivo": ["V21", "X80 Pro", "X100 Ultra", "Y72"],
    "realme": ["realme 16 5G", "realme 16 Pro 5G", "realme 16 Pro Plus 5G", "realme GT7"],
    "asus": ["Zenfone 12 Ultra", "Zenfone 9", "ROG Phone 9", "ROG Phone 9 Pro"],
}


def test_hostile_corpus_rejected_by_every_wave2_validator():
    accepted = []
    total_rejections = 0
    for oem, validate in VALIDATORS.items():
        for text in _HOSTILE[oem]:
            outcome = validate(text)
            if outcome.outcome == VALID:
                accepted.append((oem, text))
            else:
                total_rejections += 1
                assert outcome.reason, f"{oem} rejected {text!r} without a reason"

    assert accepted == [], f"hostile candidates were accepted as VALID: {accepted}"
    assert total_rejections > 0


def test_genuine_models_still_validate_for_every_wave2_oem():
    unexpectedly_rejected = []
    for oem, validate in VALIDATORS.items():
        for text in _VALID_EXAMPLES[oem]:
            outcome = validate(text)
            if outcome.outcome != VALID:
                unexpectedly_rejected.append((oem, text, outcome.reason))

    assert unexpectedly_rejected == [], (
        f"genuine phone model names were rejected — validator too strict: {unexpectedly_rejected}"
    )


def test_asus_rejects_pc_hardware_specifically():
    from collectors.wave1.validator import REASON_PC_HARDWARE

    pc_hardware = [
        "ASUS ROG Strix G16 gaming laptop",
        "ASUS Crosshair X870E motherboard",
        "ASUS GeForce RTX 4080 graphics card",
        "ASUS ProArt Display monitor",
        "ASUS ZenWiFi router",
    ]
    for text in pc_hardware:
        outcome = validate_asus(text)
        assert outcome.outcome != VALID
        assert outcome.reason == REASON_PC_HARDWARE, f"{text!r} should be rejected as PC hardware, got {outcome.reason}"


def test_vivo_never_treats_iqoo_as_vivo_identity():
    for text in ["iQOO 13", "iQOO Neo 10", "iqoo z9"]:
        outcome = validate_vivo(text)
        assert outcome.outcome != VALID
        assert outcome.reason == "iqoo_not_vivo"


def test_motorola_rejects_lenovo_pc_products():
    for text in ["ThinkPad X1 Carbon", "Lenovo Yoga 9i 2-in-1 laptop"]:
        outcome = validate_motorola(text)
        assert outcome.outcome != VALID
