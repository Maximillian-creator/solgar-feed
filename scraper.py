"""
Solgar + Viridian — update-feeds met de échte beschikbaarheid uit de B2B
========================================================================
Solgar publiceert zelf twee feeds (www.solgar.nl/xml/solgar-producten en
/xml/viridian-producten), maar `<available>` daarin klopt niet. Gemeten op 05-10-2026 tegen
de eigen B2B (sales.solgarvitamins.nl): van de 26 Solgar-producten die de B2B niet kan
leveren, stonden er 12 in de feed op "Ja" (waaronder één uit assortiment). Van de 6 bij
Viridian waren het er 2. De feed veranderde van 30-09 tot 05-10 geen enkele
beschikbaarheid. Stock Sync zet "Ja" om in doorverkopen, dus klanten bestelden wat niet
kwam. Zie _bouwplannen/_verkenning/solgar-b2b-vs-feed-2026-10-05.md in het projectmap.

Deze feeds zijn Solgars eigen feeds, byte voor byte. Alleen `<available>` wordt per
variant overschreven met wat de B2B nú laat zien. Stock Sync hoeft dus alleen een andere
URL te lezen: de koppeling blijft gelijk.

    B2B toont (categoriepagina)                      → available
    "Leverbaar" (span.stock-ok) + Bestel-knop        →  Ja
    "Tijdelijk niet leverbaar" (span.stock-no)       →  Nee
    "UIT ASSORTI..." in de titel                     →  Nee
    artikelnummer staat nergens in de B2B            →  Nee   (05-10: 3560, 0931 — Solgar voert ze niet meer)
    iets anders (onbekende klasse)                   →  Solgars eigen waarde blijft, en telt als onbepaald

De B2B toont per categoriepagina alle producten met hun status. Eén ronde = ~18
pagina's (17 categorieën, 96 per pagina), geen 400 productpagina's. De pagina
"Voorraad informatie" is NIET volledig (05-10: 23 in plaats van 27); hij wordt alleen als extra bron
meegelezen.

Inloggen gebeurt met SOLGAR_GEBRUIKER en SOLGAR_WACHTWOORD (GitHub-secrets, door Max
ingevuld). Het wachtwoord wordt nergens gelogd of weggeschreven. B2B-prijzen (inkoop)
komen nooit in de feed: alleen `<available>` verandert.

REM (les van 31-08: een halve feed laat Stock Sync producten archiveren). Per feed wordt
niets weggeschreven als:
  - Solgars feed afgebroken is of te weinig varianten heeft;
  - inloggen mislukt, of de B2B minder dan MIN_B2B producten toont;
  - > 5% van de varianten niet in de B2B staat (normaal ~1%: dan klopt het lezen niet);
  - > 5% onbepaald is;
  - > 30% niet leverbaar zou worden (normaal ~12%).
"""
from __future__ import annotations

import csv
import html
import json
import os
import subprocess
import re
import sys
import time

import requests

B2B = "https://sales.solgarvitamins.nl"
LOGIN_PAD = "/login/"
FEEDS = {
    # naam: (bron-URL, uitvoerbestand, minimum aantal varianten)
    "solgar":   (os.environ.get("SOLGAR_FEED_URL", "https://www.solgar.nl/xml/solgar-producten"), "solgar_feed.xml", 180),
    "viridian": (os.environ.get("VIRIDIAN_FEED_URL", "https://www.solgar.nl/xml/viridian-producten"), "viridian_feed.xml", 140),
}
VERSCHILLEN_FILE = "verschillen.csv"

# 05-10-2026: 17 categorieën in het menu. De lijst wordt bij elke run ook uit het menu van
# de B2B gehaald; deze vaste lijst vangt op als dat menu anders wordt opgebouwd.
CATEGORIEEN = ["aminozuren", "vitamine-a", "vitamine-d", "vitamine-b", "vitamine-c", "vitamine-e", "vitamine-k",
               "mineralen", "anti-oxidanten", "caroteen", "multivitaminen", "spijsvertering", "essentiele-vetzuren",
               "speciale-supplementen", "kruiden", "superfoods", "tincturen"]
EXTRA_PAGINAS = ["assortiment/voorraad-informatie"]
GEEN_CATEGORIE = {"info", "account", "besteltraject", "assortiment", "login", "default.asp"}

MIN_B2B = 300                 # 05-10: 405 producten (225 Solgar + 180 Viridian)
MAX_NIET_GEVONDEN_PCT = 5
MAX_ONBEPAALD_PCT = 5
MAX_NIET_LEVERBAAR_PCT = 30
PAUZE_S = 0.8
UA = "Mozilla/5.0 (GoodForYou voorraadfeed; klant van Solgar Vitamins)"

_VARIANT = re.compile(r"<variant>.*?</variant>", re.S)
_KAART = re.compile(r'<div[^>]*\bclass="listprod[ "]')


# ── Solgars eigen feed ───────────────────────────────────────────────────────

def haal_feed(url: str) -> str:
    r = requests.get(url, timeout=120, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.content.decode("utf-8")


# ── noodroute (22-10-2026) ───────────────────────────────────────────────────
# Sinds 19-10 geeft www.solgar.nl een 403 aan datacenter-adressen (GitHub-runners en de VPS),
# terwijl de B2B gewoon bereikbaar is. Drie dagen lang las Stock Sync daardoor een feed van 18-10.
# Noodroute: lukt het ophalen van Solgars feed niet, dan is de laatst weggeschreven feed de basis
# en wordt alleen `<available>` opnieuw uit de B2B gezet. Prijzen en assortiment wachten dan tot
# solgar.nl weer open is; Nebula blijft dat melden. `basis.json` onthoudt wanneer de basis voor het
# laatst écht bij Solgar vandaan kwam, zodat de noodroute na NOODROUTE_MAX_DAGEN stopt in plaats van
# stilletjes op een stokoude basis door te draaien.

BASIS_STEMPEL = "basis.json"
NOODROUTE_MAX_DAGEN = 14


def _lees_stempel() -> dict:
    try:
        with open(BASIS_STEMPEL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _schrijf_stempel(stempel: dict) -> None:
    with open(BASIS_STEMPEL, "w", encoding="utf-8", newline="") as f:
        json.dump(stempel, f, indent=1, sort_keys=True)
        f.write("\n")


def _git_tijd(bestand: str) -> float | None:
    """Wanneer het bestand voor het laatst gecommit is (voor de eerste noodroute, zonder stempel)."""
    try:
        uit = subprocess.run(["git", "log", "-1", "--format=%ct", "--", bestand],
                             capture_output=True, text=True, timeout=30)
        return float(uit.stdout.strip()) if uit.returncode == 0 and uit.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def basis_leeftijd_dagen(naam: str, bestand: str, nu: float | None = None) -> float | None:
    """Hoe oud de laatste échte Solgar-basis is: uit de stempel, anders uit git. None = onbekend."""
    nu = nu or time.time()
    stempel = _lees_stempel().get(naam)
    if stempel:
        try:
            t = time.mktime(time.strptime(stempel, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
            return (nu - t) / 86400
        except ValueError:
            pass
    t = _git_tijd(bestand)
    return (nu - t) / 86400 if t else None


def basis_feed(naam: str, url: str, bestand: str, nu: float | None = None) -> tuple[str, str]:
    """De basis voor één merk: Solgars feed, of via de noodroute onze laatste versie.
    Geeft (xml, bron). Gooit SystemExit als er geen betrouwbare basis is."""
    try:
        xml = haal_feed(url)
    except requests.RequestException as e:
        fout = str(e)[:120]
    else:
        stempel = _lees_stempel()
        stempel[naam] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(nu or time.time()))
        _schrijf_stempel(stempel)
        return xml, "solgar.nl"
    stempel = _lees_stempel()
    if naam not in stempel:
        # eerste noodroute zonder stempel: de commit-tijd van het bestand is de laatste echte basis;
        # vastleggen, anders schuift die datum bij elke noodroute-commit mee en stopt de grens nooit
        t = _git_tijd(bestand)
        if t:
            stempel[naam] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
            _schrijf_stempel(stempel)
    leeftijd = basis_leeftijd_dagen(naam, bestand, nu)
    print(f"NOODROUTE {naam}: Solgars feed niet op te halen ({fout}).", file=sys.stderr)
    if leeftijd is None:
        raise SystemExit(f"STOP {naam}: noodroute niet mogelijk, ouderdom van {bestand} onbekend "
                         f"(geen {BASIS_STEMPEL}, geen git). Geen feed weggeschreven.")
    if leeftijd > NOODROUTE_MAX_DAGEN:
        raise SystemExit(f"STOP {naam}: noodroute gestopt, de laatste echte Solgar-basis is {leeftijd:.0f} dagen "
                         f"oud (grens {NOODROUTE_MAX_DAGEN}). Solgar.nl moet weer open; geen feed weggeschreven.")
    try:
        with open(bestand, encoding="utf-8") as f:
            xml = f.read()
    except OSError:
        raise SystemExit(f"STOP {naam}: noodroute niet mogelijk, {bestand} ontbreekt. Geen feed weggeschreven.")
    if afgekapt(xml):
        raise SystemExit(f"STOP {naam}: noodroute niet mogelijk, {bestand} is afgebroken. Geen feed weggeschreven.")
    print(f"NOODROUTE {naam}: basis = onze {bestand}, Solgar-basis van {leeftijd:.1f} dagen oud; "
          f"alleen <available> wordt uit de B2B ververst.", file=sys.stderr)
    return xml, f"noodroute ({leeftijd:.1f} d)"


def _veld(blok: str, naam: str) -> str:
    m = re.search(rf"<{naam}>([^<]*)</{naam}>", blok)
    return html.unescape(m.group(1).strip()) if m else ""


def varianten(xml: str) -> list[dict]:
    """Elke variant met zijn productnaam (de naam staat op het product, niet op de variant)."""
    uit = []
    for product in re.findall(r"<product>.*?</product>", xml, re.S):
        naam = _veld(product, "name")
        for v in _VARIANT.findall(product):
            uit.append({"artikel": _veld(v, "productnumber"), "naam": naam, "inhoud": _veld(v, "amount"),
                        "available": _veld(v, "available")})
    return uit


def afgekapt(xml: str) -> bool:
    return not xml.rstrip().endswith("</catalog>")


def pas_toe(xml: str, oordeel: dict[str, str]) -> str:
    """Vervang per variant alleen `<available>`; de rest blijft byte voor byte."""
    def een(m: re.Match) -> str:
        blok = m.group(0)
        nieuw = oordeel.get(_veld(blok, "productnumber"))
        if nieuw is None:
            return blok
        return re.sub(r"<available>[^<]*</available>", f"<available>{nieuw}</available>", blok, count=1)
    return _VARIANT.sub(een, xml)


# ── de B2B: inloggen ─────────────────────────────────────────────────────────

def ingelogd(pagina: str) -> bool:
    """De B2B zet in elke pagina `var _lCustomer = true|false;`. Zonder inlog stuurt hij
    door naar /login/ (05-10), met het formulier txtBIZ_PW."""
    return bool(re.search(r"_lCustomer\s*=\s*true", pagina)) and 'name="txtBIZ_PW"' not in pagina


def loginformulier(pagina: str) -> tuple[str, dict]:
    """Actie en velden van het inlogformulier, zoals de browser ze verstuurt.

    Het platform (IBVision) voegt met een inline script twee verborgen velden toe aan het
    formulier van `dospamcheck_<id>`: `spamcheck=spamchecked` en `formauth_<X>=<token>`.
    Zonder die twee wijst de B2B de login af als spam."""
    for form in re.findall(r"<form\b.*?</form>", pagina, re.S | re.I):
        if 'name="txtBIZ_PW"' not in form:
            continue
        actie = html.unescape(re.search(r'action="([^"]*)"', form).group(1))
        velden = {}
        for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', form):
            naam, waarde = re.search(r'name="([^"]+)"', tag), re.search(r'value="([^"]*)"', tag)
            if naam:
                velden[naam.group(1)] = html.unescape(waarde.group(1)) if waarde else ""
        spam = re.search(r'id="(dospamcheck_[^"]+)"', form)
        if spam:
            for script in re.findall(r"<script[^>]*>(.*?)</script>", pagina, re.S | re.I):
                if f'getElementById("{spam.group(1)}")' not in script:
                    continue
                for naam, waarde in re.findall(r'setAttribute\("name","([^"]+)"\);\s*\w+\.setAttribute\("value","([^"]*)"\)',
                                               script):
                    velden[naam] = waarde
        return actie, velden
    raise SystemExit("STOP: geen inlogformulier (txtBIZ_PW) op de loginpagina van de B2B; is de site veranderd?")


def login(sessie: requests.Session) -> None:
    gebruiker, wachtwoord = os.environ.get("SOLGAR_GEBRUIKER"), os.environ.get("SOLGAR_WACHTWOORD")
    if not gebruiker or not wachtwoord:
        raise SystemExit("STOP: SOLGAR_GEBRUIKER / SOLGAR_WACHTWOORD ontbreken (GitHub-secrets).")
    pagina = sessie.get(B2B + LOGIN_PAD, timeout=60).text
    if ingelogd(pagina):
        return
    actie, velden = loginformulier(pagina)
    velden.update({"txtBIZ_UN": gebruiker, "txtBIZ_PW": wachtwoord, "cmd_login": ""})
    antwoord = sessie.post(actie, data=velden, timeout=60)
    if ingelogd(antwoord.text) or ingelogd(sessie.get(B2B + "/", timeout=60).text):
        return
    # wat de B2B zelf zegt, zonder inloggegevens: het log van een publieke repo is openbaar
    meldingen = {m.strip() for m in re.findall(r"(?i)[^<>]{0,80}(?:onjuist|ongeldig|geblokkeerd|verlopen|"
                                                r"mislukt|incorrect|invalid|locked)[^<>]{0,80}", antwoord.text)
                 if gebruiker not in m}
    print(f"Antwoord van de B2B op de login: HTTP {antwoord.status_code}, {antwoord.url.replace(B2B, '')[:60]}")
    for m in sorted(meldingen)[:6]:
        print(f"  B2B zegt: {html.unescape(m)[:200]}")
    raise SystemExit("STOP: inloggen op de B2B mislukt (gebruiker/wachtwoord of loginpagina veranderd). "
                     "Geen feed weggeschreven.")


# ── de B2B: lezen ────────────────────────────────────────────────────────────

def _tekst(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def lees_kaarten(pagina: str) -> list[dict]:
    """De productkaarten van een categoriepagina (zie test_feed.py voor een echt voorbeeld)."""
    starts = [m.start() for m in _KAART.finditer(pagina)]
    uit = []
    for i, s in enumerate(starts):
        kaart = pagina[s:starts[i + 1] if i + 1 < len(starts) else len(pagina)]
        art = re.search(r"<strong>\s*(V?\d{3,6})\s*</strong>", kaart)
        if not art:
            continue
        titel = re.search(r"</strong>(.*?)<div[^>]*listprod-pkgunit", kaart, re.S)
        inhoud = re.search(r'listprod-pkgunit[^>]*>(.*?)</div>', kaart, re.S)
        ean = re.search(r"EAN\s*(?:&nbsp;|\s)*(\d{8,14})", kaart)
        klasse = re.search(r'class="(stock-[a-z-]+)"', kaart)
        verwacht = re.search(r"Verwacht:\s*(?:&nbsp;|\s)*([0-9-]{8,10})", kaart)
        # alleen binnen het bestelblok kijken: de hartjesknop (favorieten) staat ervoor, en na
        # de laatste kaart van een pagina volgen nog knoppen van de pagina zelf
        bestelblok = re.search(r'class="list-prod-order"[^>]*>(.*?)</div>', kaart, re.S)
        bestel = bool(bestelblok and "<button" in bestelblok.group(1))
        uit.append({"artikel": art.group(1), "titel": _tekst(titel.group(1)) if titel else "",
                    "inhoud": _tekst(inhoud.group(1)) if inhoud else "", "ean": ean.group(1) if ean else "",
                    "voorraad": klasse.group(1) if klasse else "", "bestelknop": bestel,
                    "verwacht": verwacht.group(1) if verwacht else ""})
    return uit


def aantal_paginas(pagina: str) -> int:
    m = re.search(r"Pagina\s*\d+\s*van\s*(\d+)", _tekst(pagina))
    return int(m.group(1)) if m else 1


def oordeel_van(k: dict | None) -> str | None:
    """'Ja', 'Nee', of None = onbepaald (dan blijft Solgars eigen waarde staan)."""
    if k is None:
        return "Nee"                      # niet in de B2B: Solgar voert hem niet (meer)
    if "UIT ASSORTI" in k["titel"].upper():
        return "Nee"
    if k["voorraad"] == "stock-no":
        return "Nee"
    if k["voorraad"] == "stock-ok":
        return "Ja" if k["bestelknop"] else "Nee"
    return None


def reden_van(k: dict | None) -> str:
    if k is None:
        return "niet gevonden in de B2B"
    if "UIT ASSORTI" in k["titel"].upper():
        return "uit assortiment"
    if k["voorraad"] == "stock-no":
        return "tijdelijk niet leverbaar" + (f", verwacht {k['verwacht']}" if k["verwacht"] else "")
    if k["voorraad"] == "stock-ok":
        return "leverbaar" if k["bestelknop"] else "leverbaar, maar geen bestelknop"
    return f"onbekend ({k['voorraad'] or 'geen voorraadlabel'})"


def categorieen_uit_menu(pagina: str) -> list[str]:
    gevonden = []
    for pad in re.findall(r'href="(?:https://sales\.solgarvitamins\.nl)?/([a-z0-9-]+)/"', pagina):
        if pad not in GEEN_CATEGORIE and pad not in gevonden:
            gevonden.append(pad)
    return gevonden


def _haal(sessie: requests.Session, pad: str, start: int) -> requests.Response | None:
    for poging in range(3):
        try:
            r = sessie.get(f"{B2B}/{pad}/", params={"artmaxcount": 96, "alstart": start}, timeout=60)
            if r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            return r
        except requests.RequestException:
            time.sleep(3 * (poging + 1))
    return None


def lees_b2b(sessie: requests.Session) -> dict[str, dict]:
    voorpagina = sessie.get(B2B + "/", timeout=60).text
    paden = list(dict.fromkeys(CATEGORIEEN + categorieen_uit_menu(voorpagina)))[:40] + EXTRA_PAGINAS
    alles: dict[str, dict] = {}
    opnieuw_ingelogd = False
    for pad in paden:
        start, pagina_nr, paginas, gelezen = 0, 0, 1, 0
        while pagina_nr < paginas:
            r = _haal(sessie, pad, start)
            if r is None or r.status_code == 404:
                print(f"  {pad}: niet te lezen ({'404' if r is not None else 'netwerk'})")
                break
            if not ingelogd(r.text):
                if opnieuw_ingelogd:
                    raise SystemExit("STOP: de B2B-sessie valt steeds weg. Geen feed weggeschreven.")
                login(sessie)            # sessie verlopen: één keer opnieuw (stopt hard als dat mislukt)
                opnieuw_ingelogd = True
                continue
            kaarten = lees_kaarten(r.text)
            for k in kaarten:
                alles.setdefault(k["artikel"], k)
            gelezen += len(kaarten)
            paginas = aantal_paginas(r.text)
            pagina_nr += 1
            start += 96
            time.sleep(PAUZE_S)
        if gelezen:
            print(f"  {pad}: {gelezen} producten (totaal nu {len(alles)})")
    return alles


# ── samen ────────────────────────────────────────────────────────────────────

def keur(naam: str, n_feed: int, minimum: int, oordeel: dict[str, str | None], niet_gevonden: int) -> None:
    """De rem voor één feed. Gooit SystemExit en dan wordt die feed niet weggeschreven."""
    if n_feed < minimum:
        raise SystemExit(f"STOP {naam}: Solgars feed heeft maar {n_feed} varianten (ondergrens {minimum}).")
    if niet_gevonden * 100 > MAX_NIET_GEVONDEN_PCT * n_feed:
        raise SystemExit(f"STOP {naam}: {niet_gevonden} van {n_feed} varianten niet in de B2B gevonden "
                         f"(grens {MAX_NIET_GEVONDEN_PCT}%, normaal ~1%). Waarschijnlijk klopt het lezen niet.")
    onbepaald = sum(1 for o in oordeel.values() if o is None)
    if onbepaald * 100 > MAX_ONBEPAALD_PCT * n_feed:
        raise SystemExit(f"STOP {naam}: {onbepaald} van {n_feed} varianten onbepaald (grens {MAX_ONBEPAALD_PCT}%).")
    nee = sum(1 for o in oordeel.values() if o == "Nee")
    if nee * 100 > MAX_NIET_LEVERBAAR_PCT * n_feed:
        raise SystemExit(f"STOP {naam}: {nee} van {n_feed} zouden niet leverbaar worden (grens "
                         f"{MAX_NIET_LEVERBAAR_PCT}%, normaal ~12%). Waarschijnlijk klopt het lezen niet.")


def verwerk(naam: str, xml: str, minimum: int, b2b: dict[str, dict]) -> tuple[str, list[dict], dict]:
    """Nieuwe feed + verschillenlijst voor één merk. Gooit SystemExit via de rem."""
    if afgekapt(xml):
        raise SystemExit(f"STOP {naam}: Solgars feed is afgebroken (</catalog> ontbreekt).")
    lijst = varianten(xml)
    oordeel = {v["artikel"]: oordeel_van(b2b.get(v["artikel"])) for v in lijst}
    niet_gevonden = sum(1 for v in lijst if v["artikel"] not in b2b)
    keur(naam, len(lijst), minimum, oordeel, niet_gevonden)
    verschil = []
    for v in lijst:
        o = oordeel[v["artikel"]]
        if o is not None and o != v["available"]:
            verschil.append({"merk": naam, "artikelnummer": v["artikel"], "product": v["naam"], "inhoud": v["inhoud"],
                             "solgar_feed": v["available"], "b2b": o, "b2b_ziet": reden_van(b2b.get(v["artikel"]))})
    telling = {"Ja": 0, "Nee": 0, None: 0}
    for o in oordeel.values():
        telling[o] += 1
    telling["niet_gevonden"] = niet_gevonden
    return pas_toe(xml, {a: o for a, o in oordeel.items() if o is not None}), verschil, telling


def main() -> None:
    start = time.time()
    print("Solgar + Viridian UPDATE-feeds (beschikbaarheid uit de B2B) gestart\n")
    feeds, bronnen, fouten = {}, {}, []
    for naam, (url, bestand, _) in FEEDS.items():
        try:
            feeds[naam], bronnen[naam] = basis_feed(naam, url, bestand)
        except SystemExit as e:
            print(e, file=sys.stderr)
            fouten.append(naam)
    if not feeds:
        raise SystemExit("STOP: geen enkele basis (Solgar noch noodroute). Geen feed weggeschreven.")
    sessie = requests.Session()
    sessie.headers["User-Agent"] = UA
    login(sessie)
    print("Ingelogd op de B2B")
    b2b = lees_b2b(sessie)
    print(f"B2B: {len(b2b)} producten gelezen")
    if len(b2b) < MIN_B2B:
        raise SystemExit(f"STOP: de B2B toont maar {len(b2b)} producten (ondergrens {MIN_B2B}). Geen feed weggeschreven.")
    verschillen = []
    for naam, (_, bestand, minimum) in FEEDS.items():
        if naam not in feeds:
            continue
        try:
            nieuw, verschil, telling = verwerk(naam, feeds[naam], minimum, b2b)
        except SystemExit as e:
            print(e, file=sys.stderr)
            fouten.append(naam)
            continue
        with open(bestand, "w", encoding="utf-8", newline="") as f:
            f.write(nieuw)
        verschillen += verschil
        print(f"{naam}: {telling['Ja']} Ja, {telling['Nee']} Nee (waarvan {telling['niet_gevonden']} niet in de B2B), "
              f"{telling[None]} onbepaald → {bestand}; {len(verschil)} anders dan de basis ({bronnen[naam]})")
    if not fouten:
        with open(VERSCHILLEN_FILE, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["merk", "artikelnummer", "product", "inhoud", "solgar_feed", "b2b", "b2b_ziet"])
            w.writeheader()
            w.writerows(sorted(verschillen, key=lambda r: (r["merk"], r["artikelnummer"])))
    print(f"\nKlaar in {time.time() - start:.0f}s")
    print("Feed-URL's voor Stock Sync:")
    for _, bestand, _ in FEEDS.values():
        print(f"  https://raw.githubusercontent.com/Maximillian-creator/solgar-feed/main/{bestand}")
    if fouten:
        raise SystemExit(f"STOP: {', '.join(fouten)} niet weggeschreven (de rem). De vorige versie blijft staan.")


if __name__ == "__main__":
    main()
