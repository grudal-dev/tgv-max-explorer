"""Coordonnées des gares desservies par TGVmax.

Le jeu de données TGVmax ne fournit pas de coordonnées : on s'appuie sur une
table de référence embarquée (les ~150 gares les plus courantes), complétée si
besoin par la commande ``geocode_stations`` (référentiel des gares SNCF) ou
par une saisie manuelle dans l'admin Django.
"""

from __future__ import annotations

import re
import unicodedata

# Clé = nom normalisé (voir normalize_name). Valeur = (lat, lon).
KNOWN_STATIONS: dict[str, tuple[float, float]] = {
    # Île-de-France
    "PARIS": (48.8566, 2.3522),
    "PARIS GARE DE LYON": (48.8443, 2.3744),
    "PARIS MONTPARNASSE": (48.8410, 2.3194),
    "PARIS NORD": (48.8809, 2.3553),
    "PARIS EST": (48.8768, 2.3592),
    "PARIS BERCY": (48.8392, 2.3826),
    "PARIS AUSTERLITZ": (48.8420, 2.3655),
    "PARIS ST LAZARE": (48.8763, 2.3253),
    "AEROPORT CDG2 TGV ROISSY": (49.0040, 2.5711),
    "AEROPORT CDG 2 TGV": (49.0040, 2.5711),
    "MARNE LA VALLEE CHESSY": (48.8698, 2.7826),
    "MARNE LA VALLEE": (48.8698, 2.7826),
    "MASSY TGV": (48.7255, 2.2604),
    "MASSY PALAISEAU": (48.7255, 2.2604),
    "VERSAILLES CHANTIERS": (48.7955, 2.1353),
    # Hauts-de-France
    "LILLE": (50.6372, 3.0750),
    "LILLE EUROPE": (50.6392, 3.0755),
    "LILLE FLANDRES": (50.6365, 3.0707),
    "TGV HAUTE PICARDIE": (49.8590, 2.8325),
    "ARRAS": (50.2867, 2.7811),
    "DOUAI": (50.3713, 3.0903),
    "LENS": (50.4264, 2.8270),
    "BETHUNE": (50.5216, 2.6420),
    "VALENCIENNES": (50.3632, 3.5175),
    "DUNKERQUE": (51.0306, 2.3681),
    "CALAIS FRETHUN": (50.9010, 1.8114),
    "CALAIS VILLE": (50.9531, 1.8516),
    "BOULOGNE VILLE": (50.7206, 1.6106),
    "HAZEBROUCK": (50.7244, 2.5397),
    "AMIENS": (49.8903, 2.3076),
    "ST QUENTIN": (49.8410, 3.2880),
    # Grand Est
    "STRASBOURG": (48.5850, 7.7343),
    "CHAMPAGNE ARDENNE TGV": (49.2140, 3.9940),
    "REIMS": (49.2595, 4.0244),
    "MEUSE TGV": (48.9790, 5.2720),
    "LORRAINE TGV": (48.9476, 6.1696),
    "METZ VILLE": (49.1097, 6.1773),
    "METZ": (49.1097, 6.1773),
    "NANCY VILLE": (48.6898, 6.1743),
    "NANCY": (48.6898, 6.1743),
    "THIONVILLE": (49.3533, 6.1680),
    "EPINAL": (48.1795, 6.4415),
    "ST DIE DES VOSGES": (48.2876, 6.9480),
    "SAVERNE": (48.7440, 7.3630),
    "COLMAR": (48.0735, 7.3470),
    "MULHOUSE": (47.7418, 7.3428),
    "MULHOUSE VILLE": (47.7418, 7.3428),
    "SELESTAT": (48.2600, 7.4430),
    "CHARLEVILLE MEZIERES": (49.7685, 4.7247),
    "SEDAN": (49.6990, 4.9310),
    "CHALONS EN CHAMPAGNE": (48.9550, 4.3490),
    "VITRY LE FRANCOIS": (48.7210, 4.5870),
    "BAR LE DUC": (48.7710, 5.1650),
    "SARREBOURG": (48.7330, 7.0520),
    # Bourgogne-Franche-Comté
    "DIJON": (47.3233, 5.0270),
    "DIJON VILLE": (47.3233, 5.0270),
    "BESANCON FRANCHE COMTE TGV": (47.3077, 5.9545),
    "BESANCON VIOTTE": (47.2470, 6.0220),
    "BELFORT MONTBELIARD TGV": (47.5866, 6.8990),
    "MONTBARD": (47.6240, 4.3360),
    "LE CREUSOT MONTCEAU MONTCHANIN": (46.7653, 4.4993),
    "MACON LOCHE TGV": (46.2820, 4.7790),
    "MACON VILLE": (46.3050, 4.8270),
    "CHALON SUR SAONE": (46.7810, 4.8430),
    "BEAUNE": (47.0230, 4.8460),
    "DOLE VILLE": (47.0960, 5.4930),
    "MOUCHARD": (46.9760, 5.7990),
    "FRASNE": (46.8550, 6.1620),
    "PONTARLIER": (46.9030, 6.3540),
    # Auvergne-Rhône-Alpes
    "LYON": (45.7600, 4.8590),
    "LYON PART DIEU": (45.7606, 4.8594),
    "LYON PERRACHE": (45.7488, 4.8262),
    "LYON ST EXUPERY TGV": (45.7206, 5.0756),
    "SAINT EXUPERY": (45.7206, 5.0756),
    "ST ETIENNE CHATEAUCREUX": (45.4433, 4.3998),
    "GRENOBLE": (45.1913, 5.7145),
    "GRENOBLE UNIVERSITE GIERES": (45.1850, 5.7820),
    "VALENCE TGV": (44.9915, 4.9786),
    "VALENCE TGV RHONE ALPES SUD": (44.9915, 4.9786),
    "VALENCE VILLE": (44.9285, 4.8935),
    "CHAMBERY CHALLES LES EAUX": (45.5710, 5.9195),
    "AIX LES BAINS LE REVARD": (45.6880, 5.9090),
    "ANNECY": (45.9020, 6.1220),
    "BELLEGARDE": (46.1080, 5.8260),
    "BELLEGARDE AIN": (46.1080, 5.8260),
    "ANNEMASSE": (46.1990, 6.2370),
    "THONON LES BAINS": (46.3700, 6.4820),
    "EVIAN LES BAINS": (46.4000, 6.5890),
    "ALBERTVILLE": (45.6730, 6.3870),
    "MOUTIERS SALINS BRIDES LES BAINS": (45.4870, 6.5310),
    "AIME LA PLAGNE": (45.5560, 6.6490),
    "LANDRY": (45.5730, 6.7330),
    "BOURG ST MAURICE": (45.6190, 6.7700),
    "ST JEAN DE MAURIENNE ARVAN": (45.2750, 6.3510),
    "ST MICHEL VALLOIRE": (45.2160, 6.4730),
    "MODANE": (45.1950, 6.6600),
    "BOURG EN BRESSE": (46.2010, 5.2150),
    "CULOZ": (45.8480, 5.7880),
    "CLERMONT FERRAND": (45.7780, 3.1000),
    "VICHY": (46.1250, 3.4320),
    "ROANNE": (46.0350, 4.0730),
    "MONTELIMAR": (44.5560, 4.7450),
    # PACA
    "MARSEILLE ST CHARLES": (43.3027, 5.3806),
    "MARSEILLE": (43.3027, 5.3806),
    "AIX EN PROVENCE TGV": (43.4553, 5.3173),
    "AVIGNON TGV": (43.9218, 4.7862),
    "AVIGNON CENTRE": (43.9418, 4.8056),
    "TOULON": (43.1285, 5.9295),
    "LES ARCS DRAGUIGNAN": (43.4560, 6.4780),
    "ST RAPHAEL VALESCURE": (43.4234, 6.7685),
    "CANNES": (43.5536, 7.0193),
    "ANTIBES": (43.5860, 7.1200),
    "NICE VILLE": (43.7046, 7.2619),
    "NICE": (43.7046, 7.2619),
    "MONACO MONTE CARLO": (43.7389, 7.4200),
    "MENTON": (43.7740, 7.4930),
    "ORANGE": (44.1360, 4.8150),
    "ARLES": (43.6850, 4.6310),
    "MIRAMAS": (43.5800, 5.0010),
    # Occitanie
    "MONTPELLIER ST ROCH": (43.6045, 3.8806),
    "MONTPELLIER SUD DE FRANCE": (43.5950, 3.9230),
    "MONTPELLIER": (43.6045, 3.8806),
    "NIMES": (43.8325, 4.3660),
    "NIMES CENTRE": (43.8325, 4.3660),
    "NIMES PONT DU GARD": (43.7860, 4.4150),
    "SETE": (43.4125, 3.6960),
    "AGDE": (43.3170, 3.4660),
    "BEZIERS": (43.3365, 3.2185),
    "NARBONNE": (43.1905, 3.0060),
    "PERPIGNAN": (42.6960, 2.8790),
    "CARCASSONNE": (43.2180, 2.3510),
    "CASTELNAUDARY": (43.3190, 1.9540),
    "LEZIGNAN CORBIERES": (43.2000, 2.7570),
    "TOULOUSE MATABIAU": (43.6110, 1.4535),
    "TOULOUSE": (43.6110, 1.4535),
    "MONTAUBAN VILLE BOURBON": (44.0145, 1.3410),
    "MONTAUBAN": (44.0145, 1.3410),
    "TARBES": (43.2410, 0.0710),
    "LOURDES": (43.1000, -0.0400),
    "PAU": (43.2915, -0.3700),
    "ORTHEZ": (43.4870, -0.7650),
    # Nouvelle-Aquitaine
    "BORDEAUX ST JEAN": (44.8259, -0.5560),
    "BORDEAUX": (44.8259, -0.5560),
    "LIBOURNE": (44.9150, -0.2390),
    "ARCACHON": (44.6590, -1.1680),
    "AGEN": (44.2070, 0.6210),
    "MARMANDE": (44.5000, 0.1640),
    "DAX": (43.7200, -1.0500),
    "BAYONNE": (43.4965, -1.4700),
    "BIARRITZ": (43.4590, -1.5450),
    "ST JEAN DE LUZ CIBOURE": (43.3870, -1.6610),
    "HENDAYE": (43.3530, -1.7820),
    "MONT DE MARSAN": (43.8930, -0.4990),
    "ANGOULEME": (45.6530, 0.1650),
    "POITIERS": (46.5822, 0.3330),
    "FUTUROSCOPE": (46.6690, 0.3680),
    "CHATELLERAULT": (46.8170, 0.5460),
    "NIORT": (46.3170, -0.4560),
    "LA ROCHELLE VILLE": (46.1530, -1.1450),
    "LA ROCHELLE": (46.1530, -1.1450),
    "SURGERES": (46.1080, -0.7520),
    "ROCHEFORT": (45.9430, -0.9700),
    "SAINTES": (45.7440, -0.6230),
    "LIMOGES BENEDICTINS": (45.8360, 1.2680),
    "BRIVE LA GAILLARDE": (45.1590, 1.5220),
    "PERIGUEUX": (45.1870, 0.7080),
    # Centre-Val de Loire
    "ST PIERRE DES CORPS": (47.3860, 0.7240),
    "TOURS": (47.3897, 0.6940),
    "VENDOME VILLIERS SUR LOIR": (47.8200, 1.0600),
    "ORLEANS": (47.9070, 1.9050),
    "LES AUBRAIS": (47.9260, 1.9070),
    "BLOIS CHAMBORD": (47.5860, 1.3210),
    "CHATEAUROUX": (46.8100, 1.6940),
    "VIERZON": (47.2230, 2.0680),
    "BOURGES": (47.0950, 2.3940),
    # Pays de la Loire
    "NANTES": (47.2173, -1.5420),
    "ANGERS ST LAUD": (47.4645, -0.5560),
    "ANGERS": (47.4645, -0.5560),
    "LE MANS": (47.9955, 0.1925),
    "SABLE SUR SARTHE": (47.8390, -0.3350),
    "LAVAL": (48.0760, -0.7600),
    "SAUMUR": (47.2700, -0.0710),
    "ST NAZAIRE": (47.2860, -2.2100),
    "LA BAULE ESCOUBLAC": (47.2880, -2.3910),
    "LE POULIGUEN": (47.2710, -2.4280),
    "LE CROISIC": (47.2920, -2.5110),
    "PORNICHET": (47.2640, -2.3390),
    "LA ROCHE SUR YON": (46.6720, -1.4180),
    "LES SABLES D OLONNE": (46.4990, -1.7810),
    "ANCENIS": (47.3710, -1.1790),
    # Bretagne
    "RENNES": (48.1035, -1.6723),
    "VITRE": (48.1230, -1.2090),
    "ST MALO": (48.6455, -2.0050),
    "DOL DE BRETAGNE": (48.5520, -1.7560),
    "LAMBALLE": (48.4680, -2.5150),
    "ST BRIEUC": (48.5070, -2.7660),
    "GUINGAMP": (48.5560, -3.1500),
    "PLOUARET TREGOR": (48.6120, -3.4730),
    "LANNION": (48.7300, -3.4620),
    "MORLAIX": (48.5780, -3.8320),
    "LANDERNEAU": (48.4500, -4.2510),
    "BREST": (48.3880, -4.4790),
    "REDON": (47.6510, -2.0840),
    "VANNES": (47.6640, -2.7520),
    "AURAY": (47.6800, -2.9990),
    "LORIENT": (47.7550, -3.3660),
    "QUIMPERLE": (47.8700, -3.5480),
    "ROSPORDEN": (47.9600, -3.8350),
    "QUIMPER": (47.9940, -4.0920),
    # Normandie
    "ROUEN RIVE DROITE": (49.4489, 1.0940),
    "LE HAVRE": (49.4930, 0.1250),
    "CAEN": (49.1760, -0.3490),
    "CHERBOURG": (49.6330, -1.6200),
    "EVREUX NORMANDIE": (49.0180, 1.1430),
    # International
    "BRUXELLES MIDI": (50.8357, 4.3360),
    "BRUXELLES": (50.8357, 4.3360),
    "LUXEMBOURG": (49.6000, 6.1340),
    "GENEVE": (46.2100, 6.1425),
    "GENEVE CORNAVIN": (46.2100, 6.1425),
    "LAUSANNE": (46.5168, 6.6291),
    "BALE SBB": (47.5476, 7.5897),
    "BALE": (47.5476, 7.5897),
    "BASEL SBB": (47.5476, 7.5897),
    "ZURICH HB": (47.3779, 8.5403),
    "FREIBURG IM BREISGAU HBF": (47.9977, 7.8411),
    "FRANKFURT AM MAIN HBF": (50.1071, 8.6638),
    "STUTTGART HBF": (48.7840, 9.1817),
    "KARLSRUHE HBF": (48.9935, 8.4020),
    "MUNCHEN HBF": (48.1402, 11.5584),
    "MILANO PORTA GARIBALDI": (45.4847, 9.1872),
    "MILANO CENTRALE": (45.4862, 9.2045),
    "TORINO PORTA SUSA": (45.0715, 7.6650),
    "BARCELONA SANTS": (41.3792, 2.1400),
    "FIGUERES VILAFANT": (42.2650, 2.9450),
    "GIRONA": (41.9790, 2.8170),
    "MADRID PUERTA DE ATOCHA": (40.4065, -3.6895),
}

_PAREN = re.compile(r"\([^)]*\)")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_REPLACEMENTS = [
    (re.compile(r"\bSAINTE\b"), "STE"),
    (re.compile(r"\bSAINT\b"), "ST"),
    (re.compile(r"\bAEROPORT\b"), "AEROPORT"),
]


def normalize_name(name: str) -> str:
    """Normalise un nom de gare : majuscules, sans accents, sans parenthèses."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = _PAREN.sub(" ", s.upper())
    s = s.replace("-", " ").replace("'", " ")
    s = _NON_ALNUM.sub(" ", s)
    for pattern, repl in _REPLACEMENTS:
        s = pattern.sub(repl, s)
    return " ".join(s.split())


def lookup_coordinates(name: str) -> tuple[float, float] | None:
    """Cherche les coordonnées d'une gare dans la table embarquée.

    Essaie le nom exact puis des préfixes de plus en plus courts
    (« PARIS GARE DE LYON HALL 1 » -> « PARIS GARE DE LYON » -> … -> « PARIS »).
    """
    key = normalize_name(name)
    if key in KNOWN_STATIONS:
        return KNOWN_STATIONS[key]
    words = key.split()
    for n in range(len(words) - 1, 0, -1):
        prefix = " ".join(words[:n])
        if prefix in KNOWN_STATIONS:
            return KNOWN_STATIONS[prefix]
    return None
