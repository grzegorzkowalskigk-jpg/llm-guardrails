"""Warstwy bariery ochronnej — czysty, deterministyczny post-processing.

Żadna warstwa NIE zagląda do klucza odpowiedzi. Każda ocenia wyjście modelu
wyłącznie na podstawie: struktury (L1), tekstu źródłowego (L2) i reguł
dziedzinowych (L3). Klucz odpowiedzi służy potem tylko do OCENY warstw
(ile halucynacji złapały, ile przepuściły, ile fałszywych alarmów).

L1 — schemat/typy (Pydantic): struktura, formaty, zakresy.
L2 — ugruntowanie: czy wartość w ogóle WYSTĘPUJE w dokumencie źródłowym.
L3 — reguły ról i spójności: NRB ma 26 cyfr (NIP ma 10 — to nie konto),
     „wystawił" nie może być firmą z dokumentu, „data zapłaty" przepisana
     z terminu płatności to cudza rola, netto+VAT=brutto, suma kontrolna NIP.
"""
from __future__ import annotations

import re

from schema import Extraction

LEGAL_FORMS = ("sp. z o.o", "s.a", "sp.j", "s.c", "sp.k")


def digits(s: object) -> str:
    return re.sub(r"\D", "", str(s or ""))


def norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def nip_checksum_ok(nip: str) -> bool:
    d = digits(nip)
    if len(d) != 10:
        return False
    w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    return sum(a * int(b) for a, b in zip(w, d)) % 11 == int(d[9])


def money_variants(v: float) -> list[str]:
    return [f"{v:.2f}", f"{v:.2f}".replace(".", ","), f"{v:g}"]


# ── L1: schemat ──────────────────────────────────────────────────────────────
def layer1_schema(raw: dict) -> tuple[Extraction | None, list[str]]:
    try:
        return Extraction.model_validate(raw), []
    except Exception as e:  # noqa: BLE001
        msgs = []
        for line in str(e).splitlines():
            line = line.strip()
            if line and not line.startswith(("For further", "Traceback")) and "validation error" not in line:
                msgs.append(line[:90])
        return None, [f"L1/schemat: {m}" for m in msgs[:4]] or ["L1/schemat: odrzucono"]


# ── L2: ugruntowanie w źródle ────────────────────────────────────────────────
def layer2_grounding(ext: Extraction, ocr: str) -> list[str]:
    issues = []
    ocr_low = ocr.lower()
    ocr_digits = digits(ocr)

    def in_doc_str(v: str) -> bool:
        return norm(v) in ocr_low or (digits(v) != "" and digits(v) in ocr_digits)

    def in_doc_money(v: float) -> bool:
        return any(x in ocr for x in money_variants(v))

    for f in ("invoice_number", "seller_nip", "buyer_nip"):
        if not in_doc_str(getattr(ext, f)):
            issues.append(f"L2/grounding: {f} '{getattr(ext, f)}' nie wystepuje w dokumencie")
    for f in ("total_net", "total_vat", "total_gross"):
        if not in_doc_money(getattr(ext, f)):
            issues.append(f"L2/grounding: {f} {getattr(ext, f)} nie wystepuje w dokumencie")

    if ext.numer_konta is not None and digits(ext.numer_konta) not in ocr_digits:
        issues.append(f"L2/grounding: numer_konta '{ext.numer_konta}' nie wystepuje w dokumencie")
    if ext.rabat is not None and not in_doc_money(ext.rabat):
        issues.append(f"L2/grounding: rabat {ext.rabat} nie wystepuje w dokumencie")
    if ext.wystawil is not None and norm(ext.wystawil) not in ocr_low:
        issues.append(f"L2/grounding: wystawil '{ext.wystawil}' nie wystepuje w dokumencie")
    if ext.data_zaplaty is not None and ext.data_zaplaty not in ocr:
        issues.append(f"L2/grounding: data_zaplaty '{ext.data_zaplaty}' nie wystepuje w dokumencie")
    return issues


# ── L3: reguły ról i spójności ───────────────────────────────────────────────
def layer3_rules(ext: Extraction, ocr: str) -> list[str]:
    issues = []

    # numer konta: polski NRB = 26 cyfr; 10 cyfr to NIP, nie konto
    if ext.numer_konta is not None:
        d = digits(ext.numer_konta)
        if len(d) != 26:
            issues.append(f"L3/rola: numer_konta ma {len(d)} cyfr (NRB ma 26) - to nie numer rachunku")
        if d and (d == digits(ext.seller_nip) or d == digits(ext.buyer_nip)):
            issues.append("L3/rola: numer_konta identyczny z NIP - pomylone role pol")

    # wystawil: firma z dokumentu to nie osoba wystawiajaca
    if ext.wystawil is not None:
        w = norm(ext.wystawil)
        if any(form in w for form in LEGAL_FORMS):
            issues.append(f"L3/rola: wystawil '{ext.wystawil}' to firma (forma prawna), nie osoba")
        else:
            # nazwa firmy z dokumentu (linia po SPRZEDAWCA/NABYWCA) uzyta jako osoba
            m = re.findall(r"(?:SPRZEDAWCA|NABYWCA):\s*\n\s*(.+)", ocr)
            if any(norm(x) == w for x in m):
                issues.append(f"L3/rola: wystawil '{ext.wystawil}' to strona transakcji, nie osoba wystawiajaca")

    # data zaplaty: przepisana z innej roli (termin platnosci / daty faktury)
    if ext.data_zaplaty is not None:
        roles = dict(re.findall(r"(Data wystawienia|Data sprzedazy|Termin platnosci):\s*(\d{4}-\d{2}-\d{2})", ocr))
        for role, date in roles.items():
            if ext.data_zaplaty == date:
                issues.append(f"L3/rola: data_zaplaty przepisana z pola '{role}' - dokument nie zawiera daty zaplaty")
                break

    # rabat: absurd kwotowy
    if ext.rabat is not None and ext.rabat > ext.total_net:
        issues.append("L3/spojnosc: rabat wiekszy niz suma netto")

    # spojnosc kwot i NIP-ow (dotyczy pol prawdziwych)
    if abs(ext.total_net + ext.total_vat - ext.total_gross) > 0.02:
        issues.append("L3/spojnosc: netto + VAT != brutto")
    for f in ("seller_nip", "buyer_nip"):
        if not nip_checksum_ok(getattr(ext, f)):
            issues.append(f"L3/spojnosc: {f} ma bledna sume kontrolna")
    return issues


def run_layers(raw: dict, ocr: str) -> dict:
    """Pełna bariera: zwraca ekstrakcję (lub None) + problemy per warstwa."""
    ext, l1 = layer1_schema(raw)
    if ext is None:
        return {"ext": None, "l1": l1, "l2": [], "l3": [], "ok": False}
    l2 = layer2_grounding(ext, ocr)
    l3 = layer3_rules(ext, ocr)
    return {"ext": ext, "l1": l1, "l2": l2, "l3": l3, "ok": not (l1 or l2 or l3)}
