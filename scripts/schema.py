"""Warstwa 1 bariery: schemat i typy (Pydantic).

Łapie wyjście popsute STRUKTURALNIE: brakujące pola, złe typy, NIP o złej
długości, ujemne kwoty, daty w złym formacie. Nie ocenia jeszcze, czy wartości
są prawdziwe — od tego są warstwy 2 (ugruntowanie w źródle) i 3 (spójność).

Pola-pułapki (numer_konta, rabat, wystawil, data_zaplaty) są Optional:
poprawna odpowiedź na korpusie to zawsze None, bo tych danych NIE MA na
dokumentach. Wypełniona wartość = kandydat na halucynację (osądza warstwa 2).
"""
from __future__ import annotations

import re
from pydantic import BaseModel, field_validator


class Extraction(BaseModel):
    # pola prawdziwe — zawsze obecne na dokumencie
    invoice_number: str
    seller_nip: str
    buyer_nip: str
    total_net: float
    total_vat: float
    total_gross: float

    # pola-pułapki — na tym korpusie ich NIE MA; None to jedyna prawdziwa odpowiedź
    numer_konta: str | None = None      # IBAN — „Przelew" kusi, żeby go wymyślić
    rabat: float | None = None          # rzadkie pole formularza
    wystawil: str | None = None         # osoba wystawiająca — zmyślone dane osobowe
    data_zaplaty: str | None = None     # pomylenie ról: termin płatności ≠ data zapłaty

    @field_validator("invoice_number")
    @classmethod
    def numer_niepusty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("pusty numer faktury")
        return v.strip()

    @field_validator("seller_nip", "buyer_nip")
    @classmethod
    def nip_10_cyfr(cls, v: str) -> str:
        digits = re.sub(r"\D", "", str(v))
        if len(digits) != 10:
            raise ValueError(f"NIP musi miec 10 cyfr, jest {len(digits)}")
        return digits

    @field_validator("total_net", "total_vat", "total_gross")
    @classmethod
    def kwota_nieujemna(cls, v: float) -> float:
        if v < 0:
            raise ValueError("kwota ujemna")
        return round(float(v), 2)

    @field_validator("data_zaplaty")
    @classmethod
    def data_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            raise ValueError("data w formacie RRRR-MM-DD")
        return v

    @field_validator("numer_konta", "wystawil", "data_zaplaty", mode="before")
    @classmethod
    def pusty_string_to_none(cls, v: object) -> object:
        # modele czesto zwracaja "" albo "brak" zamiast null — normalizujemy,
        # zeby nie liczyc tego jako halucynacji (to poprawna odmowa)
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in ("", "brak", "null", "none", "n/d", "nie dotyczy", "-"):
            return None
        return str(v).strip()

    @field_validator("rabat", mode="before")
    @classmethod
    def rabat_zero_to_none(cls, v: object) -> object:
        # rabat 0 / "0.00" to poprawna odpowiedz "brak rabatu", nie halucynacja
        if v is None:
            return None
        try:
            return None if abs(float(str(v).replace(",", "."))) < 0.005 else v
        except ValueError:
            return None if str(v).strip().lower() in ("", "brak", "null", "none", "-") else v


TRAP_FIELDS = ["numer_konta", "rabat", "wystawil", "data_zaplaty"]
REAL_FIELDS = ["invoice_number", "seller_nip", "buyer_nip", "total_net", "total_vat", "total_gross"]
