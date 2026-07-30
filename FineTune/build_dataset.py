"""
Phase 3 — Build instruction-tuning dataset from extracted case records.

Reads all JSON records from extracted_records/, generates instruction/output
pairs, splits into train/val/test by case (no leakage), and writes JSONL files
to training_data/.

Usage:
    python build_dataset.py                    # build from all valid records
    python build_dataset.py --dry-run          # print stats without writing files
    python build_dataset.py --split 80 10 10   # custom train/val/test split %

Output files:
    training_data/train.jsonl
    training_data/val.jsonl
    training_data/test.jsonl
    training_data/dataset_stats.json

Each JSONL line format (Alpaca-style, compatible with most fine-tuning frameworks):
    {
        "instruction": "...",
        "input": "...",      # case context
        "output": "...",     # expected model output
        "metadata": {        # for tracing/debugging — strip before training if needed
            "source_file": "...",
            "pair_type": "...",
            "case_citation": "..."
        }
    }
"""

import argparse
import json
import random
import re
import sys
import logging
from pathlib import Path
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

RECORDS_DIR = Path("extracted_records")
OUTPUT_DIR = Path("training_data")

# Minimum paragraph text length to use in a training pair
MIN_PARA_LENGTH = 80
# Minimum headnote point text length
MIN_HEADNOTE_LENGTH = 60

OUTCOME_DESCRIPTIONS = {
    "granted":   "granted anticipatory bail to the appellant/petitioner",
    "modified":  "modified the bail conditions imposed by the lower court",
    "deleted":   "deleted the onerous bail condition entirely",
    "refused":   "refused to grant anticipatory bail",
    "dismissed": "dismissed the appeal, upholding the lower court's order",
    "referred":  "referred the matter to a larger bench for consideration",
    "interim":   "granted interim protection from arrest pending further hearing",
}


# ─────────────────────────────────────────────────────────────────────────────
# Pair generators — one function per pair type
# Each takes a record dict and returns list[dict] of pairs.
# Returns [] if the record lacks the required fields.
# ─────────────────────────────────────────────────────────────────────────────

def _meta(rec: dict, pair_type: str) -> dict:
    return {
        "source_file": rec["source_file"],
        "pair_type": pair_type,
        "case_citation": rec.get("case_citation", ""),
        "decided_on_year": rec.get("decided_on_year"),
    }


def _clean(text: str) -> str:
    """Collapse whitespace for clean training text."""
    return re.sub(r"\s+", " ", text).strip()


def gen_outcome_classification(rec: dict) -> list[dict]:
    """
    Pair type: outcome_classification
    Given case facts, predict the SC's outcome.
    """
    outcome = rec.get("bail_outcome")
    if not outcome or outcome not in OUTCOME_DESCRIPTIONS:
        return []

    appellant = rec.get("appellant") or "the appellant"
    respondent = rec.get("respondent") or "the State"
    court = rec.get("court") or "the Supreme Court"
    acts = ", ".join(rec.get("referred_acts", [])) or "Section 438 CrPC"

    # Use first headnote point as context if available
    pts = rec.get("headnote_points", [])
    context = _clean(pts[0]["text"]) if pts else _clean(rec.get("headnote_raw", ""))
    if not context or len(context) < MIN_HEADNOTE_LENGTH:
        return []

    instruction = (
        f"In this anticipatory bail case under {acts}, "
        f"{appellant} approached {court} challenging the bail order. "
        "Based on the following case summary, classify the Supreme Court's outcome."
    )
    output = (
        f"The Supreme Court {OUTCOME_DESCRIPTIONS[outcome]}. "
        f"Outcome classification: {outcome.upper()}."
    )
    if rec.get("bail_amount_original") and outcome in ("modified", "deleted"):
        output += (
            f" The original condition was {rec['bail_amount_original']}."
        )
    if rec.get("bail_amount_modified") and outcome == "modified":
        output += f" This was modified to {rec['bail_amount_modified']}."

    return [{"instruction": instruction, "input": context, "output": output,
             "metadata": _meta(rec, "outcome_classification")}]


def gen_legal_principle(rec: dict) -> list[dict]:
    """
    Pair type: legal_principle
    Extract the generalizable legal principle from the case.
    """
    ratio = rec.get("ratio_decidendi")
    if not ratio or len(_clean(ratio)) < MIN_PARA_LENGTH:
        return []

    acts = ", ".join(rec.get("referred_acts", [])) or "Section 438 CrPC"
    instruction = (
        f"This is a Supreme Court judgment concerning anticipatory bail under {acts}. "
        "State the legal principle (ratio decidendi) established or applied in this case."
    )

    # Use headnote as context if available
    pts = rec.get("headnote_points", [])
    context = _clean(pts[0]["text"]) if pts else ""
    if not context:
        # Fall back to first 2 paragraphs as context
        paras = rec.get("numbered_paragraphs", [])
        context = " ".join(_clean(p["text"]) for p in paras[:2])

    output = _clean(ratio)

    return [{"instruction": instruction, "input": context, "output": output,
             "metadata": _meta(rec, "legal_principle")}]


def gen_headnote_points(rec: dict) -> list[dict]:
    """
    Pair type: headnote_point_A / headnote_point_B / headnote_point_C
    Each labelled headnote point is a compressed holding — model learns
    to produce that compression given the case context.
    """
    pts = rec.get("headnote_points", [])
    if not pts:
        return []

    pairs = []
    acts = ", ".join(rec.get("referred_acts", [])) or "Section 438 CrPC"

    # Use paragraphs as the "input" context
    paras = rec.get("numbered_paragraphs", [])
    # Limit to first 4 paragraphs to keep context bounded
    context_paras = paras[:4] if len(paras) >= 4 else paras
    context = " ".join(_clean(p["text"]) for p in context_paras)
    if len(context) < MIN_PARA_LENGTH:
        return []

    for pt in pts:
        text = _clean(pt["text"])
        if len(text) < MIN_HEADNOTE_LENGTH:
            continue
        label = pt["label"]
        instruction = (
            f"From this Supreme Court judgment on anticipatory bail under {acts}, "
            f"extract legal proposition {label} as it would appear in the official headnote. "
            "State it as a concise legal holding."
        )
        output = text
        pairs.append({
            "instruction": instruction,
            "input": context,
            "output": output,
            "metadata": _meta(rec, f"headnote_point_{label}"),
        })

    return pairs


def gen_bail_condition_extraction(rec: dict) -> list[dict]:
    """
    Pair type: bail_condition_extraction
    Given judgment paragraphs, extract the conditions imposed on bail.
    """
    conditions = rec.get("bail_conditions", [])
    if not conditions:
        return []

    # Need the grant/modification paragraph as context
    paras = rec.get("numbered_paragraphs", [])
    # Find the paragraph that contains condition language
    condition_para = None
    for para in paras:
        if any(_clean(c).lower()[:40] in _clean(para["text"]).lower() for c in conditions):
            condition_para = _clean(para["text"])
            break

    if not condition_para or len(condition_para) < MIN_PARA_LENGTH:
        return []

    instruction = (
        "Extract all conditions imposed on the grant of anticipatory bail "
        "from the following judgment paragraph."
    )
    output = "\n".join(f"- {_clean(c)}" for c in conditions)

    return [{"instruction": instruction, "input": condition_para, "output": output,
             "metadata": _meta(rec, "bail_condition_extraction")}]


def gen_section_identification(rec: dict) -> list[dict]:
    """
    Pair type: section_identification
    Given a case description, identify which CrPC provisions apply.
    """
    acts = rec.get("referred_acts", [])
    if not acts:
        return []

    pts = rec.get("headnote_points", [])
    context = _clean(pts[0]["text"]) if pts else _clean(rec.get("headnote_raw", ""))
    if not context or len(context) < MIN_HEADNOTE_LENGTH:
        return []

    instruction = (
        "Identify the specific provisions of the Code of Criminal Procedure "
        "that are applicable in this bail matter."
    )
    acts_text = ", ".join(acts)
    output = (
        f"The following provisions of CrPC apply: {acts_text}. "
        "Section 438 deals with direction for grant of bail to a person "
        "apprehending arrest (anticipatory bail). "
        "Section 438(2) specifies the conditions that may be imposed while "
        "granting anticipatory bail."
    )

    return [{"instruction": instruction, "input": context, "output": output,
             "metadata": _meta(rec, "section_identification")}]


def gen_case_summary(rec: dict) -> list[dict]:
    """
    Pair type: case_summary
    Summarize the case: parties, issue, outcome, key condition.
    """
    outcome = rec.get("bail_outcome")
    appellant = rec.get("appellant")
    respondent = rec.get("respondent")
    date = rec.get("decided_on")
    citation = rec.get("case_citation")

    if not all([outcome, appellant, respondent, date]):
        return []

    # Build full context from judgment paragraphs
    paras = rec.get("numbered_paragraphs", [])
    if not paras:
        return []
    context = " ".join(_clean(p["text"]) for p in paras[:6])

    instruction = (
        "Provide a structured summary of this Supreme Court anticipatory bail judgment, "
        "covering: (1) parties, (2) legal issue, (3) court's decision, "
        "(4) key conditions imposed or modified."
    )

    # Build structured output
    outcome_desc = OUTCOME_DESCRIPTIONS.get(outcome, outcome)
    lines = [
        f"Case: {citation or 'N/A'} | Decided: {date}",
        f"Parties: {appellant} v. {respondent}",
        f"Issue: Application for anticipatory bail under {', '.join(rec.get('referred_acts', ['S.438']))}.",
        f"Decision: The Supreme Court {outcome_desc}.",
    ]
    if rec.get("bail_amount_original"):
        lines.append(f"Original condition: {rec['bail_amount_original']}.")
    if rec.get("bail_amount_modified"):
        lines.append(f"Modified to: {rec['bail_amount_modified']}.")
    if rec.get("dispute_nature"):
        lines.append(f"Nature of dispute: {rec['dispute_nature']}.")
    if rec.get("ratio_decidendi"):
        ratio_snippet = _clean(rec["ratio_decidendi"])[:200]
        lines.append(f"Key principle: {ratio_snippet}...")

    output = "\n".join(lines)

    return [{"instruction": instruction, "input": context[:1500], "output": output,
             "metadata": _meta(rec, "case_summary")}]


def gen_onerous_condition_reasoning(rec: dict) -> list[dict]:
    """
    Pair type: onerous_condition_reasoning
    Specific to the core anticipatory bail topic: was the condition onerous?
    Only generated when bail_amount_original is present and outcome is
    modified/deleted (the court found it excessive).
    """
    if rec.get("bail_outcome") not in ("modified", "deleted"):
        return []

    orig = rec.get("bail_amount_original")
    if not orig:
        return []

    # Find the paragraph containing the reasoning about the condition being onerous
    paras = rec.get("numbered_paragraphs", [])
    reasoning_para = None
    for para in paras:
        text_lower = para["text"].lower()
        if any(w in text_lower for w in ["onerous", "excessive", "disproportionate",
                                          "recovery", "civil suit", "modify", "deleted",
                                          "condition of deposit"]):
            if len(para["text"]) > MIN_PARA_LENGTH:
                reasoning_para = _clean(para["text"])
                break

    if not reasoning_para:
        return []

    instruction = (
        f"The lower court imposed a bail condition of {orig}. "
        "Explain whether this condition was appropriate under Section 438 CrPC "
        "and what the Supreme Court decided about it."
    )

    outcome = rec.get("bail_outcome")
    mod = rec.get("bail_amount_modified")

    if outcome == "deleted":
        output = (
            f"The Supreme Court held that the condition of {orig} was onerous and "
            "contrary to the purpose of anticipatory bail under Section 438 CrPC. "
            "Criminal proceedings cannot be used as a tool for recovery of civil dues. "
            "The court deleted the condition entirely. " + reasoning_para
        )
    else:
        output = (
            f"The Supreme Court found the condition of {orig} to be onerous "
            "and not commensurate with the purpose of anticipatory bail. "
        )
        if mod:
            output += (
                f"In modification of the order, the court directed the "
                f"appellant to furnish {mod} instead. "
            )
        output += reasoning_para

    return [{"instruction": instruction, "input": reasoning_para, "output": output,
             "metadata": _meta(rec, "onerous_condition_reasoning")}]


def gen_ipc_section_reasoning(rec: dict) -> list[dict]:
    """
    Pair type: ipc_section_reasoning
    For each IPC section mentioned, generate a Q&A about why it was invoked.
    """
    ipc = [s for s in rec.get("act_sections", []) if s.get("act_short_name") == "IPC"]
    if not ipc:
        return []

    paras = rec.get("numbered_paragraphs", [])
    context = " ".join(_clean(p["text"]) for p in paras[:4])
    if len(context) < MIN_PARA_LENGTH:
        return []

    pairs = []
    seen_sections: set[str] = set()
    for s in ipc:
        sec = s["section"]
        if sec in seen_sections:
            continue
        seen_sections.add(sec)

        title = s.get("section_title") or f"Section {sec} IPC"
        how = s.get("how_used", "mentioned")
        ctx = s.get("context", "")

        instruction = (
            f"Why was Section {sec} of the Indian Penal Code ({title}) "
            "invoked in this case? Explain its relevance."
        )
        output = (
            f"Section {sec} IPC ({title}) was {how.lower()} in this case. "
        )
        if ctx:
            output += _clean(ctx)
        if s.get("is_charged"):
            output += " The accused was charged under this section."
        if s.get("is_interpreted"):
            output += " The court interpreted this section."

        pairs.append({
            "instruction": instruction,
            "input": context[:800],
            "output": output,
            "metadata": _meta(rec, "ipc_section_reasoning"),
        })

    return pairs[:2]  # cap at 2 per case to avoid repetition


def gen_crpc_section_reasoning(rec: dict) -> list[dict]:
    """
    Pair type: crpc_section_reasoning
    For each CrPC section mentioned, generate a Q&A about how it was applied.
    """
    crpc = [s for s in rec.get("act_sections", []) if s.get("act_short_name") == "CrPC"]
    if not crpc:
        return []

    paras = rec.get("numbered_paragraphs", [])
    context = " ".join(_clean(p["text"]) for p in paras[:4])
    if len(context) < MIN_PARA_LENGTH:
        return []

    pairs = []
    seen_sections: set[str] = set()
    for s in crpc:
        sec = s["section"]
        if sec in seen_sections:
            continue
        seen_sections.add(sec)

        title = s.get("section_title") or f"Section {sec} CrPC"
        how = s.get("how_used", "applied")
        ctx = s.get("context", "")

        instruction = (
            f"What is Section {sec} of CrPC ({title}) "
            "and how was it applied in this case?"
        )
        output = (
            f"Section {sec} CrPC deals with {title}. "
            f"In this case, it was {how.lower()}. "
        )
        if ctx:
            output += _clean(ctx)

        pairs.append({
            "instruction": instruction,
            "input": context[:800],
            "output": output,
            "metadata": _meta(rec, "crpc_section_reasoning"),
        })

    return pairs[:2]


def gen_procedural_history(rec: dict) -> list[dict]:
    """
    Pair type: procedural_history
    Summarise the procedural chain from FIR to SC.
    """
    proc = rec.get("procedural_history")
    if not proc:
        return []

    paras = rec.get("numbered_paragraphs", [])
    context = " ".join(_clean(p["text"]) for p in paras[:3])
    if len(context) < MIN_PARA_LENGTH:
        return []

    instruction = (
        "Describe the procedural history of this case from the FIR stage "
        "to the Supreme Court."
    )

    lines = []
    if proc.get("fir_number"):
        fir_line = f"FIR: {proc['fir_number']}"
        if proc.get("fir_date"):
            fir_line += f" dated {proc['fir_date']}"
        if proc.get("police_station"):
            fir_line += f", registered at {proc['police_station']}"
        if proc.get("district"):
            fir_line += f", {proc['district']}"
        lines.append(fir_line)
    if proc.get("sessions_court_decision"):
        lines.append(f"Sessions Court: {_clean(proc['sessions_court_decision'])[:120]}")
    if proc.get("high_court_bench") or proc.get("high_court_order_date"):
        hc = proc.get("high_court_bench", "High Court")
        date = proc.get("high_court_order_date", "")
        decision = proc.get("high_court_decision", "")
        hc_line = f"{hc}"
        if date:
            hc_line += f" (order dated {date})"
        if decision:
            hc_line += f": {_clean(decision)[:100]}"
        lines.append(hc_line)

    if not lines:
        return []

    output = " → ".join(lines)

    return [{
        "instruction": instruction,
        "input": context[:800],
        "output": output,
        "metadata": _meta(rec, "procedural_history"),
    }]


# ─────────────────────────────────────────────────────────────────────────────
# Pair generation orchestrator
# ─────────────────────────────────────────────────────────────────────────────

GENERATORS = [
    gen_outcome_classification,
    gen_legal_principle,
    gen_headnote_points,
    gen_bail_condition_extraction,
    gen_section_identification,
    gen_case_summary,
    gen_onerous_condition_reasoning,
    gen_ipc_section_reasoning,
    gen_crpc_section_reasoning,
    gen_procedural_history,
]


def generate_pairs_for_record(rec: dict) -> list[dict]:
    """Generate all valid instruction/output pairs for one record."""
    all_pairs = []
    for gen_fn in GENERATORS:
        try:
            pairs = gen_fn(rec)
            all_pairs.extend(pairs)
        except Exception as e:
            logger.warning(f"Generator {gen_fn.__name__} failed for "
                           f"{rec.get('source_file', '?')}: {e}")
    return all_pairs


# ─────────────────────────────────────────────────────────────────────────────
# Train / val / test split
# ─────────────────────────────────────────────────────────────────────────────

def split_by_case(
    records: list[dict],
    train_pct: float = 0.8,
    val_pct: float = 0.1,
    seed: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Split records by case (source_file), not by individual pair.
    All pairs from the same case go into the same split — no leakage.

    Strategy: sort by year (oldest → train, newest → test) then shuffle
    within each year group. This is more realistic than pure random split
    because in production, the model will face cases from years not in training.
    """
    # Group by year
    by_year: dict[int, list[dict]] = defaultdict(list)
    no_year = []
    for rec in records:
        yr = rec.get("decided_on_year")
        if yr:
            by_year[yr].append(rec)
        else:
            no_year.append(rec)

    rng = random.Random(seed)

    # Sort years, shuffle within each year
    ordered = []
    for yr in sorted(by_year.keys()):
        group = by_year[yr][:]
        rng.shuffle(group)
        ordered.extend(group)

    # Put no-year records at end (shuffle them)
    rng.shuffle(no_year)
    ordered.extend(no_year)

    n = len(ordered)
    train_end = int(n * train_pct)
    val_end = train_end + int(n * val_pct)

    return ordered[:train_end], ordered[train_end:val_end], ordered[val_end:]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def load_valid_records() -> list[dict]:
    """Load all records that pass minimum quality bar."""
    records = []
    skipped = 0
    for path in sorted(RECORDS_DIR.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not load {path.name}: {e}")
            skipped += 1
            continue

        # Minimum bar: must have referred_acts with 438 and numbered_paragraphs
        if not any("438" in a for a in rec.get("referred_acts", [])):
            logger.debug(f"Skip {path.name}: no Section 438")
            skipped += 1
            continue
        if not rec.get("numbered_paragraphs"):
            logger.debug(f"Skip {path.name}: no paragraphs")
            skipped += 1
            continue

        records.append(rec)

    logger.info(f"Loaded {len(records)} valid records ({skipped} skipped)")
    return records


def write_jsonl(path: Path, pairs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fine-tuning dataset")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without writing files")
    parser.add_argument("--split", nargs=3, type=int, default=[80, 10, 10],
                        metavar=("TRAIN", "VAL", "TEST"),
                        help="Train/val/test split percentages (must sum to 100)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_p, val_p, test_p = args.split
    if train_p + val_p + test_p != 100:
        logger.error("Split percentages must sum to 100")
        sys.exit(1)

    records = load_valid_records()
    if not records:
        logger.error(f"No valid records in {RECORDS_DIR}/")
        sys.exit(1)

    # Split records first (by case)
    train_recs, val_recs, test_recs = split_by_case(
        records,
        train_pct=train_p / 100,
        val_pct=val_p / 100,
        seed=args.seed,
    )

    logger.info(f"Case split: train={len(train_recs)} val={len(val_recs)} test={len(test_recs)}")

    # Generate pairs per split
    splits: dict[str, tuple[list[dict], list[dict]]] = {
        "train": (train_recs, []),
        "val":   (val_recs, []),
        "test":  (test_recs, []),
    }

    pair_type_counts: dict[str, int] = defaultdict(int)
    pairs_per_case: list[int] = []

    for split_name, (recs, _) in splits.items():
        all_pairs = []
        for rec in recs:
            pairs = generate_pairs_for_record(rec)
            pairs_per_case.append(len(pairs))
            all_pairs.extend(pairs)
            for p in pairs:
                pair_type_counts[p["metadata"]["pair_type"]] += 1
        splits[split_name] = (recs, all_pairs)

    total_pairs = sum(len(pairs) for _, pairs in splits.values())

    # Stats
    print(f"\n{'='*60}")
    print(f"  DATASET BUILD SUMMARY")
    print(f"{'='*60}")
    print(f"  Source records : {len(records)}")
    print(f"  Total pairs    : {total_pairs}")
    print(f"  Avg pairs/case : {sum(pairs_per_case)/len(pairs_per_case):.1f}")
    print(f"  Min pairs/case : {min(pairs_per_case)}")
    print(f"  Max pairs/case : {max(pairs_per_case)}")
    print(f"{'─'*60}")
    print(f"  Split breakdown:")
    for split_name, (recs, pairs) in splits.items():
        print(f"    {split_name:<6}: {len(recs):3} cases → {len(pairs):4} pairs")
    print(f"{'─'*60}")
    print(f"  Pairs by type:")
    for pair_type, count in sorted(pair_type_counts.items(), key=lambda x: -x[1]):
        print(f"    {pair_type:<35}: {count}")
    print(f"{'='*60}\n")

    if args.dry_run:
        logger.info("Dry run — no files written")
        # Print one example per type for inspection
        seen_types: set[str] = set()
        for _, pairs in splits.values():
            for pair in pairs:
                pt = pair["metadata"]["pair_type"]
                if pt not in seen_types:
                    seen_types.add(pt)
                    print(f"\n--- EXAMPLE: {pt} ---")
                    print("INSTRUCTION:", pair["instruction"][:200])
                    print("INPUT:", pair["input"][:200])
                    print("OUTPUT:", pair["output"][:200])
        return

    # Write JSONL files (without metadata by default — add --keep-meta if needed)
    stats = {
        "total_records": len(records),
        "total_pairs": total_pairs,
        "split": {
            split_name: {"cases": len(recs), "pairs": len(pairs)}
            for split_name, (recs, pairs) in splits.items()
        },
        "pair_type_counts": dict(pair_type_counts),
        "avg_pairs_per_case": round(sum(pairs_per_case) / len(pairs_per_case), 2),
    }

    for split_name, (_, pairs) in splits.items():
        out_path = OUTPUT_DIR / f"{split_name}.jsonl"
        # Write training format (instruction + input + output, no metadata)
        training_pairs = [
            {"instruction": p["instruction"], "input": p["input"], "output": p["output"]}
            for p in pairs
        ]
        write_jsonl(out_path, training_pairs)
        logger.info(f"Wrote {len(training_pairs)} pairs → {out_path}")

        # Also write a version with metadata for debugging
        debug_path = OUTPUT_DIR / f"{split_name}_with_metadata.jsonl"
        write_jsonl(debug_path, pairs)

    stats_path = OUTPUT_DIR / "dataset_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    logger.info(f"Stats → {stats_path}")

    print(f"Dataset written to {OUTPUT_DIR}/")
    print(f"Training files: train.jsonl ({splits['train'][1].__len__()} pairs), "
          f"val.jsonl ({splits['val'][1].__len__()}), "
          f"test.jsonl ({splits['test'][1].__len__()})")


if __name__ == "__main__":
    main()
