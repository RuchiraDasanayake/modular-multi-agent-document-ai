from __future__ import annotations

from pathlib import Path

import scripts.build_schema_conditioned_pack as schema_pack


def test_schema_conditioned_pack_has_fixed_schema_and_sources() -> None:
    pack = schema_pack.build_pack(100)
    cases = pack["cases"]
    schema_keys = set(schema_pack.SCHEMA_KEYS)

    assert len(cases) == 100

    for case in cases:
        expected = case.get("expected")
        expected_sources = case.get("expected_sources")
        fields = case.get("fields")
        rel_path = str(case.get("path", "")).strip()

        assert isinstance(expected, dict)
        assert isinstance(expected_sources, dict)
        assert isinstance(fields, dict)
        assert set(expected.keys()) == schema_keys
        assert set(expected_sources.keys()) == schema_keys
        assert set(fields.keys()) == schema_keys
        assert rel_path
        assert (schema_pack.REPO_ROOT / Path(rel_path)).exists()

        for value in expected.values():
            assert isinstance(value, str)
            assert value.strip()
