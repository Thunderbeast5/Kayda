"""
Debug script to show the actual IPC heading reference that Stage 1 LLM sees.
"""
from lexigraphbe.query_understanding_agent import _build_ipc_heading_reference

# Build the reference exactly as Stage 1 does (with no statute_db)
ipc_ref = _build_ipc_heading_reference(statute_db=None)

print("="*80)
print("IPC HEADING REFERENCE SENT TO STAGE 1 LLM")
print("="*80)
print(ipc_ref)
print("="*80)

# Check if 304A is present
if "304A" in ipc_ref:
    print("\n✅ Section 304A IS present in the reference")
    # Extract the 304A line
    for line in ipc_ref.split('\n'):
        if "304A" in line:
            print(f"   {line.strip()}")
else:
    print("\n❌ Section 304A is MISSING from the reference")

# Check if 269 is present
if "269" in ipc_ref:
    print("\n✅ Section 269 IS present in the reference")
    for line in ipc_ref.split('\n'):
        if "269:" in line:  # Use colon to avoid matching 2069
            print(f"   {line.strip()}")
else:
    print("\n❌ Section 269 is MISSING from the reference")

print("\n" + "="*80)
print(f"Total lines in reference: {len(ipc_ref.split(chr(10)))}")
print("="*80)
