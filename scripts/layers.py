"""EN: Guard layers - deterministic post-processing of model output. No layer
sees the answer key: L1 checks structure, L2 grounding in the source text,
L3 domain rules.
PL: Warstwy bariery - deterministyczny post-processing wyjscia modelu. Zadna
warstwa nie zaglada do klucza: L1 sprawdza strukture, L2 ugruntowanie
w tekscie zrodlowym, L3 reguly dziedzinowe.
"""
from __future__ import annotations

import re

from schema import Extraction

LEGAL_FORMS = ("sp. z o.o", "s.a", "sp.j", "s.c", "sp.k")


def digits(s: object) -> str:
    """EN: Keeps digits only. / PL: Zostawia same cyfry."""
    return re.sub(r"\D", "", str(s or ""))


def norm(s: object) -> str:
    """EN: Normalises a value for comparison. / PL: Normalizuje wartosc do porownania."""
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def nip_checksum_ok(nip: str) -> bool:
    """EN: Validates a tax id checksum. / PL: Sprawdza cyfre kontrolna NIP-u."""
    d = digits(nip)
    if len(d) != 10:
        return False
    w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    return sum(a * int(b) for a, b in zip(w, d)) % 11 == int(d[9])


def money_variants(v: float) -> list[str]:
    """EN: Returns the common textual forms of an amount.
    PL: Zwraca typowe zapisy tekstowe kwoty.
    """
    return [f"{v:.2f}", f"{v:.2f}".replace(".", ","), f"{v:g}"]


# ── L1: schemat ──────────────────────────────────────────────────────────────
def layer1_schema(raw: dict) -> tuple[Extraction | None, list[str]]:
    """EN: Validates raw output against the schema.
    PL: Waliduje surowe wyjscie wobec schematu.
    """
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
    """EN: Checks each extracted value appears in the source document.
    PL: Sprawdza, czy kazda wyciagnieta wartosc wystepuje w dokumencie.
    """
    issues = []
    ocr_low = ocr.lower()
    ocr_digits = digits(ocr)

    def in_doc_str(v: str) -> bool:
        """EN: Checks a string appears in the document.
        PL: Sprawdza, czy napis wystepuje w dokumencie.
        """
        return norm(v) in ocr_low or (digits(v) != "" and digits(v) in ocr_digits)

    def in_doc_money(v: float) -> bool:
        """EN: Checks an amount appears in the document in any common form.
        PL: Sprawdza, czy kwota wystepuje w dokumencie w dowolnym typowym zapisie.
        """
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
    """EN: Applies domain rules (arithmetic, dates, roles).
    PL: Stosuje reguly dziedzinowe (arytmetyka, daty, role).
    """
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
            # nazwa firmy z dokumentu (linia po SPRZEDAWCA/NABYWCA) uzyta jako osoba —
            # takze SKROCONA (iteracja #1: 'Nowak i Wspolnicy' z 'Kancelaria Nowak
            # i Wspolnicy' przechodzilo, bo nie rownalo sie DOKLADNIE nazwie strony);
            # regula: wszystkie tokeny 'wystawil' zawieraja sie w nazwie strony
            m = re.findall(r"(?:SPRZEDAWCA|NABYWCA):\s*\n\s*(.+)", ocr)
            for x in m:
                party = set(norm(x).split())
                tokens = set(w.split())
                if tokens and tokens <= party:
                    issues.append(f"L3/rola: wystawil '{ext.wystawil}' to (skrocona) nazwa strony transakcji, nie osoba")
                    break

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


def issue_class(issue: str) -> str:
    """EN: Splits blame between a document defect and a model error.
    PL: Rozdziela wine miedzy wade dokumentu a blad modelu.
    """
    return "defect" if issue.startswith("L3/spojnosc") else "model"


def run_layers(raw: dict, ocr: str) -> dict:
    """EN: Runs all layers; returns the extraction (or None) and issues per layer.
    PL: Uruchamia wszystkie warstwy; zwraca ekstrakcje (lub None) i problemy per warstwa.
    """
    ext, l1 = layer1_schema(raw)
    if ext is None:
        return {"ext": None, "l1": l1, "l2": [], "l3": [], "ok": False}
    l2 = layer2_grounding(ext, ocr)
    l3 = layer3_rules(ext, ocr)
    return {"ext": ext, "l1": l1, "l2": l2, "l3": l3, "ok": not (l1 or l2 or l3)}
