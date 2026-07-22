"""Faza 3: pętla samokorekty — odrzucenie z konkretnym powodem + jedna poprawka.

Bariera nie tylko blokuje: mówi modelowi DLACZEGO. Dla każdego dokumentu,
na którym warstwy zgłosiły problem, wysyłamy jedną prośbę o poprawę z listą
zastrzeżeń. Mierzymy: ile problemów znika po jednej rundzie feedbacku
(odzysk), a ile wymaga twardej blokady.

Uruchamiać PO zakończeniu run_extract (Ollama wolna).

Uruchomienie:  python scripts/retry_loop.py <model> <naive|guarded>
Wynik:         eval/retry__<model>__<wariant>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import chat_json  # noqa: E402
from layers import issue_class, run_layers  # noqa: E402
from run_extract import PROMPTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Feedback musi niesc PELNY kontekst: schemat pol + poprzednia odpowiedz modelu +
# konkretne zastrzezenia. Bez tego (iteracja #1) model regenerowal JSON od zera
# i ponownie halucynowal pulapki - poprawka pogarszala wynik (1 -> 4 zastrzezenia).
FEEDBACK = """Jestes ekstraktorem danych z polskich faktur. Ekstrahujesz DOKLADNIE te pola:
{"invoice_number": str, "seller_nip": str (same cyfry), "buyer_nip": str (same cyfry),
 "total_net": number, "total_vat": number, "total_gross": number,
 "numer_konta": str | null, "rabat": number | null, "wystawil": str | null,
 "data_zaplaty": str | null}

Twoja poprzednia odpowiedz dla tej faktury:
{previous}

Kontrola jakosci odrzucila ja z powodow:
{issues}

Popraw WYLACZNIE wskazane pola i zwroc pelny JSON z tym samym zestawem pol.
Zasada nadrzedna: przepisuj tylko to, co FAKTYCZNIE jest na dokumencie; jesli
danego pola nie ma na fakturze - zwroc null (nie zgaduj, nie wyliczaj).

FAKTURA:
{ocr}
"""


def main() -> None:
    model, variant = sys.argv[1], sys.argv[2]
    key = {k["id"]: k for k in json.loads((ROOT / "data/answer_key.json").read_text(encoding="utf-8"))}
    raw = json.loads((ROOT / "eval" / f"raw__{model.replace(':', '_')}__{variant}.json").read_text(encoding="utf-8"))

    out = ROOT / "eval" / f"retry__{model.replace(':', '_')}__{variant}.json"
    results = []
    if out.exists():
        results = json.loads(out.read_text(encoding="utf-8"))["results"]
    done = {r["id"] for r in results}

    # Retry ma sens TYLKO dla bledow modelu; wady dokumentu (arytmetyka, zla suma
    # kontrolna) model wiernie przepisal - te ida do czlowieka, nie do poprawki.
    flagged = []
    defect_only = 0
    for r in raw["results"]:
        ocr = (ROOT / key[r["id"]]["ocr_file"]).read_text(encoding="utf-8")
        verdict = run_layers(r["got"], ocr)
        issues = verdict["l1"] + verdict["l2"] + verdict["l3"]
        model_issues = [x for x in issues if issue_class(x) == "model"]
        if not issues or r["id"] in done:
            continue
        if not model_issues:
            defect_only += 1  # tylko wada dokumentu - retry pominiety, do czlowieka
            continue
        flagged.append((r["id"], ocr, model_issues, r["got"]))

    print(f"{model}/{variant}: {len(flagged)} do poprawki (bledy modelu) | "
          f"{defect_only} pominietych (wada dokumentu -> czlowiek)")
    for i, (doc_id, ocr, issues, prev) in enumerate(flagged, 1):
        prompt = (FEEDBACK
                  .replace("{previous}", json.dumps(prev, ensure_ascii=False))
                  .replace("{issues}", "\n".join(f"- {x}" for x in issues))
                  .replace("{ocr}", ocr))
        got2, m = chat_json(prompt, model=model)
        verdict2 = run_layers(got2, ocr)
        # liczymy tylko bledy modelu (defekt dokumentu moze zostac - to nie wina retry)
        left = [x for x in verdict2["l1"] + verdict2["l2"] + verdict2["l3"] if issue_class(x) == "model"]
        results.append({"id": doc_id, "issues_before": issues, "got_retry": got2,
                        "issues_after": left, "metrics": m})
        print(f"[{i}/{len(flagged)}] {doc_id}: {len(issues)} bledow modelu -> {len(left)} po poprawce ({m['seconds']}s)")
        out.write_text(json.dumps({"model": model, "variant": variant, "defect_only": defect_only,
                                   "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")

    fixed = sum(1 for r in results if not r["issues_after"])
    print(f"\nOdzysk bledow modelu po jednej rundzie feedbacku: {fixed}/{len(results)} dokumentow czystych")


if __name__ == "__main__":
    main()
