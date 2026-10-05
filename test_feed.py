"""Tests zonder netwerk en zonder inlog: pinnen vast wat een B2B-kaart betekent, dat de
feed verder byte voor byte gelijk blijft, dat het inlogformulier compleet is, en dat de rem stopt.

    python -m pytest -q test_feed.py
"""
import re

import pytest

import scraper

# echte kaarten van sales.solgarvitamins.nl/vitamine-d/ (05-10-2026); href/src/value weggelaten
LEVERBAAR = ('<div class="listprod flytobasket favorite " id="prod_0940"><a class="listprod-item">'
             '<div class="listprod-title"><span class="fa fa-fw fa-star"></span> <strong>0940</strong> Cod Liver Oil '
             '(Levertraan) softg.<div class="listprod-pkgunit">100 stuks</div></div><div class="listprod-zi-nut">'
             '<div class="listprod-ean"> EAN 0033984009400</div><div class="listprod-zi"> ZI nr.: 14319446</div>'
             '<div class="listprod-nut"> Nut nr.: AS: 701/38</div></div><div class="listprod-stock"><span class="stock-ok">'
             'Leverbaar <i class="fa fa-check-circle icon-stock-ok"></i></span></div><div class="listprod-prices">'
             '<div class="actualprice"> € 6,04</div></div><div class="listprod-img"><img></div></a>'
             '<div class="list-prod-fav"><button type="submit" name="cmd_AddOneToFavorites_0940"><i class="far fa-heart">'
             '</i></button></div><div class="list-prod-order"><input type="number" min="1" max="100"><button type="submit">'
             '<span class="d-none d-md-inline">Bestel</span> <span class="fa fa-shopping-basket"></span></button></div></div>')
NIET = ('<div class="listprod flytobasket favorite " id="prod_1170"><a class="listprod-item"><div class="listprod-title">'
        '<span class="fa fa-fw fa-star"></span> <strong>1170</strong> Super Cod Liver Oil + Vit D Comp softg.'
        '<div class="listprod-pkgunit">60 stuks</div></div><div class="listprod-zi-nut"><div class="listprod-ean"> '
        'EAN 0033984311701</div><div class="listprod-zi"> ZI nr.: 15586294</div><div class="listprod-nut"> Nut nr.: '
        'AS: 701/49</div></div><div class="listprod-stock"><span class="stock-no">Tijdelijk niet leverbaar '
        '<i class="fa fa-minus-circle"></i></span></div><div class="listprod-prices"><div class="actualprice"> € 11,75'
        '</div></div><div class="listprod-img"><img></div></a><div class="list-prod-fav"><button type="submit" '
        'name="cmd_RemoveFromFavorites_1170"><span class="fas fa-heart"></span></button></div>'
        '<div class="list-prod-order"><small>Verwacht: 2026-11-15</small></div></div>')
UIT_ASS = NIET.replace("1170</strong> Super Cod Liver Oil + Vit D Comp softg.", "3319</strong> UIT ASSORTI Vit D-3 15 µg/600 IU caps.")
PAGINA = ('<script>var _lCustomer = true;</script><div class="artlist"><div class="d-none"><input></div>'
          '<div class="prodlist row">' + LEVERBAAR + NIET + UIT_ASS + '</div></div>'
          '<div class="artlist-nav-block artlist-nav-pages"> Pagina 1 van 2 </div>'
          '<select><option>24</option></select><button>Toepassen</button>')


def test_betekenis_van_een_kaart():
    k = {x["artikel"]: x for x in scraper.lees_kaarten(PAGINA)}
    assert list(k) == ["0940", "1170", "3319"]
    assert k["0940"]["titel"] == "Cod Liver Oil (Levertraan) softg." and k["0940"]["inhoud"] == "100 stuks"
    assert k["0940"]["ean"] == "0033984009400" and k["0940"]["bestelknop"]
    assert k["1170"]["verwacht"] == "2026-11-15" and not k["1170"]["bestelknop"]
    # de laatste kaart van een pagina loopt door tot het einde; de knoppen daar tellen niet
    assert not k["3319"]["bestelknop"]
    assert scraper.oordeel_van(k["0940"]) == "Ja"
    assert scraper.oordeel_van(k["1170"]) == "Nee"
    assert scraper.oordeel_van(k["3319"]) == "Nee"
    assert scraper.reden_van(k["1170"]) == "tijdelijk niet leverbaar, verwacht 2026-11-15"
    assert scraper.reden_van(k["3319"]) == "uit assortiment"
    assert scraper.oordeel_van(None) == "Nee"                 # niet in de B2B (05-10: 3560, 0931)
    # leverbaar-label zonder bestelknop: niet bestelbaar; onbekend label: niet raden
    zonder_knop = scraper.lees_kaarten(LEVERBAAR.replace('<button type="submit"><span class="d-none', '<span class="d-none'))[0]
    assert scraper.oordeel_van(zonder_knop) == "Nee"
    onbekend = scraper.lees_kaarten(LEVERBAAR.replace("stock-ok", "stock-low"))[0]
    assert scraper.oordeel_van(onbekend) is None
    assert scraper.aantal_paginas(PAGINA) == 2
    # &nbsp; tussen "EAN" en het nummer (zo staat het in de browser) leest ook
    assert scraper.lees_kaarten(LEVERBAAR.replace("EAN 0033984009400", "EAN&nbsp;0033984009400"))[0]["ean"] == "0033984009400"


def test_ingelogd():
    assert scraper.ingelogd(PAGINA)
    assert not scraper.ingelogd(PAGINA.replace("true", "false"))
    assert not scraper.ingelogd(PAGINA + '<input type="password" value="" name="txtBIZ_PW" />')


# het inlogformulier van sales.solgarvitamins.nl/login/ (05-10-2026), token ingekort
LOGIN = ('<script>var _lCustomer = false;</script>'
         '<form method="post" action="https://sales.solgarvitamins.nl/default.asp?pageid=52" name="oBIZForm_0" id="oBIZForm_0">'
         '<input type="hidden" name="lastquerystring" value="pageid=52" />'
         '<input type="text" name="txtBIZ_UN" autofocus /><input type="password" value="" name="txtBIZ_PW" />'
         '<input type="checkbox" value="true" name="chkRememberHashLogin" /><button type="submit" name="cmd_login">Inloggen</button>'
         '<input type="hidden" name="dospamcheck" id="dospamcheck_1791208065787" value="true" /></form>'
         '<form method="post" action="https://sales.solgarvitamins.nl/default.asp?pageid=52" name="oBIZForm_1">'
         '<input type="text" name="txt_PasswordResetEmail" value="" />'
         '<input type="hidden" name="dospamcheck" id="dospamcheck_1791208065788" value="true" /></form>'
         '<script type="text/javascript">{ var MPSC=document.createElement("input");MPSC.setAttribute("name","spamcheck");'
         'MPSC.setAttribute("value","spamchecked");MPSC.setAttribute("type","hidden");'
         'document.getElementById("dospamcheck_1791208065787").form.appendChild(MPSC);MPSC=document.createElement("input");'
         'MPSC.setAttribute("name","formauth_90FA8D7242DD2B8");MPSC.setAttribute("value","20261005145000_d5dc.c4f7");'
         'MPSC.setAttribute("type","hidden");document.getElementById("dospamcheck_1791208065787").form.appendChild(MPSC);}</script>'
         '<script type="text/javascript">{ var MPSC=document.createElement("input");MPSC.setAttribute("name","spamcheck");'
         'MPSC.setAttribute("value","spamchecked");MPSC.setAttribute("type","hidden");'
         'document.getElementById("dospamcheck_1791208065788").form.appendChild(MPSC);MPSC=document.createElement("input");'
         'MPSC.setAttribute("name","formauth_14C382CD32FF46C6");MPSC.setAttribute("value","ANDER_FORMULIER");'
         'MPSC.setAttribute("type","hidden");document.getElementById("dospamcheck_1791208065788").form.appendChild(MPSC);}</script>')


def test_inlogformulier_compleet_met_spamcheck():
    actie, velden = scraper.loginformulier(LOGIN)
    assert actie == "https://sales.solgarvitamins.nl/default.asp?pageid=52"
    assert velden == {"lastquerystring": "pageid=52", "dospamcheck": "true", "spamcheck": "spamchecked",
                      "formauth_90FA8D7242DD2B8": "20261005145000_d5dc.c4f7"}     # niet die van het resetformulier
    with pytest.raises(SystemExit):
        scraper.loginformulier("<form><input name='x'></form>")


def test_inloggen_zonder_secrets_stopt(monkeypatch):
    monkeypatch.delenv("SOLGAR_GEBRUIKER", raising=False)
    monkeypatch.delenv("SOLGAR_WACHTWOORD", raising=False)
    with pytest.raises(SystemExit):
        scraper.login(None)


def test_menu():
    pagina = ('<a href="https://sales.solgarvitamins.nl/aminozuren/">Aminozuren</a>'
              '<a href="https://sales.solgarvitamins.nl/info/nieuws/">Nieuws</a>'
              '<a href="https://sales.solgarvitamins.nl/account/favorieten/">Fav</a>'
              '<a href="/nieuwe-categorie/">Nieuw</a><a href="https://sales.solgarvitamins.nl/aminozuren/">dubbel</a>')
    assert scraper.categorieen_uit_menu(pagina) == ["aminozuren", "nieuwe-categorie"]


# ingekort uit www.solgar.nl/xml/solgar-producten (05-10-2026)
FEED = ('<?xml version="1.0" encoding="UTF-8"?><catalog xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><summary>'
        '<uniqueproductcount>2</uniqueproductcount><productvariantcount>3</productvariantcount></summary>'
        '<product><name>Advanced 40+ Acidophilus</name><application_kag>Bevat &#039;vriendelijke&#039; bacteriën.'
        '</application_kag><available_note></available_note><varianten>'
        '<variant><productnumber>0027</productnumber><ean_barcode>033984007482</ean_barcode><amount>60</amount>'
        '<shape>plantaardige capsules</shape><price>35.95</price><available>Ja</available></variant>'
        '<variant><productnumber>0029</productnumber><ean_barcode>033984007383</ean_barcode><amount>120</amount>'
        '<shape>plantaardige capsules</shape><price>64.45</price><available>Nee</available></variant></varianten>'
        '<keywords>probiotica</keywords></product>'
        '<product><name>Advanced Acidophilus Plus</name><varianten><variant><productnumber>0025</productnumber>'
        '<amount>120</amount><price>39.5</price><available>Nee</available></variant></varianten></product></catalog>\n\n')


def test_alleen_available_verandert():
    uit = scraper.pas_toe(FEED, {"0027": "Nee", "0029": "Nee", "0025": "Ja"})
    assert [v["available"] for v in scraper.varianten(uit)] == ["Nee", "Nee", "Ja"]
    weg = lambda t: re.sub(r"<available>[^<]*</available>", "", t)  # noqa: E731
    assert weg(uit) == weg(FEED)                                      # verder byte voor byte gelijk
    assert scraper.pas_toe(FEED, {}) == FEED                          # geen oordeel = Solgars waarde
    assert [(v["artikel"], v["naam"]) for v in scraper.varianten(FEED)] == [
        ("0027", "Advanced 40+ Acidophilus"), ("0029", "Advanced 40+ Acidophilus"), ("0025", "Advanced Acidophilus Plus")]
    assert not scraper.afgekapt(FEED) and scraper.afgekapt(FEED[:-20])


def _b2b(nee=(), weg=(), onbekend=(), n=300):
    k = {}
    for i in range(n):
        a = f"{i:04d}"
        if a in weg:
            continue
        k[a] = {"titel": "x", "voorraad": "stock-x" if a in onbekend else ("stock-no" if a in nee else "stock-ok"),
                "bestelknop": a not in nee, "verwacht": ""}
    return k


def _feed(n=300):
    v = "".join(f"<variant><productnumber>{i:04d}</productnumber><available>Ja</available></variant>" for i in range(n))
    return f"<catalog><product><name>P</name><varianten>{v}</varianten></product></catalog>"


def test_verwerk_en_de_rem():
    nieuw, verschil, telling = scraper.verwerk("solgar", _feed(), 200, _b2b(nee={"0001", "0002"}, weg={"0003"}))
    assert telling == {"Ja": 297, "Nee": 3, None: 0, "niet_gevonden": 1}
    assert [(r["artikelnummer"], r["b2b_ziet"]) for r in verschil] == [
        ("0001", "tijdelijk niet leverbaar"), ("0002", "tijdelijk niet leverbaar"), ("0003", "niet gevonden in de B2B")]
    assert nieuw.count("<available>Nee</available>") == 3
    with pytest.raises(SystemExit):                                   # feed te klein
        scraper.verwerk("solgar", _feed(150), 200, _b2b())
    with pytest.raises(SystemExit):                                   # 20/300 niet gevonden > 5%
        scraper.verwerk("solgar", _feed(), 200, _b2b(weg={f"{i:04d}" for i in range(20)}))
    with pytest.raises(SystemExit):                                   # 20/300 onbepaald > 5%
        scraper.verwerk("solgar", _feed(), 200, _b2b(onbekend={f"{i:04d}" for i in range(20)}))
    with pytest.raises(SystemExit):                                   # 100/300 niet leverbaar > 30%
        scraper.verwerk("solgar", _feed(), 200, _b2b(nee={f"{i:04d}" for i in range(100)}))
    with pytest.raises(SystemExit):                                   # afgebroken
        scraper.verwerk("solgar", _feed()[:-12], 200, _b2b())
    # 05-10 werkelijk: 27 van 226 niet leverbaar (12%) en 2 niet gevonden: gaat door
    scraper.verwerk("solgar", _feed(), 200, _b2b(nee={f"{i:04d}" for i in range(36)}, weg={"0298", "0299"}))
