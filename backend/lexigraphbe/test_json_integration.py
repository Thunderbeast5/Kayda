"""
Test script to verify ipc.json integration with StatuteRepository.
"""

from statute_repository import StatuteRepository

def test_json_loading():
    """Test that ipc.json is loaded correctly."""
    print("=" * 80)
    print("Testing ipc.json Integration")
    print("=" * 80)
    
    repo = StatuteRepository.get_instance()
    
    # Test 1: Check if sections are loaded
    print("\n1. Checking loaded sections...")
    sections_db = repo.get_sections_db()
    ipc_sections = [s for s in sections_db if s.get("statute") == "IPC"]
    print(f"   Total IPC sections loaded: {len(ipc_sections)}")
    
    # Test 2: Check specific section from JSON
    print("\n2. Testing Section 21 (Public servant) from ipc.json...")
    definition = repo.get_statutory_definition("21", "IPC")
    if definition:
        print(f"   ✅ Section 21 definition found!")
        print(f"   Length: {len(definition)} characters")
        print(f"   Preview: {definition[:200]}...")
    else:
        print(f"   ❌ Section 21 NOT found in repository")
    
    # Test 3: Check statute_db structure
    print("\n3. Checking statute_db structure...")
    statute_db = repo.get_statute_db()
    if "IPC_21" in statute_db:
        sec_21 = statute_db["IPC_21"]
        print(f"   ✅ IPC_21 found in statute_db")
        print(f"   Title: {sec_21.get('section_title', 'N/A')}")
        print(f"   Chapter: {sec_21.get('chapter_title', 'N/A')}")
        print(f"   Has full_text: {'full_text' in sec_21}")
        print(f"   Has explanation: {'explanation' in sec_21}")
        print(f"   Has illustrations: {'illustrations' in sec_21}")
    else:
        print(f"   ❌ IPC_21 NOT found in statute_db")
    
    # Test 4: Test a section that should be in CSV (not in ipc.json yet)
    print("\n4. Testing Section 498A (should fallback to CSV)...")
    definition_498a = repo.get_statutory_definition("498A", "IPC")
    if definition_498a:
        print(f"   ✅ Section 498A definition found (CSV fallback)")
        print(f"   Length: {len(definition_498a)} characters")
        print(f"   Preview: {definition_498a[:200]}...")
    else:
        print(f"   ❌ Section 498A NOT found")
    
    # Test 5: List all JSON-loaded sections
    print("\n5. All sections loaded from ipc.json:")
    json_sections = [s for s in ipc_sections if "IPC_" + s["section_number"] in statute_db]
    for sec in json_sections[:10]:  # Show first 10
        sec_num = sec["section_number"]
        title = sec["title"]
        print(f"   - Section {sec_num}: {title}")
    print(f"   ... ({len(json_sections)} total)")
    
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

if __name__ == "__main__":
    test_json_loading()
