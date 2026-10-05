# Solgar + Viridian feeds → Stock Sync (met de beschikbaarheid uit de B2B)

Solgar publiceert zelf twee feeds: `www.solgar.nl/xml/solgar-producten` en
`/xml/viridian-producten`. Het veld `<available>` daarin klopt niet met hun eigen B2B
(`sales.solgarvitamins.nl`). Op 05-10-2026 is dat product voor product nagekeken:
- Van de **26 Solgar-producten** die de B2B niet kan leveren, stonden er **12** in de feed op
  "Ja". Een daarvan is uit het assortiment.
- Bij **Viridian** waren het **2 van de 6**.
- Tussen 30-09 en 05-10 veranderde in de feed geen enkele beschikbaarheid.

Stock Sync zet "Ja" om in doorverkopen. Klanten bestelden dus wat niet kwam.

Deze repo maakt betere feeds. Het zijn Solgars eigen feeds, **byte voor byte**. Alleen
`<available>` wordt per variant vervangen door wat de B2B nu laat zien. Stock Sync hoeft dus
alleen een andere URL te lezen: de koppeling blijft gelijk.

| B2B toont (categoriepagina) | available |
|---|---|
| "Leverbaar" + knop Bestel | Ja |
| "Tijdelijk niet leverbaar" | Nee |
| "UIT ASSORTI…" in de titel | Nee |
| artikelnummer staat nergens in de B2B | Nee |

Een ronde leest 17 categoriepagina's plus "Voorraad informatie", met 96 producten per pagina.
Dat zijn ~18 verzoeken en duurt ongeveer een halve minuut.

**Nooit in de feed:** B2B-prijzen (inkoop) en inloggegevens. Alles behalve `<available>`
blijft precies zoals Solgar het publiceert.

## Feed-URL's (Stock Sync)

| Stock Sync-profiel | URL |
|---|---|
| Solgar Update (03:30) | `https://raw.githubusercontent.com/Maximillian-creator/solgar-feed/main/solgar_feed.xml` |
| Viridian Update (03:00) | `https://raw.githubusercontent.com/Maximillian-creator/solgar-feed/main/viridian_feed.xml` |

`verschillen.csv` somt na elke run op waar de B2B anders zegt dan Solgars eigen feed. Bij
"tijdelijk niet leverbaar" staat ook de verwachte datum erbij.

## Schema

2× per dag, **20:47 en 10:47 NL** (zomertijd). GitHub start tot 6 uur te laat, dus ruim
vóór Stock Sync (03:00). Daarnaast meteen na elke wijziging aan `scraper.py`.

## De rem (er wordt niets weggeschreven als…)

- Solgars feed afgebroken is of te weinig varianten heeft (Solgar < 180, Viridian < 140);
- het inloggen op de B2B mislukt, of de B2B minder dan 300 producten toont;
- meer dan 5% van de varianten niet in de B2B staat (normaal ~1%);
- meer dan 5% onbepaald is (een onbekend voorraadlabel);
- meer dan 30% niet leverbaar zou worden (normaal ~12%: dan klopt het lezen niet).

Per feed: houdt de rem Viridian tegen, dan wordt Solgar nog wel bijgewerkt (en andersom).
De vorige versie blijft staan, en Nebula ziet een rode run.

## Eenmalig instellen (Max)

1. Maak op GitHub een lege, **publieke** repo `solgar-feed` (net als de andere feeds,
   anders kan Stock Sync hem niet lezen).
2. Ga naar Settings → Secrets and variables → Actions → New repository secret en maak
   er twee aan:
   - `SOLGAR_GEBRUIKER`: de gebruikersnaam waarmee je inlogt op sales.solgarvitamins.nl
   - `SOLGAR_WACHTWOORD`: het wachtwoord daarvan
3. Claude Code pusht de code. De eerste run start dan vanzelf. Het eerste echte inloggen
   gebeurt dus in die run: kijk of hij groen is.
4. Is die run groen, en ziet `verschillen.csv` er goed uit? Zet dan in Stock Sync bij
   "Solgar Update" en "Viridian Update" de bron-URL op de URL's hierboven. Aan de
   koppeling hoeft niets te veranderen.

## Lokaal testen (zonder inlog)

```bash
pip install -r requirements.txt pytest
python -m pytest -q test_feed.py
```
