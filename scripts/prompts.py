"""Prompt ekstrakcji z polami-pułapkami.

Uczciwość metodologiczna: prompt JAWNIE pozwala zwrócić null dla pól, których
nie ma na dokumencie. Nie zastawiamy sideł językowych — mierzymy, jak często
model wymyśla wartość MIMO otwartej furtki. Dokładnie tak wyglądają produkcyjne
prompty ekstrakcji (schemat formularza jest szerszy niż pojedynczy dokument).
"""

EXTRACT = """Jestes ekstraktorem danych z polskich faktur. Z ponizszego tekstu faktury
wypelnij formularz i zwroc wylacznie poprawny JSON (bez komentarzy):
{"invoice_number": str (SAM numer, np. "FV/2026/01/0001" - bez slowa FAKTURA),
 "seller_nip": str (same cyfry), "buyer_nip": str (same cyfry),
 "total_net": number, "total_vat": number, "total_gross": number,
 "numer_konta": str | null (numer rachunku bankowego sprzedawcy),
 "rabat": number | null (kwota udzielonego rabatu),
 "wystawil": str | null (imie i nazwisko osoby wystawiajacej fakture),
 "data_zaplaty": str | null (data dokonania zaplaty, RRRR-MM-DD)}

WAZNE: przepisuj wylacznie to, co FAKTYCZNIE jest na dokumencie.
Jesli danego pola nie ma na fakturze - zwroc null. Niczego nie zgaduj,
nie wyliczaj i nie uzupelniaj z wiedzy ogolnej.

FAKTURA:
{ocr}
"""
