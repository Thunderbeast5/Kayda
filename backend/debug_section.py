"""Explain why a section is (not) retrieved.  Usage:  python debug_section.py 304A "causing death by medical negligence"
Run from backend\ (same folder as run_prefilter_demo.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))
import lexigraphbe.classifier_prefilter as cp

sec = sys.argv[1].upper()
query = sys.argv[2] if len(sys.argv) > 2 else "causing death by medical negligence failure to provide care"
pf = cp.StatuteClassifierPrefilter()
recs = [r for r in pf.sections_db if r["section_number"].upper() == sec and r["statute"] == "IPC"]
print(f"records matching {sec}: {len(recs)}")
if not recs:
    print("-> section is NOT in sections_db at all (check ipc.json id / section_number format)")
    print("sample section_numbers:", [r['section_number'] for r in pf.sections_db[:15]])
    sys.exit()
rec = recs[0]
print({k: (str(v)[:120]) for k, v in rec.items()})
print("non-offence filtered:", pf._is_non_offence_section(rec))
print("fatal-disqualified  :", pf.evaluate_fatal_disqualification(rec["section_number"].upper(), "IPC", query)[:2])
toks = cp._tokenize(query)
w = {t: 1.0 for t in toks}
print("query tokens:", toks)
bm = pf._get_bm25()
idx = pf.sections_db.index(rec)
raw, matched, mass = bm.score(idx, w)
print(f"this section: raw={raw:.3f} matched={matched} coverage={mass/bm.total_mass(w):.2f}")
ranked = pf._rank(w, "IPC", query)
pos = [i for i, r in enumerate(ranked) if r[0] is rec]
print("rank in this query:", (pos[0] + 1) if pos else "NOT RANKED (filtered by coverage/relative floor)")
print("top 8 for this query:")
for r, s, m, c in ranked[:8]:
    print(f"  {r['section_number']:<6} {s:<5} cov={c} {m}  {r['title'][:60]}")