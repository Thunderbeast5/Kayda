import re

# Read file
with open('c:/Users/Ajinkya/Desktop/MootCourt/backend/lexigraphbe/ipc.json', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Check if this line closes an array with ]
    # and the next line starts a new chapter with {
    # without a closing brace and comma
    if i < len(lines) - 1:
        current_stripped = line.strip()
        next_stripped = lines[i + 1].strip()
        
        # Pattern: array closes with ] or ], and next line starts with {
        if (current_stripped in [']', '],']) and next_stripped == '{':
            # We need to add },  before the {
            # But first check if there's supposed to be a closing brace
            # Look back to see if we're inside a chapter that needs closing
            if current_stripped == ']':
                # Change it to ],
                line = line.rstrip() + ',\n'
            # Add closing brace with comma
            fixed_lines.append(line)
            fixed_lines.append('    },\n')
            i += 1
            continue
    
    fixed_lines.append(line)
    i += 1

# Write back
with open('c:/Users/Ajinkya/Desktop/MootCourt/backend/lexigraphbe/ipc.json', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('✓ Fixed all chapter boundaries')
