import re

# Read file
with open('c:/Users/Ajinkya/Desktop/MootCourt/backend/lexigraphbe/ipc.json', 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Fix 1: Replace Python booleans with JSON booleans (308 occurrences)
content = re.sub(r': True,', r': true,', content)
content = re.sub(r': False,', r': false,', content)
content = re.sub(r': True\n', r': true\n', content)
content = re.sub(r': False\n', r': false\n', content)

# Fix 2: Fix the chapter XVI structure
# Find and replace the problematic section around line 550-552
old_pattern = r'      \]\n    \}\n  \],\n    "metadata":'
new_pattern = r'      ],\n      "metadata":'
content = re.sub(old_pattern, new_pattern, content)

# Also need to move the closing brace after case_query
# Find the case_query line and the closing pattern after it
old_end = r'("case_query": "[^"]+"\n    \},)\n    \{'
new_end = r'\1\n    },\n    {'
content = re.sub(old_end, new_end, content, flags=re.DOTALL)

# Write back
with open('c:/Users/Ajinkya/Desktop/MootCourt/backend/lexigraphbe/ipc.json', 'w', encoding='utf-8') as f:
    f.write(content)

print('✓ Fixed Python booleans (True/False → true/false)')
print('✓ Fixed chapter XVI structure (moved metadata inside chapter)')
