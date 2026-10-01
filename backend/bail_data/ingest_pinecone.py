"""
KAYDA - Precedent ingestion into Pinecone

This version is designed for a Pinecone INDEX WITH INTEGRATED EMBEDDING
using:
    llama-text-embed-v2

The Pinecone index embeds the text server-side.

Usage:

    pip install --upgrade pinecone python-dotenv

    # Ingest ONE JSON file
    python embed_precedents.py ingest ./cases/_2012_5_SCR_1.json

    # Ingest multiple specific JSON files
    python embed_precedents.py ingest ./cases/a.json ./cases/b.json

    # Ingest every JSON directly inside a folder
    python embed_precedents.py ingest ./cases --all

    # Dry run
    python embed_precedents.py ingest ./cases/_2012_5_SCR_1.json --dry-run

    # Search
    python embed_precedents.py query "anticipatory bail in a serious offence"

Environment:
    PINECONE_API_KEY=...
    PINECONE_INDEX_NAME=precedents
"""

import argparse
import json
import os
import sys
import glob
import time

from dotenv import load_dotenv
from pinecone import Pinecone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "precedents")

# IMPORTANT:
# This must be the same namespace used during ingestion and querying.
NAMESPACE = "precedents"

# This MUST match the field configured in your Pinecone integrated index.
#
# Your index is configured with llama-text-embed-v2.
# We use "text" as the source field.
TEXT_FIELD = "text"

UPSERT_BATCH_SIZE = 50


# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------

def validate_environment():

    if not API_KEY:
        raise RuntimeError(
            "PINECONE_API_KEY not found.\n"
            "Put it in your .env file."
        )

    print("=" * 70)
    print("PINECONE CONFIGURATION")
    print("=" * 70)

    print(f"Index     : {INDEX_NAME}")
    print(f"Namespace : {NAMESPACE}")
    print(f"API key   : {'LOADED' if API_KEY else 'MISSING'}")
    print()


# ---------------------------------------------------------------------------
# Pinecone connection
# ---------------------------------------------------------------------------

def get_index():

    pc = Pinecone(api_key=API_KEY)

    # Describe the index so we can verify what actually exists.
    try:
        description = pc.describe_index(INDEX_NAME)

        print("=" * 70)
        print("INDEX INFORMATION")
        print("=" * 70)

        print(f"Name : {INDEX_NAME}")
        print(f"Host : {description.host}")

        # Try to inspect integrated embedding configuration.
        try:
            print(f"Model: {description.embed.model}")
            print(f"Field map: {description.embed.field_map}")
        except Exception:
            print("Integrated embedding information could not be read.")

        print()

    except Exception as e:
        raise RuntimeError(
            f"Could not access Pinecone index '{INDEX_NAME}'.\n"
            f"Error: {e}"
        )

    index = pc.Index(INDEX_NAME)

    return pc, index


# ---------------------------------------------------------------------------
# Metadata cleaning
# ---------------------------------------------------------------------------

def clean_meta(data):

    cleaned = {}

    for key, value in data.items():

        if value is None:
            continue

        if value == "":
            continue

        if value == []:
            continue

        # Pinecone metadata supports primitive values and lists of strings.
        # Convert unusual structures to JSON strings.
        if isinstance(value, dict):
            cleaned[key] = json.dumps(
                value,
                ensure_ascii=False
            )

        elif isinstance(value, list):

            # Keep lists of primitive values.
            if all(
                isinstance(x, (str, int, float, bool))
                for x in value
            ):
                cleaned[key] = value

            else:
                cleaned[key] = json.dumps(
                    value,
                    ensure_ascii=False
                )

        else:
            cleaned[key] = value

    return cleaned


# ---------------------------------------------------------------------------
# Load JSON
# ---------------------------------------------------------------------------

def load_json(path):

    print(f"Reading: {path}")

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_records(path):

    data = load_json(path)

    case = data.get("case", {})
    case_id = data.get("case_id")

    if not case_id:
        raise ValueError(
            f"{path}: missing 'case_id'"
        )

    doc_meta = data.get(
        "doc_meta",
        {}
    )

    issues = case.get(
        "issues",
        []
    )

    propositions = case.get(
        "propositions",
        []
    )

    review = data.get(
        "needs_review",
        []
    )

    verdicts = data.get(
        "verdicts",
        {}
    )

    # -----------------------------------------------------------------------
    # Base metadata
    # -----------------------------------------------------------------------

    base_metadata = {
        "case_id": case_id,

        "case_name": case.get(
            "case_name"
        ),

        "citation": doc_meta.get(
            "citation_scr"
        ),

        "court": case.get(
            "court"
        ),

        "year": doc_meta.get(
            "year"
        ),

        "decided_on": doc_meta.get(
            "decided_on"
        ),

        "procedural_stage": case.get(
            "procedural_stage"
        ),
    }

    records = []

    # -----------------------------------------------------------------------
    # Match proposition -> issue
    # -----------------------------------------------------------------------

    def find_issue(proposition):

        proposition_anchors = set(
            proposition.get(
                "anchors",
                []
            )
        )

        for issue in issues:

            issue_anchors = set(
                issue.get(
                    "anchors",
                    []
                )
            )

            if proposition_anchors & issue_anchors:
                return issue

        return None

    # -----------------------------------------------------------------------
    # Proposition records
    # -----------------------------------------------------------------------

    for proposition in propositions:

        text_value = proposition.get(
            "text"
        )

        if not text_value:
            continue

        proposition_id = proposition.get(
            "id"
        )

        if not proposition_id:
            continue

        issue = find_issue(
            proposition
        )

        parts = []

        if issue:

            question = issue.get(
                "question"
            )

            if question:
                parts.append(
                    f"Issue: {question}"
                )

        parts.append(
            f"Holding: {text_value}"
        )

        conditions = proposition.get(
            "conditions",
            []
        )

        if conditions:

            parts.append(
                "Conditions: "
                + "; ".join(
                    str(x)
                    for x in conditions
                )
            )

        text = "\n".join(parts)

        verdict = verdicts.get(
            proposition_id,
            {}
        )

        quote_missing = any(
            review_item.startswith(
                f"{proposition_id}:"
            )
            and "quote not found"
            in review_item
            for review_item in review
        )

        metadata = clean_meta({

            **base_metadata,

            "unit_type": "proposition",

            "kind": proposition.get(
                "kind"
            ),

            "is_holding": proposition.get(
                "is_holding"
            ),

            "favors": proposition.get(
                "favors"
            ),

            "statutes": proposition.get(
                "statutes",
                []
            ),

            "anchors": proposition.get(
                "anchors",
                []
            ),

            "quote_verified": not quote_missing,

            "favors_verified": verdict.get(
                "favors_correct"
            ),

        })

        records.append({

            "_id":
                f"{case_id}#{proposition_id}",

            TEXT_FIELD:
                text,

            **metadata,

        })

    # -----------------------------------------------------------------------
    # Issue records
    # -----------------------------------------------------------------------

    all_statutes = sorted({

        str(statute)

        for proposition in propositions

        for statute in proposition.get(
            "statutes",
            []
        )

    })

    for index, issue in enumerate(issues):

        question = issue.get(
            "question",
            ""
        )

        short_answer = issue.get(
            "short_answer",
            ""
        )

        text = (
            f"Issue: {question}\n"
            f"Answer: {short_answer}"
        ).strip()

        metadata = clean_meta({

            **base_metadata,

            "unit_type": "issue",

            "statutes": all_statutes,

            "anchors": issue.get(
                "anchors",
                []
            ),

        })

        records.append({

            "_id":
                f"{case_id}#issue{index + 1}",

            TEXT_FIELD:
                text,

            **metadata,

        })

    return records


# ---------------------------------------------------------------------------
# Find input JSON files
# ---------------------------------------------------------------------------

def resolve_files(paths, use_all=False):

    files = []

    # Explicitly supplied files
    for path in paths:

        if os.path.isfile(path):

            if not path.lower().endswith(".json"):
                print(
                    f"Skipping non-JSON file: {path}"
                )
                continue

            files.append(
                os.path.abspath(path)
            )

        elif os.path.isdir(path):

            if use_all:

                folder_files = sorted(
                    glob.glob(
                        os.path.join(
                            path,
                            "*.json"
                        )
                    )
                )

                files.extend(
                    os.path.abspath(f)
                    for f in folder_files
                )

            else:

                raise ValueError(
                    f"{path} is a folder.\n"
                    f"Use --all if you want to ingest "
                    f"every JSON inside it."
                )

        else:

            # Allow wildcard paths
            matches = glob.glob(path)

            if matches:

                files.extend(
                    os.path.abspath(f)
                    for f in matches
                    if f.lower().endswith(".json")
                )

            else:

                raise FileNotFoundError(
                    f"File not found: {path}"
                )

    # Remove duplicates
    files = sorted(
        set(files)
    )

    if not files:

        raise RuntimeError(
            "No JSON files found."
        )

    return files


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest(paths, dry_run=False, use_all=False):

    files = resolve_files(
        paths,
        use_all=use_all
    )

    print("=" * 70)
    print("FILES TO INGEST")
    print("=" * 70)

    for file in files:
        print(file)

    print()

    # -----------------------------------------------------------------------
    # Build records
    # -----------------------------------------------------------------------

    all_records = []

    for path in files:

        try:

            records = build_records(
                path
            )

            print(
                f"{os.path.basename(path)} "
                f"-> {len(records)} records"
            )

            all_records.extend(
                records
            )

        except Exception as e:

            print(
                f"ERROR processing {path}: {e}",
                file=sys.stderr
            )

    print()
    print(
        f"TOTAL FILES   : {len(files)}"
    )

    print(
        f"TOTAL RECORDS : {len(all_records)}"
    )

    if not all_records:

        raise RuntimeError(
            "Zero records were generated."
        )

    # -----------------------------------------------------------------------
    # Show sample
    # -----------------------------------------------------------------------

    print()
    print("=" * 70)
    print("SAMPLE RECORD")
    print("=" * 70)

    sample = all_records[0]

    print(
        json.dumps(
            sample,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    # -----------------------------------------------------------------------
    # Dry run
    # -----------------------------------------------------------------------

    if dry_run:

        print(
            "DRY RUN: nothing was uploaded."
        )

        return

    # -----------------------------------------------------------------------
    # Connect
    # -----------------------------------------------------------------------

    pc, index = get_index()

    # -----------------------------------------------------------------------
    # Upsert using Pinecone's integrated embedding
    # -----------------------------------------------------------------------

    print("=" * 70)
    print("UPLOADING RECORDS")
    print("=" * 70)

    total_uploaded = 0

    for start in range(
        0,
        len(all_records),
        UPSERT_BATCH_SIZE
    ):

        batch = all_records[
            start:start + UPSERT_BATCH_SIZE
        ]

        print(
            f"Uploading records "
            f"{start + 1}-{start + len(batch)}..."
        )

        try:

            response = index.upsert_records(
                namespace=NAMESPACE,
                records=batch
            )

            print(
                f"Response: {response}"
            )

            total_uploaded += len(batch)

        except Exception as e:

            print(
                "UPSERT FAILED:",
                e,
                file=sys.stderr
            )

            raise

    print()
    print(
        f"SUCCESS: submitted "
        f"{total_uploaded} records."
    )

    print(
        "Pinecone is generating the embeddings "
        "server-side."
    )

    # -----------------------------------------------------------------------
    # Give Pinecone a little time
    # -----------------------------------------------------------------------

    print()
    print(
        "Waiting for Pinecone indexing..."
    )

    time.sleep(3)

    # -----------------------------------------------------------------------
    # Verify index statistics
    # -----------------------------------------------------------------------

    print()
    print("=" * 70)
    print("VERIFYING PINECONE")
    print("=" * 70)

    try:

        stats = index.describe_index_stats()

        print(
            json.dumps(
                stats.to_dict()
                if hasattr(stats, "to_dict")
                else stats,
                indent=2,
                default=str
            )
        )

    except Exception as e:

        print(
            f"Could not read index stats: {e}"
        )

    # -----------------------------------------------------------------------
    # Verify specific IDs
    # -----------------------------------------------------------------------

    ids = [
        record["_id"]
        for record in all_records[:5]
    ]

    print()
    print(
        f"Checking first {len(ids)} IDs..."
    )

    try:

        fetched = index.fetch(
            ids=ids,
            namespace=NAMESPACE
        )

        print(
            "FETCH RESULT:"
        )

        print(
            json.dumps(
                fetched.to_dict()
                if hasattr(fetched, "to_dict")
                else fetched,
                indent=2,
                default=str
            )
        )

    except Exception as e:

        print(
            f"Fetch verification failed: {e}"
        )

    print()
    print("=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(query_text, top_k=10):

    pc, index = get_index()

    print("=" * 70)
    print("SEARCH")
    print("=" * 70)

    print(
        f"Query: {query_text}"
    )

    print(
        f"Namespace: {NAMESPACE}"
    )

    print()

    # IMPORTANT:
    # For an integrated-embedding index, do NOT manually call
    # pc.inference.embed().
    #
    # Pinecone embeds this query itself.

    response = index.search(
        namespace=NAMESPACE,
        query={
            "inputs": {
                TEXT_FIELD: query_text
            },
            "top_k": top_k
        }
    )

    # Depending on SDK version, response can be converted to dict.
    if hasattr(
        response,
        "to_dict"
    ):
        response = response.to_dict()

    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
            default=str
        )
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Ingest KAYDA precedent JSON files "
            "into Pinecone integrated embedding index."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command"
    )

    # -----------------------------------------------------------------------
    # ingest
    # -----------------------------------------------------------------------

    ingest_parser = subparsers.add_parser(
        "ingest"
    )

    ingest_parser.add_argument(
        "paths",
        nargs="+",
        help=(
            "Specific JSON file(s), wildcard(s), "
            "or a folder with --all."
        )
    )

    ingest_parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "If a folder is supplied, ingest every "
            "*.json file in that folder."
        )
    )

    ingest_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build records but do not upload."
    )

    # -----------------------------------------------------------------------
    # query
    # -----------------------------------------------------------------------

    query_parser = subparsers.add_parser(
        "query"
    )

    query_parser.add_argument(
        "text",
        help="Natural-language legal query."
    )

    query_parser.add_argument(
        "--top-k",
        type=int,
        default=10
    )

    args = parser.parse_args()

    validate_environment()

    _default_out = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "out"
    )

    if args.command is None:
        print(f"No command given — defaulting to: ingest '{_default_out}' --all\n")
        ingest(paths=[_default_out], use_all=True)

    elif args.command == "ingest":

        ingest(
            paths=args.paths,
            dry_run=args.dry_run,
            use_all=args.all
        )

    elif args.command == "query":

        search(
            query_text=args.text,
            top_k=args.top_k
        )


if __name__ == "__main__":
    main()