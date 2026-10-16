from src.domain.coaching_fingerprints import canonical_fingerprint


def test_canonical_fingerprint_ignores_object_key_order() -> None:
    assert canonical_fingerprint({"workout": {"id": "w", "steps": [1, 2]}, "value": 2}) == \
           canonical_fingerprint({"value": 2, "workout": {"steps": [1, 2], "id": "w"}})
    assert canonical_fingerprint({"steps": [1, 2]}) != canonical_fingerprint({"steps": [2, 1]})
