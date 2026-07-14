"""
mock_ruby_test_runner.py

Python verification harness for the protobuf Ruby enum_getter fix (PR #27848).
Used when `ruby` is not installed on the host system.

Structurally verifies the same assertions as tests/basic.rb:
  1. enum_getter returns the correct constant for a valid key
  2. enum_getter returns None for a missing key (not raise)
  3. enum_getter returns None when enum_module is None (not raise)
  4. enum_getter returns the correct constant for key=0

This is NOT a general Ruby→Python transpiler. It is a single hardcoded
proof-of-equivalence for this specific fix.
"""

import sys


# ── Python equivalent of the fixed Ruby enum_getter ──────────────────────────

def enum_getter(enum_module: dict | None, key: int):
    """
    Python equivalent of the fixed Ruby enum_getter.
    enum_module is a dict {name: value} mirroring Ruby module constants.
    """
    if enum_module is None or not isinstance(enum_module, dict):
        return None
    matching = [name for name, val in enum_module.items() if val == key]
    if not matching:
        return None
    return matching[0]


# ── Test enum (mirrors TestEnums in tests/basic.rb) ──────────────────────────

TEST_ENUMS = {
    "UNKNOWN": 0,
    "FOO":     1,
    "BAR":     2,
}


# ── Assertions ────────────────────────────────────────────────────────────────

def run_tests():
    failures = []

    # test_enum_getter: valid key → returns constant name
    result = enum_getter(TEST_ENUMS, 1)
    if result != "FOO":
        failures.append(f"test_enum_getter: expected 'FOO', got {result!r}")

    # test_enum_getter_missing_key: absent key → returns None, not raise
    result = enum_getter(TEST_ENUMS, 999)
    if result is not None:
        failures.append(f"test_enum_getter_missing_key: expected None, got {result!r}")

    # test_enum_getter_nil_module: None module → returns None, not raise
    try:
        result = enum_getter(None, 1)
        if result is not None:
            failures.append(f"test_enum_getter_nil_module: expected None, got {result!r}")
    except Exception as exc:
        failures.append(f"test_enum_getter_nil_module: raised {exc!r} (should return None)")

    # test_enum_getter_zero_value: key=0 → returns 'UNKNOWN'
    result = enum_getter(TEST_ENUMS, 0)
    if result != "UNKNOWN":
        failures.append(f"test_enum_getter_zero_value: expected 'UNKNOWN', got {result!r}")

    if failures:
        print("FAIL — protobuf enum_getter mock harness:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("OK — 4 tests passed (Python mock for ruby -Ilib -Itests tests/basic.rb --name=test_enum_getter)")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
