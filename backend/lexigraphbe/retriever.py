import json, re, os
from rank_bm25 import BM25Okapi
from nltk.stem import PorterStemmer
ps = PorterStemmer()
STOP = set("a an the of or and to in on at by for with from as is are was were be been that this it its his her their my me our i he she they him them when then after before without not no did do does has have had into up out".split())

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def toks(t): return [ps.stem(w) for w in re.findall(r"[a-z]+", t.lower()) if w not in STOP]

class Retriever:
    def __init__(self, ipc=None, kw=None):
        ipc = ipc or os.path.join(BASE_DIR, 'ipc.json')
        kw = kw or os.path.join(BASE_DIR, 'ipc_keywords.json')
        d = json.load(open(ipc, encoding='utf-8'))
        self.secs = []
        for c in d['chapters']:
            chap_num = c.get('chapter_number', '')
            chap_title = c.get('chapter_title', '')
            chap_str = f"Chapter {chap_num} - {chap_title}" if chap_num else chap_title
            for s in c['sections']:
                if not (s['is_omitted'] or s['is_repealed']):
                    s['_chapter'] = chap_str
                    self.secs.append(s)
        K = {e['section']: e for e in json.load(open(kw, encoding='utf-8'))['sections']}
        self.K = K
        self.ids = [s['section_number'] for s in self.secs]
        text = lambda s: ' '.join([s['heading'], s.get('text') or ''])
        self.bm_text = BM25Okapi([toks(text(s)) for s in self.secs])
        kwdoc = lambda s: ' '.join([s['heading']] + K[s['section_number']]['layman_keywords'] * 2 + K[s['section_number']]['auto_keywords'])
        self.bm_kw = BM25Okapi([toks(kwdoc(s)) for s in self.secs])
        # phrase sets for exact multi-word matches
        self.phr = {sid: [tuple(toks(p)) for p in K[sid]['layman_keywords'] if len(toks(p)) >= 2] for sid in self.ids}

    @staticmethod
    def _norm(x):
        m = max(x) or 1
        return [v / m for v in x]

    def _phrase_bonus(self, q, sid):
        qt = toks(q); n = 0
        for ph in self.phr[sid]:
            L = len(ph)
            # match if all stems of the phrase appear in a window of L+2 query tokens (order-insensitive, tolerant)
            for i in range(len(qt)):
                w = qt[i:i + L + 2]
                if all(p in w for p in ph): n += 1; break
        return n

    def search(self, q, mode='hybrid', k=10, w_text=0.3, w_phr=0.12):
        qt = toks(q)
        t = self._norm(self.bm_text.get_scores(qt))
        if mode == 'text':
            sc = t
        else:
            kw = self._norm(self.bm_kw.get_scores(qt))
            sc = [kw[i] + w_text * t[i] + w_phr * min(self._phrase_bonus(q, self.ids[i]), 4) for i in range(len(self.ids))]
            sc = [sc[i] * self.K[self.ids[i]]['retrieval_prior'] for i in range(len(sc))]
        order = sorted(range(len(sc)), key=lambda i: -sc[i])[:k]
        return [(self.ids[i], self.secs[i]['heading'], round(sc[i], 3)) for i in order]

    def retrieve_top_k(self, q, k=20, mode='hybrid'):
        hits = self.search(q, mode=mode, k=k)
        if not hits:
            return []
        top_score = hits[0][2] if hits and hits[0][2] > 0 else 1.0
        out = []
        for sid, heading, score in hits:
            idx = self.ids.index(sid)
            sec = self.secs[idx]
            out.append({
                "section_number": sid,
                "section_title": heading,
                "chapter": sec.get("_chapter", ""),
                "statute": "IPC",
                "raw_score": float(score),
                "score": round(min(1.0, float(score) / top_score), 4),
                "ingredients": sec.get("ingredients") or [],
                "text": sec.get("text") or "",
            })
        return out


_RETRIEVER_INSTANCE = None


def get_retriever(ipc=None, kw=None):
    global _RETRIEVER_INSTANCE
    if _RETRIEVER_INSTANCE is None:
        _RETRIEVER_INSTANCE = Retriever(ipc=ipc, kw=kw)
    return _RETRIEVER_INSTANCE


EVAL = [  # (query, gold sections - any acceptable)
 ("My business partner secretly took 5 Lakh Rupees from our official joint company bank account without telling me, transferred it to his personal wallet, and then blocked my phone number when I asked about it.", {"405","406","408","409","403"}),
 ("My husband and in-laws keep harassing me for dowry and beat me", {"498A"}),
 ("Someone stole my mobile phone from my pocket in a crowded bus", {"378","379"}),
 ("A man threatened to leak my private photos unless I paid him money", {"384","383","503","506"}),
 ("I paid a builder for a flat but he took the money and never delivered, the documents were fake", {"420","415","417","467","468"}),
 ("Driver was speeding and hit a pedestrian who died on the spot", {"304A","279","337","338"}),
 ("My neighbour entered my house at night while we were asleep and stole jewellery", {"457","454","380","458","451"}),
 ("An employee of our shop took cash from the till over several months", {"381","408","403"}),
 ("A mob armed with swords attacked our locality during a communal clash", {"148","147","149","153A"}),
 ("He kept following me and sending messages even after I refused", {"354D","509","354A"}),
 ("Someone made a fake signature on my property sale deed", {"467","465","464","468","471"}),
 ("Police officer demanded a bribe to register my complaint", {"161","166A","165"}),
 ("They kidnapped my minor daughter and demanded ransom", {"363","364A","361"}),
 ("A person posted false allegations on social media damaging my reputation", {"499","500"}),
 ("The accused beat my brother with an iron rod and broke his arm", {"325","326","324","323","320"}),
 ("He married again without divorcing his first wife", {"494","495"}),
 ("The shopkeeper sold adulterated milk", {"272","273"}),
 ("She was found dead in her in-laws' house within a year of marriage, they had demanded dowry", {"304B","498A"}),
 ("A friend tried to stab me with a knife but missed", {"307","324"}),
 ("Someone pretended to be a bank officer and took my OTP and emptied my account", {"419","420","415"}),
 ("The company director diverted investors' funds to his own accounts", {"409","405","406","420"}),
 ("My landlord locked me in the room and would not let me leave", {"342","340","341"}),
]

if __name__ == '__main__':
    R = Retriever()
    def hit(res, gold, k): return any(r[0] in gold for r in res[:k])
    def rr(res, gold):
        for i, r in enumerate(res, 1):
            if r[0] in gold: return 1 / i
        return 0
    for mode in ('text', 'hybrid'):
        h1 = h5 = h10 = mrr = 0
        for q, g in EVAL:
            res = R.search(q, mode, k=50)
            h1 += hit(res, g, 1); h5 += hit(res, g, 5); h10 += hit(res, g, 10); mrr += rr(res, g)
        n = len(EVAL)
        print(f"{mode:7s} hit@1={h1/n:.2f} hit@5={h5/n:.2f} hit@10={h10/n:.2f} MRR={mrr/n:.2f}")
    print("\nYour query, hybrid top 10:")
    for r in R.search(EVAL[0][0], 'hybrid', 10): print(r)
    print("\nMisses (hybrid, top10):")
    for q, g in EVAL:
        res = R.search(q, 'hybrid', 10)
        if not hit(res, g, 10): print('-', q[:70], '->', [r[0] for r in res[:5]])
