import json

with open('lexigraphbe/ipc.json', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total chapters: {len(data.get('chapters', []))}\n")

for i, ch in enumerate(data.get('chapters', [])):
    sections = ch.get('sections', [])
    section_nums = [s.get('section_number') for s in sections]
    print(f"Chapter {i+1}: {ch.get('chapter_number')} - {ch.get('chapter_title')}")
    print(f"  Sections ({len(sections)}): {', '.join(section_nums[:10])}")
    if len(sections) > 10:
        print(f"  ... and {len(sections) - 10} more")
    print()
