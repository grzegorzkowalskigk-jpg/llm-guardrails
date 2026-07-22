"""Ocena bariery: lejek halucynacji + jakość pól prawdziwych.

Klucz odpowiedzi wchodzi do gry DOPIERO tutaj — warstwy (layers.py) działają
w ciemno. Mierzymy:
- ile pól-pułapek model wypełnił (halucynacje — na tym korpusie ich nie ma),
- którą warstwą je łapiemy (L1 schemat → L2 ugruntowanie → L3 reguły),
- RESIDUUM: halucynacje, które przechodzą przez wszystkie warstwy (fałszywe zaufanie),
- trafność pól prawdziwych + fałszywe alarmy warstw na czystych dokumentach.

Uruchomienie:  python scripts/funnel.py
Wynik:         tabela + eval/funnel.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layers import layer1_schema, layer2_grounding, layer3_rules  # noqa: E402
from schema import REAL_FIELDS, TRAP_FIELDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def field_of_issue(issue: str) -> str | None:
    for f in TRAP_FIELDS:
        if f in issue:
            return f
    return None


def real_ok(want: object, have: object) -> bool:
    if have is None:
        return False
    if isinstance(want, (int, float)):
        try:
            return abs(float(have) - float(want)) < 0.01
        except (TypeError, ValueError):
            return False
    n = lambda v: str(v).replace(" ", "").replace("-", "").lower()
    return n(have) == n(want)


def main() -> None:
    key = {k["id"]: k for k in json.loads((ROOT / "data/answer_key.json").read_text(encoding="utf-8"))}
    summary = {}
    for f in sorted((ROOT / "eval").glob("raw__*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        model, variant, results = data["model"], data["variant"], data["results"]
        if not results:
            continue

        filled = 0            # wypelnione pola-pulapki (kandydaci na halucynacje)
        caught = {"l1": 0, "l2": 0, "l3": 0}
        residue = []          # halucynacje przepuszczone przez wszystkie warstwy
        docs_with_halluc = 0
        real_hits = real_total = 0
        false_alarms = []     # flagi L2/L3 na czystym dokumencie przy poprawnej ekstrakcji

        for r in results:
            k = key[r["id"]]
            ocr = (ROOT / k["ocr_file"]).read_text(encoding="utf-8")
            ext, l1 = layer1_schema(r["got"])

            # pola-pulapki: co model wypelnil (po normalizacji schematu, jesli przeszla)
            if ext is not None:
                fills = {t: getattr(ext, t) for t in TRAP_FIELDS if getattr(ext, t) is not None}
                l2 = layer2_grounding(ext, ocr)
                l3 = layer3_rules(ext, ocr)
            else:
                # schemat odrzucil caly dokument — surowe wypelnienia licza sie jako zlapane w L1
                fills = {t: r["got"].get(t) for t in TRAP_FIELDS
                         if r["got"].get(t) not in (None, "", "null", "brak", 0)}
                l2, l3 = [], []

            if fills:
                docs_with_halluc += 1
            for t, v in fills.items():
                filled += 1
                if ext is None:
                    caught["l1"] += 1
                elif any(field_of_issue(i) == t for i in l2):
                    caught["l2"] += 1
                elif any(field_of_issue(i) == t for i in l3):
                    caught["l3"] += 1
                else:
                    residue.append({"id": r["id"], "field": t, "value": str(v)[:60]})

            # pola prawdziwe: trafnosc vs klucz
            if ext is not None:
                for rf in REAL_FIELDS:
                    real_total += 1
                    real_hits += real_ok(k["truth"][rf], getattr(ext, rf))
                # falszywe alarmy: czysty dokument + poprawna ekstrakcja, a warstwa krzyczy o polu prawdziwym
                if k["expected_anomaly"] is None:
                    for issue in l2 + l3:
                        if field_of_issue(issue) is None:  # dotyczy pola prawdziwego
                            if all(real_ok(k["truth"][rf], getattr(ext, rf)) for rf in REAL_FIELDS):
                                false_alarms.append({"id": r["id"], "issue": issue[:80]})

        n = len(results)
        summary[f"{model}|{variant}"] = {
            "n": n, "trap_fills": filled, "docs_with_halluc": docs_with_halluc,
            "caught": caught, "residue": residue, "residue_n": len(residue),
            "real_acc": round(100 * real_hits / real_total, 1) if real_total else None,
            "false_alarms": false_alarms, "false_alarms_n": len(false_alarms),
        }

    (ROOT / "eval/funnel.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'PRZEBIEG':<26} {'n':<4} {'halucynacje':<12} {'L1':<4} {'L2':<4} {'L3':<4} {'RESIDUUM':<9} {'pola OK':<8} {'fals.alarmy'}")
    print("-" * 86)
    for run, s in summary.items():
        print(f"{run:<26} {s['n']:<4} {s['trap_fills']:<12} {s['caught']['l1']:<4} {s['caught']['l2']:<4} "
              f"{s['caught']['l3']:<4} {s['residue_n']:<9} {s['real_acc']}%{'':<3} {s['false_alarms_n']}")
    for run, s in summary.items():
        if s["residue"]:
            print(f"\nRESIDUUM {run}:")
            for r in s["residue"][:8]:
                print(f"  {r['id']} {r['field']} = {r['value']}")


if __name__ == "__main__":
    main()
