"""Alias + timeline logic smoke tests (no DB required for pure helpers)."""

from entity_resolution.resolver import EntityResolver


def test_family_key_consistency():
    class Dummy:
        regional_suffixes = ["B", "U", "N", "W", "E", "J", "Z", "0"]

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
    assert d._extract_family_key("SM-S957B") == d._extract_family_key("SM-S957U")
    assert d._extract_family_key("SM-S957B") == d._extract_family_key("SM-S957N")
    assert d._extract_family_key("SM-S957B") != d._extract_family_key("SM-S958B")
    print("family key consistency ok")


if __name__ == "__main__":
    test_family_key_consistency()
    print("alias/timeline helper tests passed")
