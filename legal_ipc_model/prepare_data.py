"""
prepare_data.py — Step 1: Validate JSON files and build training datasets.

Usage:
    python prepare_data.py --data_dir /path/to/26000/json/files
    python prepare_data.py --data_dir data/raw --output_dir data/processed
"""
import argparse
import sys
sys.path.insert(0, "src")

from utils.logger_setup import setup_logger
from data_preparation.data_validator import DataValidator
from data_preparation.dataset_builder import DatasetBuilder

logger = setup_logger()


def main():
    parser = argparse.ArgumentParser(description="Prepare legal training data")
    parser.add_argument("--data_dir",   default="data/raw",
                        help="Directory containing the 26k JSON files")
    parser.add_argument("--output_dir", default="data/processed",
                        help="Where to save train/val/test splits")
    parser.add_argument("--val_ratio",  type=float, default=0.08)
    parser.add_argument("--test_ratio", type=float, default=0.07)
    args = parser.parse_args()

    # ── Step 1: Validate ──────────────────────────────────────────────────────
    logger.info("=== Phase 1: Data Validation ===")
    validator = DataValidator(args.data_dir)
    cases     = validator.validate_and_load()

    if not cases:
        logger.error("No valid cases found. Check --data_dir path.")
        sys.exit(1)

    # ── Step 2: Build dataset ─────────────────────────────────────────────────
    logger.info("=== Phase 2: Dataset Building ===")
    builder  = DatasetBuilder(cases)
    records  = builder.build()

    if not records:
        logger.error("No records built. Check data quality.")
        sys.exit(1)

    # ── Step 3: Split ─────────────────────────────────────────────────────────
    logger.info("=== Phase 3: Train/Val/Test Split ===")
    train, val, test = builder.split(records, args.val_ratio, args.test_ratio)

    # ── Step 4: Save ──────────────────────────────────────────────────────────
    logger.info("=== Phase 4: Saving ===")
    builder.save(train, f"{args.output_dir}/train")
    builder.save(val,   f"{args.output_dir}/val")
    builder.save(test,  f"{args.output_dir}/test")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Total cases loaded : {len(cases)}")
    logger.info(f"Total records built: {len(records)}")
    logger.info(f"  Train : {len(train)}")
    logger.info(f"  Val   : {len(val)}")
    logger.info(f"  Test  : {len(test)}")
    logger.info(f"Saved to: {args.output_dir}")
    logger.info("Data preparation complete. Run train.py next.")


if __name__ == "__main__":
    main()
