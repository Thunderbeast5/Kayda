# Virtual Moot Court — Lexi Graph Agent

**Final Year Project · Problem framing & approach notes**

## Problem Statement

The project is a **virtual moot court / trial court** with role agents (Prosecutor, Defense, Judge). Scope is limited to **anticipatory bail matters** (S.438 CrPC / S.482 BNSS).

The **Lexi Graph Agent** is the legal-retrieval component: given the case facts and the **side it is serving**, it must retrieve the sections, acts, and precedents that agent needs to support its arguments.

Running example:

> *"A man threatened his wife for dowry. The wife has registered an FIR. The accused seeks anticipatory bail."*
>
> The **Prosecutor agent** must argue why anticipatory bail should be **denied** — and needs Lexi to supply: offence sections (S.498A IPC, S.3/4 Dowry Prohibition Act, S.506), bail-law factors (S.438 considerations: gravity, tampering risk, custodial interrogation for recovery of stridhan), and precedents where AB was refused on similar facts.

Second example (from our corpus — *Dilip Singh v. State of M.P.*, LAWS(SC)-2021-1-41):

> Facts: complainant paid Rs 41 lakhs for agricultural land; accused never executed the sale deed; HC granted anticipatory bail conditioned on depositing Rs 41 lakhs.
>
> - Prosecution angle: S.420 (cheating), S.406 (criminal breach of trust)
> - Defense angle: "dispute is civil in nature" — criminal color given to money recovery; SC deleted the deposit condition, holding a bail court is not a recovery agent.

---

## Why naive statute embedding fails

We first tried embedding IPC section texts in a vector DB and querying with appeal facts. This underperforms because **statutes and fact narratives live in different vocabularies**:

- Statute: *"whoever cheats and thereby dishonestly induces the person deceived to deliver any property…"*
- Facts: *"paid Rs 41 lakhs for land, seller never executed the sale deed"*

Cosine similarity between these is near-noise. Mapping facts → offence is **legal reasoning**, not semantic similarity. This is a known failure mode in legal statute retrieval (see AILA / LegalEval statute-identification tasks).

---

## Reframing: this is multi-label classification, not open retrieval

- IPC has only ~511 sections; in bail matters, **~50–80 recur** (420, 406, 498A, 376, 307, 302, 34, 120B, …). Small, closed label space.
- We have (or can mine) a corpus of structured judgments — each with facts (`numbered_paragraphs`), labels (`ipc_sections_mentioned`, `act_sections`), outcomes (`bail_outcome`), and reasoning (`ratio_decidendi`). That's a **supervised dataset for free**.

### Baselines to build first (in order)

| # | Baseline | What it is | Why |
|---|----------|------------|-----|
| 0 | **Regex extraction** | Pull sections already cited in the appeal/FIR text | Appeals usually cite the charged sections. This tells us the real value-add is finding *additional* sections + arguments, not restating the FIR. |
| 1 | **TF-IDF + one-vs-rest logistic regression** | Classic multi-label classifier: facts → sections | ~Weekend of work; strong baseline that will likely beat naive vector search. |
| 2 | **LLM brute force** | Loop over all candidate sections: *"Given these facts, is S.X attracted? For which side?"* | O(N) calls but N is small. Expensive and dumb, but it's the **ceiling check** — if this doesn't work, no clever pipeline will. |

---

## Where the LLM actually belongs

Not as the matcher — as the shell around a grounded core:

1. **Fact structuring** — appeal text is messy; LLM extracts structured facts (parties, transaction, allegation, amounts, relationship, prior history).
2. **Query rewriting (HyDE-style)** — LLM converts facts into statute-flavored language (*"dishonest inducement to deliver property"*) **before** embedding. This alone may rescue the vector-DB approach.
3. **Ingredient verification** — for each candidate section, check statutory ingredients against the facts (mens rea? delivery of property? entrustment?). Gives **explainability** — important for evaluation and the viva.
4. **Dual-perspective argument generation** — defense vs prosecution framing is pure generation:
   - Defense: civil nature of dispute, no custodial interrogation needed, roots in society, Arnesh Kumar / S.41A guidelines.
   - Prosecution: severity of offence, tampering/threat apprehension, flight risk, gravity of accusation — the S.438 factors courts actually weigh.

---

## Candidate architectures (pick 1–2)

1. **Classifier core + LLM shell** *(recommended main system)*
   `LLM fact extraction → trained classifier (TF-IDF baseline → fine-tuned InLegalBERT) proposes sections → LLM verifies ingredients → LLM generates defense/prosecution arguments`
   Clean pipeline, measurable at every stage.

2. **Case-based retrieval** *(recommended retrieval layer)*
   Embed **past bail cases**, not statutes — facts→facts similarity actually works. Retrieve nearest precedents; read off their sections, outcomes, and reasoning. Bonus: precedent citations for the argument generator for free.

3. **Enriched statute embeddings** *(salvages the original idea)*
   Don't embed bare section text. Build a "card" per section: title + ingredients + illustrations + fact snippets from real cases charged under it. Now facts match facts.

4. **Ingredient / knowledge-graph matching** *(most novel, most work)*
   Decompose each section into elements (act, mens rea, object); match extracted facts symbolically.

**Suggested plan:** build baselines #0–#1 and architecture #3 in week one, then #1 (classifier + LLM shell) as the main system with #2 feeding precedents into the argument generator. This gives a defensible answer to *"why not just ChatGPT?"* — the corpus + classifier does the grounding; the LLM does only what it's good at.

---

## Evaluation

Ground truth comes free from the corpus:

- **Section identification:** recall@k / F1 against sections actually charged or discussed in the judgment.
- **Argument quality:** human scoring rubric + LLM-as-judge, checked against the actual ratio decidendi of decided cases.
- Ablations: baseline #1 vs naive embedding vs enriched embedding vs full pipeline.

---

## Practical flags

- **IPC → BNS migration:** for offences from July 2024, IPC is replaced by the Bharatiya Nyaya Sanhita (e.g., S.420 → S.318(4)) and CrPC S.438 → BNSS S.482. Historic corpus is IPC; new FIRs are BNS. We should at minimum ship an IPC↔BNS mapping table.
- **Scope discipline:** anticipatory bail relevance isn't just "which offence" — it's bailability, punishment threshold (≥7 years → Arnesh Kumar guidelines), and civil-vs-criminal color. These belong in the feature set and the argument generator.
- **Data:** structured judgment JSONs (headnotes, act_sections, bail outcomes, ratio) are the core asset. Dataset curation quality will decide the project's ceiling.
