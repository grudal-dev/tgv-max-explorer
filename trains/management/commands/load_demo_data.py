"""Génère des données de démonstration réalistes (format identique à l'API SNCF).

Utile pour développer hors-ligne ou tester l'interface sans attendre la synchro.
"""

import random
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from trains.models import Trip
from trains.services.sncf import parse_records
from trains.services.sync import import_trips

# (axe, entité, [(gare, minutes depuis le départ)], nb de trains/jour, préfixe n°)
LINES = [
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("LYON (intramuros)", 120),
                             ("AVIGNON TGV", 160), ("MARSEILLE ST CHARLES", 195)], 9, 61),
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("VALENCE TGV", 135),
                             ("AIX EN PROVENCE TGV", 180), ("TOULON", 230), ("CANNES", 305),
                             ("NICE VILLE", 345)], 4, 62),
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("NIMES CENTRE", 175),
                             ("MONTPELLIER ST ROCH", 205), ("BEZIERS", 245), ("NARBONNE", 265),
                             ("PERPIGNAN", 305)], 4, 66),
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("GRENOBLE", 180)], 5, 65),
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("DIJON VILLE", 95),
                             ("BESANCON FRANCHE COMTE TGV", 125), ("MULHOUSE VILLE", 180)], 4, 67),
    ("SUD EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("CHAMBERY CHALLES LES EAUX", 170),
                             ("ANNECY", 225)], 3, 69),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("ST PIERRE DES CORPS", 60),
                                ("POITIERS", 100), ("ANGOULEME", 130), ("BORDEAUX ST JEAN", 125 + 40)],
     8, 84),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("BORDEAUX ST JEAN", 125),
                                ("DAX", 205), ("BAYONNE", 235), ("BIARRITZ", 245),
                                ("HENDAYE", 270)], 3, 85),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("BORDEAUX ST JEAN", 130),
                                ("AGEN", 195), ("MONTAUBAN VILLE BOURBON", 235),
                                ("TOULOUSE MATABIAU", 265)], 4, 86),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("LE MANS", 55),
                                ("RENNES", 90), ("ST BRIEUC", 135), ("MORLAIX", 190),
                                ("BREST", 220)], 5, 80),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("RENNES", 90), ("VANNES", 155),
                                ("LORIENT", 185), ("QUIMPER", 220)], 4, 87),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("LE MANS", 55),
                                ("ANGERS ST LAUD", 95), ("NANTES", 130)], 7, 88),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("POITIERS", 95), ("NIORT", 135),
                                ("LA ROCHELLE VILLE", 175)], 3, 83),
    ("ATLANTIQUE", "TGV INOUI", [("PARIS (intramuros)", 0), ("RENNES", 90), ("ST MALO", 150)], 2, 81),
    ("EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("CHAMPAGNE ARDENNE TGV", 45),
                         ("LORRAINE TGV", 85), ("STRASBOURG", 110)], 7, 24),
    ("EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("METZ VILLE", 85)], 3, 25),
    ("EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("NANCY VILLE", 95)], 3, 26),
    ("EST", "TGV INOUI", [("PARIS (intramuros)", 0), ("REIMS", 45)], 3, 27),
    ("NORD", "TGV INOUI", [("PARIS (intramuros)", 0), ("LILLE (intramuros)", 62)], 9, 72),
    ("NORD", "TGV INOUI", [("PARIS (intramuros)", 0), ("ARRAS", 50), ("DUNKERQUE", 115)], 3, 73),
    ("INTERSECTEUR", "TGV INOUI", [("LILLE (intramuros)", 0), ("AEROPORT CDG2 TGV ROISSY", 55),
                                  ("MARNE LA VALLEE CHESSY", 70), ("LYON (intramuros)", 190),
                                  ("AVIGNON TGV", 245), ("MARSEILLE ST CHARLES", 280)], 4, 50),
    ("INTERSECTEUR", "TGV INOUI", [("STRASBOURG", 0), ("MULHOUSE VILLE", 55),
                                  ("BESANCON FRANCHE COMTE TGV", 95), ("LYON (intramuros)", 205),
                                  ("MARSEILLE ST CHARLES", 305)], 3, 98),
    ("INTERSECTEUR", "TGV INOUI", [("RENNES", 0), ("LE MANS", 60), ("MASSY TGV", 120),
                                  ("LYON (intramuros)", 245)], 2, 56),
    ("INTERSECTEUR", "TGV INOUI", [("NANTES", 0), ("ANGERS ST LAUD", 40),
                                  ("MARNE LA VALLEE CHESSY", 180), ("LILLE (intramuros)", 245)], 2, 52),
    ("INTERSECTEUR", "TGV INOUI", [("BORDEAUX ST JEAN", 0), ("MASSY TGV", 135),
                                  ("LILLE (intramuros)", 225)], 2, 53),
    ("SUD EST", "TGV INOUI", [("BORDEAUX ST JEAN", 0), ("TOULOUSE MATABIAU", 130),
                             ("NARBONNE", 215), ("MONTPELLIER ST ROCH", 270),
                             ("MARSEILLE ST CHARLES", 375)], 2, 43),
    ("SUD EST", "TGV INOUI", [("LYON (intramuros)", 0), ("MONTPELLIER ST ROCH", 105),
                             ("PERPIGNAN", 195)], 2, 44),
    ("SUD EST", "TGV INOUI", [("LYON (intramuros)", 0), ("MARSEILLE ST CHARLES", 100),
                             ("TOULON", 150), ("NICE VILLE", 265)], 2, 45),
    ("INTERNATIONAL", "TGV INOUI", [("PARIS (intramuros)", 0), ("GENEVE", 190)], 3, 96),
    ("INTERNATIONAL", "TGV INOUI", [("PARIS (intramuros)", 0), ("BRUXELLES MIDI", 85)], 2, 93),
    ("INTERCITES", "INTERCITES", [("PARIS (intramuros)", 0), ("LIMOGES BENEDICTINS", 200),
                                 ("BRIVE LA GAILLARDE", 255), ("TOULOUSE MATABIAU", 400)], 2, 36),
    ("INTERCITES", "INTERCITES", [("PARIS (intramuros)", 0), ("CLERMONT FERRAND", 210)], 3, 59),
    ("INTERCITES", "INTERCITES", [("BORDEAUX ST JEAN", 0), ("LA ROCHELLE VILLE", 140),
                                 ("NANTES", 255)], 2, 39),
]

DEPARTURE_SLOTS = list(range(6 * 60, 20 * 60 + 1, 30))


def _fmt(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def generate_records(days: int = 30, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    today = timezone.localdate()
    records = []
    for d in range(days):
        day = today + timedelta(days=d)
        weekend = day.weekday() in (4, 6)  # vendredi / dimanche plus chargés
        for axe, entity, stops, per_day, prefix in LINES:
            slots = sorted(rng.sample(DEPARTURE_SLOTS, k=min(per_day, len(DEPARTURE_SLOTS))))
            for n, start in enumerate(slots):
                for direction in (1, -1):
                    seq = stops if direction == 1 else [
                        (s, stops[-1][1] - m) for s, m in reversed(stops)
                    ]
                    train_no = f"{prefix * 100 + n * 2 + (0 if direction == 1 else 1)}"
                    dep0 = start + (rng.choice((0, 15, 30)) if direction == -1 else 0)
                    for i in range(len(seq)):
                        for j in range(i + 1, len(seq)):
                            # Plus le train est demandé (week-end, pointe), moins il y a de places MAX.
                            peak = 7 * 60 <= dep0 <= 9 * 60 or 17 * 60 <= dep0 <= 19 * 60
                            p_free = 0.55 - (0.25 if weekend else 0) - (0.15 if peak else 0)
                            records.append({
                                "date": day.isoformat(),
                                "train_no": train_no,
                                "entity": entity,
                                "axe": axe,
                                "origine_iata": "",
                                "destination_iata": "",
                                "origine": seq[i][0],
                                "destination": seq[j][0],
                                "heure_depart": _fmt(dep0 + seq[i][1]),
                                "heure_arrivee": _fmt(dep0 + seq[j][1]),
                                "od_happy_card": "OUI" if rng.random() < p_free else "NON",
                            })
    return records


class Command(BaseCommand):
    help = "Charge des données de démonstration (30 jours, réseau TGV simplifié)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true", help="Vide les trajets avant import.")

    def handle(self, *args, days=30, seed=42, reset=False, **opts):
        if reset:
            Trip.objects.all().delete()
        records = generate_records(days, seed)
        stats = import_trips(parse_records(records), source="demo")
        self.stdout.write(self.style.SUCCESS(
            f"Démo chargée : {stats.records} enregistrements, {stats.created} créés, "
            f"{stats.updated} mis à jour."
        ))
