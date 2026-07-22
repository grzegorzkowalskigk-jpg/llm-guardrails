# Guardrails — walidacja halucynacji LLM

Sztuczna inteligencja potrafi zmyślać z pełnym przekonaniem. W tym teście model
językowy wpisał do formularzy **180 wartości, których nie było na żadnym
dokumencie** — numery kont, nazwiska, daty. Ten projekt pokazuje, jak z takiego
narzędzia zrobić system godny zaufania: nie jedną magiczną poprawką, lecz
kolejnymi warstwami kontroli, z których każda ma **zmierzoną** skuteczność na
60 fakturach z kluczem odpowiedzi.

## Jak mierzymy halucynacje

Do ekstrahowanych pól prawdziwych (numer, NIP-y, kwoty) dołożyliśmy cztery
**pola-pułapki, których na dokumentach NIE MA**: numer konta, rabat, osoba
wystawiająca, data zapłaty. Poprawna odpowiedź to zawsze „brak" (null).
Każda wypełniona pułapka = policzalna halucynacja. 60 faktur × 4 pułapki =
240 okazji do zmyślenia na model.

## Lejek zaufania

| Etap | Halucynacje (qwen2.5:3b, prompt naiwny) |
|---|---|
| Surowe wyjście modelu | **180** — średnio 3 zmyślone wartości na fakturę |
| + jedno zdanie w prompcie („jeśli pola nie ma — null") | **4** (−98%) |
| + warstwy: schemat · źródło · reguły ról | **0** przepuszczonych |

Przy zerowej liczbie fałszywych alarmów i **99,3% trafności pól prawdziwych** —
bariera nie dusi poprawnej pracy.

## Najważniejsze odkrycie: model przestawia role, nie zmyśla z powietrza

Model rzadko wymyśla dane od zera. Najczęściej bierze **prawdziwą wartość
z dokumentu i podstawia ją w złą rolę**: NIP jako numer konta, nazwę firmy jako
osobę wystawiającą, termin płatności jako datę zapłaty. Dlatego samo sprawdzenie
„czy wartość jest w dokumencie" (warstwa 2) NIE wystarcza — te wartości *są*
w dokumencie. Łapią je dopiero **reguły ról** (warstwa 3): NRB ma 26 cyfr
(NIP ma 10), firma to nie osoba, data przepisana z pola „Termin płatności".

## Warstwy bariery

1. **Schemat (Pydantic)** — struktura, typy, formaty. Pusty string to poprawna
   odmowa, nie błąd.
2. **Ugruntowanie** — czy wartość w ogóle występuje w źródle. Łapie czystą fabrykację.
3. **Reguły ról i spójności** — role pól + arytmetyka + suma kontrolna NIP.
   Warstwy **nie znają klucza odpowiedzi** — klucz służy wyłącznie do ich oceny.

## Uczciwość wobec metody (dwa przypadki)

- **Przeciek i łatka:** trzy halucynacje początkowo przeszły przez wszystkie
  warstwy (skrócona nazwa firmy jako „osoba"). Zamiast to przemilczeć — reguła
  poprawiona wg klucza, residuum spadło do **0**, wciąż bez fałszywych alarmów.
- **Samokorekta zawodzi:** pętla feedbacku dostawała odrzucone dokumenty
  z *konkretnym* zarzutem („to firma, nie osoba") i jedną szansą poprawy.
  Wynik na czterech przebiegach: **0 ze 112 błędów modelu naprawionych** —
  mały model, dostawszy dokładny zarzut, uparcie powtarza halucynację albo
  wymyśla świeżą. Wniosek: **systemowi ufasz dzięki deterministycznym warstwom,
  nie dzięki dobrej woli modelu.** Samokorekta to słaby dodatek, nie zabezpieczenie.

## Uruchomienie

```bash
# wymaga Ollamy z qwen2.5:1.5b i qwen2.5:3b
python scripts/run_extract.py qwen2.5:3b naive   # pomiar surowego wyjścia
python scripts/funnel.py                          # lejek: co łapie która warstwa
python scripts/retry_loop.py qwen2.5:3b naive     # pętla samokorekty
```

## Struktura

```
scripts/schema.py      # warstwa 1: struktura i formaty (Pydantic)
scripts/layers.py      # warstwy 2-3: ugruntowanie + reguły ról; podział wina dokumentu/modelu
scripts/run_extract.py # pomiar: 2 modele × 2 prompty × 60 faktur, wznawialny
scripts/funnel.py      # lejek oceny: co łapie która warstwa, residuum, fałszywe alarmy
scripts/retry_loop.py  # pętla samokorekty: feedback z zarzutem, pomiar odzysku
data/answer_key.json   # 60 faktur z kluczem (wspólne z agent-team-n8n)
eval/                  # surowe wyniki, lejek, retry
```
