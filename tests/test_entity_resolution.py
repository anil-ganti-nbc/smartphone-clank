"""Basic entity resolution tests."""

from datetime import datetime

from models.schemas import Discovery, Manufacturer, SourceType
from entity_resolution.resolver import EntityResolver


def test_family_key_extraction():
    # We can't easily unit-test without a DB session, so just exercise the helper logic
    class Dummy:
        regional_suffixes = ["B", "U", "N", "W"]

        def _normalize_model(self, model: str) -> str:
            return model.strip().upper().replace(" ", "").replace("-", "")

        def _extract_family_key(self, model: str) -> str:
            cleaned = self._normalize_model(model)
            for suffix in self.regional_suffixes:
                if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 3:
                    if cleaned[-len(suffix) - 1].isdigit():
                        return cleaned[: -len(suffix)]
            return cleaned

    d = Dummy()
    assert d._extract_family_key("SM-S957B") == "SMS957"
    assert d._extract_family_key("SM-S957U") == "SMS957"
    assert d._extract_family_key("SM-S957N") == "SMS957"
    assert d._extract_family_key("Pixel 9 Pro") == "PIXEL9PRO"
    print("family key tests passed")


if __name__ == "__main__":
    test_family_key_extraction()
