import gzip
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# stats.baseball.cz blokkeert sinds kort alle automatisch verkeer met een
# kale 403 (bevestigd op meerdere pagina's, ook de homepage — dus geen
# pagina-specifiek probleem maar een site-brede bot-blokkade). Deze scraper
# is daarom overgezet naar www.baseball.cz, dat dezelfde standen toont via
# een normale, makkelijk te parsen HTML-tabel.
#
# LET OP: "season" en "league" in de URL zijn interne ID's van de site zelf,
# geen jaartallen. Ze moeten waarschijnlijk elk seizoen handmatig worden
# bijgewerkt zodra de bond een nieuw seizoen aanmaakt — anders blijft dit
# de standen van seizoen 21 tonen. Controleer op www.baseball.cz onder de
# juiste competitie welke season/league-waarden er in de URL staan.
BASE_URL = "https://www.baseball.cz"
URL = "https://www.baseball.cz/competition/table/1?season=21&league=761&type=all"

# LET OP: www.baseball.cz sluit dit pad uit in robots.txt (het is bedoeld
# als "geen bots"-verzoek, geen technische blokkade — urllib handhaaft dit
# niet automatisch). Dit is een bewuste keuze van de klant om toch te
# scrapen; hou er rekening mee dat de site dit in de toekomst alsnog
# technisch kan gaan blokkeren, net als stats.baseball.cz deed.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,cs;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://www.baseball.cz/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}


def fetch_html(url, pogingen=3):
    laatste_fout = None
    for poging in range(1, pogingen + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                ruw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    ruw = gzip.decompress(ruw)
                return ruw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            laatste_fout = e
            body = ""
            try:
                body = e.read(500).decode("utf-8", errors="replace")
            except Exception:
                pass
            print(f"Poging {poging}/{pogingen}: HTTP {e.code} {e.reason}. Body (eerste 500 tekens): {body!r}")
            if e.code in (403, 429) and poging < pogingen:
                time.sleep(5 * poging)
                continue
            raise
        except urllib.error.URLError as e:
            laatste_fout = e
            print(f"Poging {poging}/{pogingen}: netwerkfout: {e.reason}")
            if poging < pogingen:
                time.sleep(5 * poging)
                continue
            raise
    if laatste_fout:
        raise laatste_fout
    raise RuntimeError("fetch_html: onbekende fout zonder resultaat")


def clean_text(html_fragment):
    """Alle tags verwijderen en witruimte normaliseren."""
    tekst = re.sub(r'<[^>]+>', '', html_fragment)
    return re.sub(r'\s+', ' ', tekst).strip()


def maak_absoluut(pad):
    if not pad:
        return ''
    if pad.startswith('http://') or pad.startswith('https://'):
        return pad
    return BASE_URL + pad


def parse_team_cel(team_html):
    """Cel met <a href="/club/default/{id}"><img src="...">Teamnaam</a>."""
    href_match = re.search(r'href="([^"]+)"', team_html)
    img_match = re.search(r'<img[^>]+src="([^"]+)"', team_html)
    club_id_match = re.search(r'/club/default/(\d+)', team_html)
    return {
        "team":       clean_text(team_html),
        "team_link":  maak_absoluut(href_match.group(1)) if href_match else '',
        "team_logo":  maak_absoluut(img_match.group(1)) if img_match else '',
        "club_id":    club_id_match.group(1) if club_id_match else '',
    }


def parse_laatste5_cel(cel_html):
    return re.findall(r'<li class="(win|lose)"', cel_html)


def parse_standings(html):
    result = {}
    # Split op <h3> fase-koppen (bv. "Základní část", eventueel gevolgd door
    # play-off fases als de site die op dezelfde pagina toont).
    parts = re.split(r'<h3[^>]*>(.*?)</h3>', html, flags=re.DOTALL)
    print(f"Debug: {len(re.findall(r'<h3', html))} <h3>-tags gevonden, {len(re.findall(r'<table', html))} <table>-tags gevonden in de opgehaalde HTML.")
    if len(parts) < 2:
        print("Debug: geen <h3>-fase-koppen gevonden — de opgehaalde HTML bevat waarschijnlijk niet de standen-tabel "
              "(bv. omdat de site die pas via JavaScript ophaalt na het laden van de pagina).")
    i = 1
    while i < len(parts):
        fase_naam = clean_text(parts[i])
        rest = parts[i + 1] if i + 1 < len(parts) else ''
        # Niet strikt op class="table" matchen: Bootstrap-tabellen hebben vaak
        # meerdere classes (bv. class="table table-hover"), dus we pakken
        # gewoon de eerstvolgende <table> na deze fase-kop.
        table_match = re.search(r'<table\b[^>]*>(.*?)</table>', rest, re.DOTALL)
        if not table_match:
            print(f"Debug: geen <table> gevonden direct na fase-kop '{fase_naam}'.")
            i += 2
            continue
        table_html = table_match.group(1)
        tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', table_html, re.DOTALL)
        rows_html = tbody_match.group(1) if tbody_match else table_html
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', rows_html, re.DOTALL)
        print(f"Debug: fase '{fase_naam}' — {len(rows)} <tr>-rijen gevonden in de tabel.")
        fase_rijen = []
        for row in rows:
            tds_raw = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            # #, Tým, Zápasy, Výhry, Prohry, Skóre, Poměr, Odstup, Laatste 5
            if len(tds_raw) < 9:
                print(f"Debug: rij overgeslagen, slechts {len(tds_raw)} <td>-cellen (verwacht 9).")
                continue
            positie = clean_text(tds_raw[0]).rstrip('.')
            team_info = parse_team_cel(tds_raw[1])
            if not team_info["team"]:
                continue
            gespeeld = clean_text(tds_raw[2])
            winst    = clean_text(tds_raw[3])
            verlies  = clean_text(tds_raw[4])
            score    = clean_text(tds_raw[5])
            pct      = clean_text(tds_raw[6])
            gb       = clean_text(tds_raw[7])
            laatste5 = parse_laatste5_cel(tds_raw[8])
            runs_voor, runs_tegen = '', ''
            if ':' in score:
                links, _, rechts = score.partition(':')
                if links.strip().isdigit() and rechts.strip().isdigit():
                    runs_voor, runs_tegen = links.strip(), rechts.strip()
            rij = {
                "positie":     positie,
                "team":        team_info["team"],
                "team_logo":   team_info["team_logo"],
                "team_link":   team_info["team_link"],
                "g":           gespeeld,
                "w":           winst,
                "l":           verlies,
                "score":       score,
                "runs_voor":   runs_voor,
                "runs_tegen":  runs_tegen,
                "pct":         pct,
                "gb":          gb,
                "laatste5":    laatste5,
            }
            fase_rijen.append(rij)
        if fase_rijen:
            result[fase_naam] = fase_rijen
        i += 2
    return result


def main():
    print(f"Ophalen van {URL}...")
    html = fetch_html(URL)
    print(f"Ontvangen: {len(html)} bytes")
    standen = parse_standings(html)
    print(f"Gevonden fases: {list(standen.keys())}")
    output = {
        "bijgewerkt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bron":       URL,
        "standen":    standen,
    }
    with open("standen_extraliga.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("✅ standen_extraliga.json opgeslagen")


if __name__ == "__main__":
    main()
