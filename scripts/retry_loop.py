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
from layers import run_layers  # noqa: E402
from run_extract import PROMPTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

FEEDBACK = """Twoja poprzednia odpowiedz dla tej faktury zostala odrzucona przez
kontrole jakosci. Zastrzezenia:
{issues}

Popraw odpowiedz zgodnie z zastrzezeniami i zwroc PELNY poprawny JSON ponownie.
Pamietaj: przepisuj wylacznie to, co FAKTYCZNIE jest na dokumencie; jesli danego
pola nie ma na fakturze - zwroc null.

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

    flagged = []
    for r in raw["results"]:
        ocr = (ROOT / key[r["id"]]["ocr_file"]).read_text(encoding="utf-8")
        verdict = run_layers(r["got"], ocr)
        issues = verdict["l1"] + verdict["l2"] + verdict["l3"]
        if issues and r["id"] not in done:
            flagged.append((r["id"], ocr, issues))

    print(f"{model}/{variant}: {len(flagged)} dokumentow do poprawki (+{len(done)} juz zrobionych)")
    for i, (doc_id, ocr, issues) in enumerate(flagged, 1):
        prompt = FEEDBACK.format(issues="\n".join(f"- {x}" for x in issues), ocr=ocr)
        got2, m = chat_json(prompt, model=model)
        verdict2 = run_layers(got2, ocr)
        left = verdict2["l1"] + verdict2["l2"] + verdict2["l3"]
        results.append({"id": doc_id, "issues_before": issues, "got_retry": got2,
                        "issues_after": left, "metrics": m})
        print(f"[{i}/{len(flagged)}] {doc_id}: {len(issues)} zastrz. -> {len(left)} po poprawce ({m['seconds']}s)")
        out.write_text(json.dumps({"model": model, "variant": variant, "results": results},
                                  ensure_ascii=False, indent=1), encoding="utf-8")

    fixed = sum(1 for r in results if r["issues_before"] and not r["issues_after"])
    print(f"\nOdzysk po jednej rundzie: {fixed}/{len(results)} dokumentow czystych")


if __name__ == "__main__":
    main()
