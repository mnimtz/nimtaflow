"""Offline geo-name helpers.

The bundled `reverse_geocoder` returns ASCII-normalised city names (so
"Mönchengladbach" → "Monchengladbach") and only a country CODE (cc), never a
country name. Two small lookups fix that for display + place search:

  • COUNTRY_DE: ISO-3166 alpha-2 → German country name (so "in der Türkei" can
    filter on Photo.country).
  • CITY_FIX:   ASCII city → proper German spelling (umlauts/ß) for the cities
    that actually show up in this library.

Both are deliberately small + curated (no external dependency). Unmapped codes
simply leave the country blank rather than storing a cryptic "TR".
"""

# ISO 3166-1 alpha-2 → German country name (common travel + Europe).
COUNTRY_DE = {
    "DE": "Deutschland", "AT": "Österreich", "CH": "Schweiz", "FR": "Frankreich",
    "IT": "Italien", "ES": "Spanien", "PT": "Portugal", "NL": "Niederlande",
    "BE": "Belgien", "LU": "Luxemburg", "GB": "Vereinigtes Königreich", "IE": "Irland",
    "DK": "Dänemark", "SE": "Schweden", "NO": "Norwegen", "FI": "Finnland",
    "IS": "Island", "PL": "Polen", "CZ": "Tschechien", "SK": "Slowakei",
    "HU": "Ungarn", "HR": "Kroatien", "SI": "Slowenien", "RS": "Serbien",
    "BA": "Bosnien und Herzegowina", "ME": "Montenegro", "AL": "Albanien",
    "GR": "Griechenland", "TR": "Türkei", "CY": "Zypern", "MT": "Malta",
    "RO": "Rumänien", "BG": "Bulgarien", "UA": "Ukraine", "RU": "Russland",
    "EE": "Estland", "LV": "Lettland", "LT": "Litauen",
    "US": "USA", "CA": "Kanada", "MX": "Mexiko", "CU": "Kuba",
    "DO": "Dominikanische Republik", "BR": "Brasilien", "AR": "Argentinien",
    "EG": "Ägypten", "MA": "Marokko", "TN": "Tunesien", "ZA": "Südafrika",
    "AE": "Vereinigte Arabische Emirate", "TH": "Thailand", "ID": "Indonesien",
    "JP": "Japan", "CN": "China", "IN": "Indien", "AU": "Australien",
    "NZ": "Neuseeland", "MV": "Malediven", "MU": "Mauritius",
}

# ASCII (reverse_geocoder) → correct German spelling. Extend as needed.
CITY_FIX = {
    "Monchengladbach": "Mönchengladbach", "Koln": "Köln", "Munchen": "München",
    "Nurnberg": "Nürnberg", "Dusseldorf": "Düsseldorf", "Osnabruck": "Osnabrück",
    "Saarbrucken": "Saarbrücken", "Lubeck": "Lübeck", "Wurzburg": "Würzburg",
    "Gutersloh": "Gütersloh", "Furth": "Fürth", "Tubingen": "Tübingen",
    "Gottingen": "Göttingen", "Ludenscheid": "Lüdenscheid", "Solingen": "Solingen",
    "Krefeld": "Krefeld", "Zurich": "Zürich", "Genf": "Genf", "Malaga": "Málaga",
    "Cordoba": "Córdoba", "Dusseldorf Pempelfort": "Düsseldorf",
    "Wandsbek": "Hamburg", "Sao Paulo": "São Paulo", "Brasilia": "Brasília",
    "Bogota": "Bogotá", "Cancun": "Cancún", "Merida": "Mérida",
}


def country_name(cc: str | None) -> str | None:
    if not cc:
        return None
    return COUNTRY_DE.get(cc.strip().upper())


def fix_city(name: str | None) -> str | None:
    if not name:
        return name
    n = name.strip()
    return CITY_FIX.get(n, n)
