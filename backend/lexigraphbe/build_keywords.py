import json, re, math, collections, os
from curated import CURATED
from nltk.stem import PorterStemmer
ps = PorterStemmer()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE_DIR, 'ipc.json')
OUT = os.path.join(BASE_DIR, 'ipc_keywords.json')
STOP = set("""a an the of or and to in on at by for with from as is are was were be been being that this these those it its his her their
any such shall may not no nor than then there which who whom whoever whose when where while if into upon under over also other
section sections act code person persons case cases whether either each every all one two three four five six seven eight nine ten
said same so only also within without commits committed commit offence offences punishable punishment liable imprisonment fine extend
term description years year either both thereof therein hereby hereof deemed accused illustration explanation example""".split())

def tok(t):
    return re.findall(r"[a-z]+", t.lower())

def terms_of(text):
    return [w for w in tok(text) if w not in STOP and len(w) > 2]

d = json.load(open(SRC))
rows = []
for c in d['chapters']:
    for s in c['sections']:
        s['_chapter'] = f"{c['chapter_number']} - {c['chapter_title']}"
        s['_subheading'] = s.get('sub_heading_context') or c.get('sub_heading') or ''
        rows.append(s)
by_id = {s['section_number']: s for s in rows}

def aux_text(s):
    """Plain-language / worked-example text (NOT the bare statutory wording)."""
    parts = []
    parts.append(s.get('key_principle') or '')
    parts += [i if isinstance(i, str) else json.dumps(i) for i in (s.get('ingredients') or [])]
    for e in s.get('illustrations') or []:
        if isinstance(e, dict):
            parts += [e.get('text',''), e.get('key_principle',''), e.get('verdict') or '']
        elif isinstance(e, str):
            parts.append(e)
    for e in s.get('explanations') or []:
        if isinstance(e, dict):
            parts += [e.get('plain_language',''), e.get('text','')]
        elif isinstance(e, str):
            parts.append(e)
    parts.append(s.get('key_distinction_from_s403','') or s.get('key_distinction','') or '')
    parts.append(s.get('plain_language','') if isinstance(s.get('plain_language'), str) else '')
    return ' '.join(p for p in parts if isinstance(p, str))

# document frequency over aux text for auto-keyword selection
df = collections.Counter()
aux_terms = {}
for s in rows:
    ts = terms_of(aux_text(s))
    aux_terms[s['section_number']] = ts
    for t in set(ts): df[t] += 1
N = len(rows)

def auto_keywords(sid, k=22):
    ts = aux_terms[sid]
    if not ts: return []
    tf = collections.Counter(ts)
    scored = []
    for t, f in tf.items():
        if df[t] > N * 0.08: continue        # too common across the Code
        scored.append((f * math.log(N / df[t]), t))
    scored.sort(reverse=True)
    return [t for _, t in scored[:k]]

REF = re.compile(r"[Ss]ection (\d+[A-Z]?(?:-[A-Z])?)")
def referenced(s):
    blob = (s.get('key_principle') or '') + ' ' + (s.get('text') or '')
    return [r for r in dict.fromkeys(REF.findall(blob)) if r in by_id and r != s['section_number']]

GENERIC = {str(i) for i in range(1, 53)} | {'Preamble'}   # Ch. I-II definitions, interpretation clauses
GENERIC |= {'29A','52A'}

out = []
for s in rows:
    sid = s['section_number']
    entry = {
        "section": sid,
        "heading": s['heading'],
        "chapter": s['_chapter'],
        "sub_heading": s['_subheading'],
        "section_type": s['section_type'],
        "status": "omitted" if s['is_omitted'] else "repealed" if s['is_repealed'] else "active",
        "layman_keywords": [k.strip() for k in CURATED.get(sid, '').split(';') if k.strip()],
        "auto_keywords": auto_keywords(sid),
        "related_sections": [],
        "retrieval_prior": 0.45 if sid in GENERIC else 1.0,
        "curated": sid in CURATED and bool(CURATED[sid]),
    }
    # punishment sections inherit vocabulary from the definition they punish
    if s['section_type'] in ('punishment', 'combined'):
        refs = referenced(s)
        entry['related_sections'] = refs[:3]
    out.append(entry)

# inheritance pass
idx = {e['section']: e for e in out}
for e in out:
    for r in e['related_sections']:
        e['layman_keywords'] += [k for k in idx[r]['layman_keywords'] if k not in e['layman_keywords']][:8]

json.dump({"description": "Keyword index for IPC retrieval. layman_keywords = hand-curated fact-pattern vocabulary; auto_keywords = TF-IDF terms mined from key_principle / ingredients / illustrations / plain_language; retrieval_prior down-weights generic definition sections.",
           "n_sections": len(out), "n_curated": sum(e['curated'] for e in out), "sections": out},
          open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print(len(out), 'sections;', sum(e['curated'] for e in out), 'curated;', sum(1 for e in out if e['auto_keywords']), 'with auto keywords')
print(json.dumps(idx['405'], indent=1)[:1800])
