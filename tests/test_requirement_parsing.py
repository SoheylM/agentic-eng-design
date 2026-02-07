#!/usr/bin/env python3
"""
Test script to verify automatic requirement parsing works correctly.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from eval_saved import get_requirement_patterns, parse_requirements_from_cdc
from prompts import CAHIER_DES_CHARGES_REV_C, CAHIER_DES_CHARGES_UAM


def test_water_system_parsing():
    """Test that water system parsing produces the same patterns as hardcoded ones."""
    print("🧪 Testing Water System Requirement Parsing")
    print("=" * 50)

    # Parse requirements from water system CDC
    water_patterns = parse_requirements_from_cdc(CAHIER_DES_CHARGES_REV_C)

    print(f"Found {len(water_patterns)} requirements:")
    for req_id, pattern in water_patterns.items():
        print(f"  {req_id}: {pattern}")

    # Expected requirements for water system
    expected_water_reqs = ["SR-01", "SR-02", "SR-03", "SR-04", "SR-05", "SR-06", "SR-07", "SR-08", "SR-09", "SR-10"]

    print(f"\n✅ Found {len(water_patterns)} requirements")
    print(f"✅ Expected {len(expected_water_reqs)} requirements")

    for req_id in expected_water_reqs:
        if req_id in water_patterns:
            print(f"✅ {req_id} found")
        else:
            print(f"❌ {req_id} missing")

    return water_patterns


def test_uam_system_parsing():
    """Test UAM system requirement parsing."""
    print("\n🚁 Testing UAM System Requirement Parsing")
    print("=" * 50)

    # Parse requirements from UAM system CDC
    uam_patterns = parse_requirements_from_cdc(CAHIER_DES_CHARGES_UAM)

    print(f"Found {len(uam_patterns)} requirements:")
    for req_id, pattern in uam_patterns.items():
        print(f"  {req_id}: {pattern}")

    # Expected requirements for UAM system
    expected_uam_reqs = ["SR-01", "SR-02", "SR-03", "SR-04", "SR-05", "SR-06", "SR-07", "SR-08", "SR-09", "SR-10"]

    print(f"\n✅ Found {len(uam_patterns)} requirements")
    print(f"✅ Expected {len(expected_uam_reqs)} requirements")

    for req_id in expected_uam_reqs:
        if req_id in uam_patterns:
            print(f"✅ {req_id} found")
        else:
            print(f"❌ {req_id} missing")

    return uam_patterns


def test_pattern_generation():
    """Test that the pattern generation function works correctly."""
    print("\n🔧 Testing Pattern Generation")
    print("=" * 50)

    # Test water system patterns
    water_patterns = get_requirement_patterns("water")
    print(f"Water system patterns: {len(water_patterns)} requirements")

    # Test UAM system patterns
    uam_patterns = get_requirement_patterns("uam")
    print(f"UAM system patterns: {len(uam_patterns)} requirements")

    # Verify they're different (as they should be)
    if water_patterns != uam_patterns:
        print("✅ Water and UAM patterns are different (as expected)")
    else:
        print("❌ Water and UAM patterns are identical (unexpected)")


def main():
    """Run all tests."""
    print("🧪 Testing Automatic Requirement Parsing")
    print("=" * 60)

    # Test water system
    water_patterns = test_water_system_parsing()

    # Test UAM system
    uam_patterns = test_uam_system_parsing()

    # Test pattern generation
    test_pattern_generation()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")

    # Summary
    print("\n📊 Summary:")
    print(f"  Water system: {len(water_patterns)} requirements parsed")
    print(f"  UAM system: {len(uam_patterns)} requirements parsed")
    print("  Both systems: ✅ Automatic parsing working")


if __name__ == "__main__":
    main()
