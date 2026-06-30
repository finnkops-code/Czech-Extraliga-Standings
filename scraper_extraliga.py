import json
import re
import urllib.request
from datetime import datetime, timezone

URL = "https://stats.baseball.cz/en/events/extraliga-2026/standings"


def fetch_html(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def clean_team_name(text):
    """Strip the 3-letter team code prefix (e.g. 'HRO Hroši' → 'Hroši')."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^[A-Z]{2,4}\s+', '', text)
    return text.strip()


def parse_standings(html):
    result = {}

    # Split on <h3> phase headers
    parts = re.split(r'<h3[^>]*>(.*?)</h3>', html, flags=re.DOTALL)

    i = 1
    while i < len(parts):
        fase_naam = re.sub(r'<[^>]+>', '', parts[i]).strip()
        rest = parts[i + 1] if i + 1 < len(parts) else ''

        table_match = re.search(r'<table[^>]*>(.*?)</table>', rest, re.DOTALL)
        if not table_match:
            i += 2
            continue

        table_html = table_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

        fase_rijen = []
        for row in rows:
            tds_raw = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds_raw]
            tds = [re.sub(r'\s+', ' ', td).strip() for td in tds]

            if len(tds) < 5:
                continue

            positie = tds[0] if tds[0] else '-'

            # Find team name (first cell with letters)
            team = ''
            team_idx = -1
            for j in range(1, len(tds)):
                if re.search(r'[A-Za-z]', tds[j]):
                    team = clean_team_name(tds[j])
                    team_idx = j
                    break

            if not team or team_idx == -1:
                continue

            # Numbers follow the team name cell
            cijfers = [c for c in tds[team_idx + 1:] if c != '']
            if len(cijfers) < 3:
                continue

            rij = {
                "positie": positie,
                "team":    team,
                "w":       cijfers[0] if len(cijfers) > 0 else '-',
                "l":       cijfers[1] if len(cijfers) > 1 else '-',
                "t":       cijfers[2] if len(cijfers) > 2 else '-',
                "pct":     cijfers[3] if len(cijfers) > 3 else '-',
                "gb":      cijfers[4] if len(cijfers) > 4 else '-',
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
