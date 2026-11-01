"""Client pour le jeu de données open data SNCF « tgvmax ».

Doc : https://ressources.data.sncf.com/explore/dataset/tgvmax/
Champs utilisés : date, train_no, entity, axe, origine_iata, destination_iata,
origine, destination, heure_depart, heure_arrivee, od_happy_card (OUI/NON).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, Iterator

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

USER_AGENT = "tgv-max-explorer/1.0 (+https://github.com/grudal-dev/tgv-max-explorer)"


@dataclass(frozen=True)
class RawTrip:
    date: date
    train_no: str
    entity: str
    axe: str
    origin_code: str
    origin_name: str
    destination_code: str
    destination_name: str
    departure: time
    arrival: time
    available: bool


class SNCFError(RuntimeError):
    pass


def _parse_time(value: str) -> time:
    value = (value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Heure invalide : {value!r}")


def parse_record(rec: dict) -> RawTrip | None:
    """Convertit un enregistrement brut de l'API ; renvoie None s'il est inexploitable."""
    try:
        return RawTrip(
            date=date.fromisoformat(str(rec["date"])[:10]),
            train_no=str(rec.get("train_no") or "").strip(),
            entity=str(rec.get("entity") or "").strip(),
            axe=str(rec.get("axe") or "").strip(),
            origin_code=str(rec.get("origine_iata") or "").strip(),
            origin_name=str(rec["origine"]).strip(),
            destination_code=str(rec.get("destination_iata") or "").strip(),
            destination_name=str(rec["destination"]).strip(),
            departure=_parse_time(rec["heure_depart"]),
            arrival=_parse_time(rec["heure_arrivee"]),
            available=str(rec.get("od_happy_card", "")).strip().upper() == "OUI",
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Enregistrement ignoré (%s) : %r", exc, rec)
        return None


def fetch_records(
    start: date | None = None, end: date | None = None, session: requests.Session | None = None
) -> list[dict]:
    """Télécharge tout le jeu (ou une plage de dates) via l'endpoint d'export JSON.

    L'endpoint /exports n'est pas paginé (contrairement à /records limité à 10 000
    lignes) : un seul appel suffit pour récupérer les ~30 jours.
    """
    url = f"{settings.TGVMAX_API_BASE}/catalog/datasets/{settings.TGVMAX_DATASET}/exports/json"
    where = []
    if start:
        where.append(f'date >= date"{start.isoformat()}"')
    if end:
        where.append(f'date <= date"{end.isoformat()}"')
    params = {"timezone": "Europe/Paris"}
    if where:
        params["where"] = " and ".join(where)

    http = session or requests.Session()
    logger.info("Téléchargement TGVmax : %s %s", url, params.get("where", ""))
    try:
        resp = http.get(url, params=params, timeout=180, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise SNCFError(f"Impossible de joindre l'API SNCF : {exc}") from exc
    except ValueError as exc:
        raise SNCFError("Réponse de l'API SNCF illisible (JSON invalide)") from exc
    if not isinstance(data, list):
        raise SNCFError(f"Format de réponse inattendu : {type(data).__name__}")
    return data


def parse_records(records: Iterable[dict]) -> Iterator[RawTrip]:
    for rec in records:
        trip = parse_record(rec)
        if trip is not None:
            yield trip
