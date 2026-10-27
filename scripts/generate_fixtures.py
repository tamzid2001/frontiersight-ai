"""Regenerate committed fixtures from the seeded generator (deterministic)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.scenarios import export_fixtures

if __name__ == "__main__":
    for p in export_fixtures(str(Path(__file__).resolve().parents[1] / "fixtures")):
        print("wrote", p)
