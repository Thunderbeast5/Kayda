import os
import re

rep_map = {
    "EFEBE9": "surface-court",
    "FAF9F6": "surface-court",
    "FBFBFA": "surface-court",
    "FCFBF8": "surface-paperLight",
    "FAF7F2": "surface-paperMain",
    "f0f0f0": "surface-border",
    "EBE7E0": "surface-border",
    "dcdcdc": "surface-border",
    "D7CCC8": "surface-border",
    "6D4C41": "wood-light",
    "4E342E": "wood-light",
    "3E2723": "wood-dark",
    "2E1A17": "wood-deep",
    "5D4037": "primaryBrown",
    "C5A059": "gold",
    "D32F2F": "semantic-danger",
    "B71C1C": "semantic-dangerDark",
    "8B0000": "semantic-criticalText",
    "E3F2FD": "semantic-infoBg",
    "90CAF9": "semantic-infoBorder",
    "0D47A1": "semantic-infoText",
    "1E88E5": "semantic-infoAccent",
    "212121": "textPrimary",
    "757575": "textMuted",
    "FFFFFF": "surface-white",
    "1565C0": "semantic-infoText",
    "bbdefb": "semantic-infoBorder",
    "64B5F6": "semantic-infoAccent",
    "e0e0e0": "surface-border",
    "FAEED1": "surface-paperMain",
    "FAFAFA": "surface-court",
    "BBDEFB": "semantic-infoBorder",
    "C62828": "semantic-dangerDark",
    "b08d4b": "gold",
    "8D6E63": "textMuted",
    "ccc": "surface-border",
    "FCEBA6": "surface-paperMain"
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    for h, v in rep_map.items():
        # Match class prefixes ignoring case on hex
        pattern = re.compile(rf"(bg|text|border|fill|ring|decoration|from|via|to)-\[#{h}\]", re.IGNORECASE)
        content = pattern.sub(rf"\1-{v}", content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('src'):
    for file in files:
        if file.endswith('.jsx'):
            process_file(os.path.join(root, file))
