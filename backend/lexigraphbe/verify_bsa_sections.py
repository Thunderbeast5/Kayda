import json

with open('backend/lexigraphbe/bsa.json', 'r', encoding='utf-8') as f:
    bsa = json.load(f)

print("Document info:", bsa.get("document", {}).get("title"), "Total sections:", bsa.get("document", {}).get("total_sections"))
sections = []
for ch_idx, ch in enumerate(bsa.get('chapters', [])):
    ch_num = ch.get('chapter_number')
    for sec in ch.get('sections', []):
        sections.append((ch_num, sec.get('section_number'), sec.get('heading')))

print(f"Count of sections: {len(sections)}")
numbers = [int(s[1]) for s in sections if s[1].isdigit()]
print(f"Min section: {min(numbers)}, Max section: {max(numbers)}")
missing_nums = set(range(1, 171)) - set(numbers)
print(f"Missing section numbers in sequence 1..170: {missing_nums}")
