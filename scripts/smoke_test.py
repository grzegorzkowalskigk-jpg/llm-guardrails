"""EN: Smoke test of the hallucination signal: checks whether the model fills the
trap fields despite an explicit null option.
PL: Test dymny sygnalu halucynacji: sprawdza, czy model wypelnia pola-pulapki
mimo jawnej mozliwosci zwrocenia null.

Usage / Uruchomienie: python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import chat_json  # noqa: E402
from prompts import EXTRACT  # noqa: E402
from schema import REAL_FIELDS, TRAP_FIELDS, Extraction  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = sys.argv[1:] or ["qwen2.5:1.5b", "qwen2.5:3b"]
PICKS = ["inv_001", "inv_002", "inv_015"]


def main() -> None:
    """EN: Runs a few documents and prints the trap fields filled.
    PL: Puszcza kilka dokumentow i wypisuje wypelnione pola-pulapki.
    """
    key = {k["id"]: k for k in json.loads((ROOT / "data/answer_key.json").read_text(encoding="utf-8"))}
    for model in MODELS:
        print(f"\n=== {model} ===")
        traps_taken = {f: 0 for f in TRAP_FIELDS}
        schema_fails = 0
        for stem in PICKS:
            ocr = (ROOT / f"data/ocr/{stem}.txt").read_text(encoding="utf-8")
            got, m = chat_json(EXTRACT.replace("{ocr}", ocr), model=model)
            try:
                ext = Extraction.model_validate(got)
                halluc = {f: getattr(ext, f) for f in TRAP_FIELDS if getattr(ext, f) is not None}
                for f in halluc:
                    traps_taken[f] += 1
                real_ok = sum(
                    1 for f in REAL_FIELDS
                    if str(getattr(ext, f)).replace(" ", "") == str(key[stem]["truth"][f]).replace(" ", "")
                    or (isinstance(key[stem]["truth"][f], float) and abs(float(getattr(ext, f)) - key[stem]["truth"][f]) < 0.01)
                )
                print(f"  {stem}: pola prawdziwe {real_ok}/6, halucynacje: {halluc or 'BRAK'} ({m['seconds']}s)")
            except Exception as e:  # noqa: BLE001
                schema_fails += 1
                print(f"  {stem}: SCHEMAT ODRZUCIL: {str(e)[:120]} ({m['seconds']}s)")
        print(f"  PODSUMOWANIE: pulapki wziete {dict(traps_taken)}, odrzuty schematu: {schema_fails}")


if __name__ == "__main__":
    main()
