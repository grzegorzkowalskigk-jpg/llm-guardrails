# Changelog — llm-guardrails

Rejestr błędów i poprawek. Bug and fix log.

## v1.0.0 (2026-07-22) — pierwsze wydanie / initial release

Naprawione / Fixed:

1. **Pętla samokorekty pogarszała wynik (1 → 4 problemy)** — odrzucając
   odpowiedź, wysyłaliśmy modelowi sam powód, bez schematu i bez jego
   poprzedniej odpowiedzi. Model generował dokument od zera zamiast poprawiać.
   Informacja zwrotna niesie teraz komplet: powód, schemat i poprzednią
   odpowiedź (`retry_loop.py`).
   *The self-correction loop made things worse (1 to 4 issues): feedback carried
   only the reason, without the schema or the model's previous answer, so the
   model regenerated from scratch. Feedback now carries all three.*

2. **Wina dokumentu mylona z winą modelu** — problem zgłoszony przez warstwy
   mógł oznaczać wadę samego dokumentu (model wiernie ją przepisał) albo błąd
   modelu. Bez rozdzielenia odsetek odzysku był bez sensu, bo w pierwszym
   przypadku poprawka jest niemożliwa. Dodano `issue_class()` (`layers.py`).
   *Layer issues conflated document defects (faithfully copied by the model)
   with model errors, making the recovery rate meaningless. Added
   `issue_class()` (`layers.py`).*

3. **Kwoty odrzucane przez dosłowne porównanie** — ta sama kwota bywa zapisana
   z kropką lub przecinkiem, ze spacją lub bez; `money_variants()` porównuje
   wszystkie typowe zapisy (`layers.py`).
   *Literal comparison rejected valid amounts written with a different decimal
   separator or spacing; `money_variants()` compares common forms.*

4. **Puste napisy i zerowe rabaty liczone jako wypełnione pola** — zawyżały
   odsetek halucynacji; walidatory mapują je na `None` (`schema.py`).
   *Empty strings and zero discounts counted as filled fields and inflated the
   hallucination rate; validators map them to `None` (`schema.py`).*
