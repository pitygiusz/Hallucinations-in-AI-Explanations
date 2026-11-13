"""Command-line entry point for the CharXiv LM Studio pipeline."""

import sys
from pathlib import Path


EXPERIMENTS_DIR = Path(__file__).resolve().parents[1] / "Experiments"
sys.path.insert(0, str(EXPERIMENTS_DIR))

from charxiv_pipeline import main


if __name__ == "__main__":
    main()
