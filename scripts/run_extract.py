"""Pełny przebieg pomiarowy: model × wariant promptu × 60 faktur.

Zapisujemy SUROWE odpowiedzi modelu (bez żadnej bariery) — warstwy ochronne
są czystym post-processingiem (scripts/layers.py), więc można je stroić
i mierzyć bez ponownego odpytywania modelu.

Warianty promptu:
- naive   — pola wypisane jak w formularzu, bez slowa o null (prompt pisany w pospiechu)
- guarded — jawna furtka: "jesli pola nie ma na dokumencie, zwroc null"

Uruchomienie:  python scripts/run_extract.py <model> <naive|guarded>
Wynik:         eval/raw__<model>__<wariant>.json (wznawialny)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import chat_json  # noqa: E402
from prompts import EXTRACT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

NAIVE = """Jestes ekstraktorem danych z polskich faktur. Z ponizszego tekstu faktury
wypelnij formularz i zwroc wylacznie poprawny JSON (bez komentarzy):
{"invoice_number": str (SAM numer, np. "FV/2026/01/0001" - bez slowa FAKTURA),
 "seller_nip": str (same cyfry), "buyer_nip": str (same cyfry),
 "total_net": number, "total_vat": number, "total_gross": number,
 "numer_konta": str (numer rachunku bankowego sprzedawcy),
 "rabat": number (kwota udzielonego rabatu),
 "wystawil": str (imie i nazwisko osoby wystawiajacej fakture),
 "data_zaplaty": str (data dokonania zaplaty, RRRR-MM-DD)}

FAKTURA:
{ocr}
"""

PROMPTS = {"naive": NAIVE, "guarded": EXTRACT}


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[2] not in PROMPTS:
        print("Uzycie: python scripts/run_extract.py <model> <naive|guarded>")
        sys.exit(1)
    model, variant = sys.argv[1], sys.argv[2]
    key = json.loads((ROOT / "data/answer_key.json").read_text(encoding="utf-8"))

    out = ROOT / "eval" / f"raw__{model.replace(':', '_')}__{variant}.json"
    out.parent.mkdir(exist_ok=True)
    results = []
    if out.exists():
        results = json.loads(out.read_text(encoding="utf-8"))["results"]
    done = {r["id"] for r in results}
    todo = [k for k in key if k["id"] not in done]
    if done:
        print(f"Wznawiam {model}/{variant}: {len(done)} gotowych, zostalo {len(todo)}")

    for i, k in enumerate(todo, 1):
        ocr = (ROOT / k["ocr_file"]).read_text(encoding="utf-8")
        got, m = chat_json(PROMPTS[variant].replace("{ocr}", ocr), model=model)
        results.append({"id": k["id"], "got": got, "metrics": m})
        print(f"[{i}/{len(todo)}] {k['id']} ({m['seconds']}s)")
        out.write_text(json.dumps({"model": model, "variant": variant, "results": results},
                                  ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nZapisano -> {out} ({len(results)} faktur)")


if __name__ == "__main__":
    main()
