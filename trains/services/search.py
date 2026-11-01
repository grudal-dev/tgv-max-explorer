"""Recherche de trajets : directs, avec correspondance, week-ends aller-retour."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from django.conf import settings
from django.db.models import QuerySet

from trains.models import Station, Trip, format_duration


def direct_trips(
    day: date,
    origin: Station | None = None,
    destination: Station | None = None,
    *,
    after: time | None = None,
    before: time | None = None,
    max_duration: int | None = None,
    only_available: bool = True,
) -> QuerySet[Trip]:
    qs = Trip.objects.filter(date=day).select_related("origin", "destination")
    if only_available:
        qs = qs.filter(available=True)
    if origin:
        qs = qs.filter(origin=origin)
    if destination:
        qs = qs.filter(destination=destination)
    if after:
        qs = qs.filter(departure_time__gte=after)
    if before:
        qs = qs.filter(departure_time__lte=before)
    if max_duration:
        qs = qs.filter(duration_minutes__lte=max_duration)
    return qs.order_by("departure_time", "duration_minutes")


@dataclass
class DestinationGroup:
    """Toutes les options pour rejoindre une gare donnée."""

    station: Station
    trips: list = field(default_factory=list)

    @property
    def best_duration(self) -> int:
        return min(t.duration_minutes for t in self.trips)

    @property
    def best_duration_display(self) -> str:
        return format_duration(self.best_duration)

    @property
    def first_departure(self):
        return min(t.departure_time for t in self.trips)

    @property
    def count(self) -> int:
        return len(self.trips)


def group_by_destination(trips) -> list[DestinationGroup]:
    groups: dict[int, DestinationGroup] = {}
    for t in trips:
        g = groups.setdefault(t.destination_id, DestinationGroup(t.destination))
        g.trips.append(t)
    return sorted(groups.values(), key=lambda g: (g.best_duration, g.station.display_name))


# --- Correspondances ---------------------------------------------------------


@dataclass
class Connection:
    first: Trip
    second: Trip

    @property
    def origin(self) -> Station:
        return self.first.origin

    @property
    def via(self) -> Station:
        return self.first.destination

    @property
    def destination(self) -> Station:
        return self.second.destination

    @property
    def wait_minutes(self) -> int:
        return int((self.second.departure_dt - self.first.arrival_dt).total_seconds() // 60)

    @property
    def total_minutes(self) -> int:
        return int((self.second.arrival_dt - self.first.departure_dt).total_seconds() // 60)

    @property
    def total_display(self) -> str:
        return format_duration(self.total_minutes)

    @property
    def wait_display(self) -> str:
        return format_duration(self.wait_minutes)


def connections(
    day: date,
    origin: Station,
    destination: Station | None = None,
    *,
    min_wait: int | None = None,
    max_wait: int | None = None,
    after: time | None = None,
    exclude_direct: bool = True,
    limit_per_destination: int = 5,
) -> list[Connection]:
    """Trajets à une correspondance, triés par durée totale.

    Si ``destination`` est None, renvoie les meilleures options vers chaque gare
    atteignable (en excluant par défaut celles déjà accessibles en direct).
    """
    min_wait = settings.CONNECTION_MIN_MINUTES if min_wait is None else min_wait
    max_wait = settings.CONNECTION_MAX_MINUTES if max_wait is None else max_wait

    first_legs = list(direct_trips(day, origin, after=after))
    if not first_legs:
        return []
    hubs = {t.destination_id for t in first_legs}
    if destination:
        hubs.discard(destination.id)

    second_qs = (
        Trip.objects.filter(
            date__in=[day, day + timedelta(days=1)], available=True, origin_id__in=hubs
        )
        .exclude(destination=origin)
        .select_related("origin", "destination")
    )
    if destination:
        second_qs = second_qs.filter(destination=destination)

    by_hub: dict[int, list[Trip]] = defaultdict(list)
    for t in second_qs:
        by_hub[t.origin_id].append(t)

    direct_dest = {t.destination_id for t in first_legs} if exclude_direct else set()
    lo, hi = timedelta(minutes=min_wait), timedelta(minutes=max_wait)

    results: list[Connection] = []
    for leg1 in first_legs:
        arr = leg1.arrival_dt
        for leg2 in by_hub.get(leg1.destination_id, ()):
            if not (lo <= leg2.departure_dt - arr <= hi):
                continue
            if destination is None and leg2.destination_id in direct_dest:
                continue
            results.append(Connection(leg1, leg2))

    results.sort(key=lambda c: (c.total_minutes, c.first.departure_time))
    if destination is not None:
        return results[: limit_per_destination * 4]

    per_dest: dict[int, int] = defaultdict(int)
    trimmed = []
    for c in results:
        if per_dest[c.destination.id] < limit_per_destination:
            per_dest[c.destination.id] += 1
            trimmed.append(c)
    return trimmed


def group_connections(conns: list[Connection]) -> list[dict]:
    groups: dict[int, dict] = {}
    for c in conns:
        g = groups.setdefault(c.destination.id, {"station": c.destination, "options": []})
        g["options"].append(c)
    out = list(groups.values())
    for g in out:
        g["best"] = g["options"][0]
    return sorted(out, key=lambda g: g["best"].total_minutes)


# --- Week-end aller-retour ---------------------------------------------------


@dataclass
class RoundTrip:
    station: Station
    outbound: list
    inbound: list

    @property
    def best_outbound(self) -> Trip:
        return min(self.outbound, key=lambda t: t.duration_minutes)

    @property
    def best_duration_display(self) -> str:
        return self.best_outbound.duration_display

    @property
    def options(self) -> int:
        return len(self.outbound) * len(self.inbound)


def round_trips(
    origin: Station,
    out_day: date,
    back_day: date,
    *,
    out_after: time | None = None,
    back_after: time | None = None,
    max_duration: int | None = None,
) -> list[RoundTrip]:
    """Destinations avec au moins un aller ET un retour MAX disponibles."""
    outs = direct_trips(out_day, origin, after=out_after, max_duration=max_duration)
    by_dest: dict[int, list[Trip]] = defaultdict(list)
    for t in outs:
        by_dest[t.destination_id].append(t)
    if not by_dest:
        return []

    backs = Trip.objects.filter(
        date=back_day, available=True, destination=origin, origin_id__in=by_dest.keys()
    ).select_related("origin", "destination").order_by("departure_time")
    if back_after:
        backs = backs.filter(departure_time__gte=back_after)
    if max_duration:
        backs = backs.filter(duration_minutes__lte=max_duration)

    back_by_origin: dict[int, list[Trip]] = defaultdict(list)
    for t in backs:
        back_by_origin[t.origin_id].append(t)

    results = []
    for dest_id, out_list in by_dest.items():
        # Un aller-retour le même jour n'a de sens que si le retour part après l'arrivée.
        in_list = back_by_origin.get(dest_id, [])
        if out_day == back_day:
            earliest_arrival = min(t.arrival_dt for t in out_list)
            in_list = [t for t in in_list if t.departure_dt > earliest_arrival]
        if in_list:
            results.append(RoundTrip(out_list[0].destination, out_list, in_list))
    return sorted(results, key=lambda r: (r.best_outbound.duration_minutes, r.station.display_name))
