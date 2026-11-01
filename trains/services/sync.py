"""Import des données TGVmax en base (upsert idempotent)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from trains.models import Station, SyncRun, Trip
from trains.services.geo import lookup_coordinates
from trains.services.sncf import RawTrip

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    records: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    stations_created: int = 0


def _get_stations(raw_trips: list[RawTrip], stats: SyncStats) -> dict[str, Station]:
    names: dict[str, str] = {}
    for t in raw_trips:
        names.setdefault(t.origin_name, t.origin_code)
        names.setdefault(t.destination_name, t.destination_code)

    existing = {s.name: s for s in Station.objects.filter(name__in=names)}
    for name, code in names.items():
        station = existing.get(name)
        if station is None:
            coords = lookup_coordinates(name)
            station = Station(name=name, code=code)
            if coords:
                station.latitude, station.longitude = coords
            station.save()
            existing[name] = station
            stats.stations_created += 1
        elif (code and not station.code) or not station.has_coordinates:
            changed = False
            if code and not station.code:
                station.code, changed = code, True
            if not station.has_coordinates and (coords := lookup_coordinates(name)):
                station.latitude, station.longitude = coords
                changed = True
            if changed:
                station.save()
    return existing


@transaction.atomic
def import_trips(
    raw_trips: Iterable[RawTrip], *, prune: bool = True, source: str = "api"
) -> SyncStats:
    """Insère / met à jour les trajets.

    ``prune`` : supprime les trajets des dates couvertes qui n'apparaissent plus
    dans le flux, ainsi que tous les trajets passés.
    """
    raw = list(raw_trips)
    stats = SyncStats(records=len(raw))
    run = SyncRun.objects.create(source=source)
    if not raw:
        run.message = "Aucun enregistrement reçu."
        run.finished_at = timezone.now()
        run.save()
        return stats

    stations = _get_stations(raw, stats)
    dates = {t.date for t in raw}

    existing: dict[tuple, Trip] = {
        (t.date, t.train_no, t.origin_id, t.destination_id): t
        for t in Trip.objects.filter(date__in=dates)
    }
    seen: set[tuple] = set()
    to_create: list[Trip] = []
    to_update: list[Trip] = []

    for r in raw:
        origin, dest = stations[r.origin_name], stations[r.destination_name]
        key = (r.date, r.train_no, origin.id, dest.id)
        if key in seen:
            continue
        seen.add(key)
        duration = Trip.compute_duration(r.departure, r.arrival)
        trip = existing.get(key)
        if trip is None:
            to_create.append(
                Trip(
                    date=r.date, train_no=r.train_no, entity=r.entity, axe=r.axe,
                    origin=origin, destination=dest,
                    departure_time=r.departure, arrival_time=r.arrival,
                    duration_minutes=duration, available=r.available,
                )
            )
        elif (
            trip.available != r.available
            or trip.departure_time != r.departure
            or trip.arrival_time != r.arrival
        ):
            trip.available = r.available
            trip.departure_time = r.departure
            trip.arrival_time = r.arrival
            trip.duration_minutes = duration
            trip.updated_at = timezone.now()
            to_update.append(trip)

    Trip.objects.bulk_create(to_create, batch_size=2000)
    Trip.objects.bulk_update(
        to_update,
        ["available", "departure_time", "arrival_time", "duration_minutes", "updated_at"],
        batch_size=2000,
    )
    stats.created, stats.updated = len(to_create), len(to_update)

    if prune:
        stale = [t.pk for k, t in existing.items() if k not in seen]
        deleted = Trip.objects.filter(pk__in=stale).delete()[0] if stale else 0
        deleted += Trip.objects.filter(date__lt=timezone.localdate()).delete()[0]
        stats.deleted = deleted

    run.ok = True
    run.records, run.created, run.updated, run.deleted = (
        stats.records, stats.created, stats.updated, stats.deleted,
    )
    run.message = f"{stats.stations_created} nouvelle(s) gare(s)."
    run.finished_at = timezone.now()
    run.save()
    logger.info("Synchro OK : %s", stats)
    return stats


def available_dates() -> list[date]:
    return list(
        Trip.objects.filter(available=True, date__gte=timezone.localdate())
        .values_list("date", flat=True).distinct().order_by("date")
    )
