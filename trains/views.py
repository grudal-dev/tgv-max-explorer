from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from trains.forms import AlertForm, SearchForm, WeekendForm, next_weekday, served_stations
from trains.models import Alert, Station, Trip, format_duration
from trains.services.search import (
    DestinationGroup,
    connections,
    direct_trips,
    group_by_destination,
    group_connections,
    round_trips,
)
from trains.services.sync import available_dates


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _point(station: Station, **extra) -> dict:
    return {
        "slug": station.slug,
        "name": station.display_name,
        "lat": station.latitude,
        "lon": station.longitude,
        **extra,
    }


def _default_date(dates):
    today = timezone.localdate()
    return today if (not dates or today in dates) else dates[0]


# --- Recherche principale ----------------------------------------------------


def search(request):
    stations = served_stations()
    dates = available_dates()
    data = request.GET.copy()
    data.setdefault("date", _default_date(dates).isoformat())
    form = SearchForm(data, stations=stations)

    ctx = {"form": form, "dates": dates, "has_data": Trip.objects.exists()}
    map_data = {"mode": "overview", "stations": [], "links": []}

    if form.is_valid():
        cd = form.cleaned_data
        day, origin, dest = cd["date"], cd["origin"], cd["destination"]
        trips = direct_trips(
            day, origin, dest,
            after=cd["after"], before=cd["before"], max_duration=cd["max_duration"],
            only_available=not cd["show_full"],
        )
        ctx.update(day=day, origin=origin, destination=dest,
                   prev_day=day - timedelta(days=1), next_day=day + timedelta(days=1))

        if origin and dest:
            ctx["mode"] = "route"
            ctx["trips"] = list(trips)
            ctx["available_count"] = sum(t.available for t in ctx["trips"])
            map_data = _route_map(origin, dest, ctx["trips"])
        elif origin:
            ctx["mode"] = "from"
            ctx["groups"] = group_by_destination(trips)
            map_data = _from_map(origin, ctx["groups"])
        elif dest:
            ctx["mode"] = "to"
            ctx["groups"] = _group_by_origin(trips)
            map_data = _to_map(dest, ctx["groups"])
        else:
            ctx["mode"] = "overview"
            ctx["overview"] = _overview(day, cd)
            map_data = {
                "mode": "overview",
                "stations": [
                    _point(o["station"], count=o["count"], best=format_duration(o["best"]))
                    for o in ctx["overview"] if o["station"].has_coordinates
                ],
                "links": [],
            }

        if origin and cd["connections"]:
            conns = connections(day, origin, dest, after=cd["after"],
                                exclude_direct=dest is None)
            if cd["max_duration"]:
                conns = [c for c in conns if c.total_minutes <= cd["max_duration"]]
            ctx["connection_groups"] = group_connections(conns)
            _add_connections_to_map(map_data, ctx["connection_groups"])

        ctx["result_count"] = (
            len(ctx.get("trips") or ctx.get("groups") or ctx.get("overview") or [])
        )
        ctx["missing_coords"] = _missing_coords(ctx)

    ctx["map_data"] = map_data
    template = "trains/partials/results.html" if _is_htmx(request) else "trains/search.html"
    return render(request, template, ctx)


def _group_by_origin(trips):
    groups: dict[int, DestinationGroup] = {}
    for t in trips:
        groups.setdefault(t.origin_id, DestinationGroup(t.origin)).trips.append(t)
    return sorted(groups.values(), key=lambda g: (g.best_duration, g.station.display_name))


def _overview(day, cd):
    qs = Trip.objects.filter(date=day, available=True)
    if cd["after"]:
        qs = qs.filter(departure_time__gte=cd["after"])
    if cd["before"]:
        qs = qs.filter(departure_time__lte=cd["before"])
    if cd["max_duration"]:
        qs = qs.filter(duration_minutes__lte=cd["max_duration"])
    rows = (
        qs.values("origin")
        .annotate(count=Count("id"), dests=Count("destination", distinct=True),
                  best=Min("duration_minutes"))
        .order_by("-count")
    )
    by_id = Station.objects.in_bulk([r["origin"] for r in rows])
    return [{"station": by_id[r["origin"]], **r} for r in rows]


def _from_map(origin, groups):
    links, points = [], []
    for g in groups:
        if not g.station.has_coordinates:
            continue
        points.append(_point(g.station, count=g.count, best=g.best_duration_display))
        if origin.has_coordinates:
            links.append({"from": [origin.latitude, origin.longitude],
                          "to": [g.station.latitude, g.station.longitude],
                          "slug": g.station.slug, "label": g.best_duration_display,
                          "kind": "direct"})
    return {"mode": "from", "origin": _point(origin) if origin.has_coordinates else None,
            "stations": points, "links": links}


def _to_map(dest, groups):
    data = _from_map(dest, groups)
    data["mode"] = "to"
    for link in data["links"]:
        link["from"], link["to"] = link["to"], link["from"]
    return data


def _route_map(origin, dest, trips):
    best = min((t.duration_minutes for t in trips), default=None)
    points = [_point(dest, best=format_duration(best) if best else "")] if dest.has_coordinates else []
    links = []
    if origin.has_coordinates and dest.has_coordinates and trips:
        links.append({"from": [origin.latitude, origin.longitude],
                      "to": [dest.latitude, dest.longitude], "slug": dest.slug,
                      "label": format_duration(best), "kind": "direct"})
    return {"mode": "route", "origin": _point(origin) if origin.has_coordinates else None,
            "stations": points, "links": links}


def _add_connections_to_map(map_data, groups):
    known = {p["slug"] for p in map_data["stations"]}
    for g in groups:
        best = g["best"]
        via, dest = best.via, best.destination
        if not (via.has_coordinates and dest.has_coordinates):
            continue
        if dest.slug not in known:
            map_data["stations"].append(_point(dest, best=best.total_display, connection=True))
            known.add(dest.slug)
        map_data["links"].append({"from": [via.latitude, via.longitude],
                                  "to": [dest.latitude, dest.longitude], "slug": dest.slug,
                                  "label": best.total_display, "kind": "connection",
                                  "via": via.display_name})


def _missing_coords(ctx):
    stations = set()
    for g in ctx.get("groups") or []:
        if not g.station.has_coordinates:
            stations.add(g.station.display_name)
    return sorted(stations)


# --- Week-end ----------------------------------------------------------------


def weekend(request):
    stations = served_stations()
    today = timezone.localdate()
    friday = next_weekday(today, 4)
    data = request.GET.copy()
    data.setdefault("out_date", friday.isoformat())
    data.setdefault("back_date", (friday + timedelta(days=2)).isoformat())
    form = WeekendForm(data if "origin" in request.GET else None, stations=stations,
                       initial={"out_date": friday, "back_date": friday + timedelta(days=2),
                                "out_after": "17:00", "back_after": "15:00"})
    ctx = {"form": form, "has_data": Trip.objects.exists()}
    map_data = {"mode": "from", "stations": [], "links": []}

    if form.is_bound and form.is_valid():
        cd = form.cleaned_data
        results = round_trips(cd["origin"], cd["out_date"], cd["back_date"],
                              out_after=cd["out_after"], back_after=cd["back_after"],
                              max_duration=cd["max_duration"])
        ctx.update(results=results, origin=cd["origin"], out_date=cd["out_date"],
                   back_date=cd["back_date"], nights=(cd["back_date"] - cd["out_date"]).days)
        origin = cd["origin"]
        map_data = {
            "mode": "from",
            "origin": _point(origin) if origin.has_coordinates else None,
            "stations": [_point(r.station, best=r.best_duration_display, count=r.options)
                         for r in results if r.station.has_coordinates],
            "links": [
                {"from": [origin.latitude, origin.longitude],
                 "to": [r.station.latitude, r.station.longitude], "slug": r.station.slug,
                 "label": r.best_duration_display, "kind": "roundtrip"}
                for r in results if r.station.has_coordinates and origin.has_coordinates
            ],
        }
    ctx["map_data"] = map_data
    template = "trains/partials/weekend_results.html" if _is_htmx(request) else "trains/weekend.html"
    return render(request, template, ctx)


# --- Alertes -----------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def alert_create(request):
    if request.method == "POST":
        form = AlertForm(request.POST)
        if form.is_valid():
            alert = form.save()
            available_now = alert.matching_trips().count()
            msg = f"Alerte créée : {alert.origin} → {alert.destination} le {alert.date:%d/%m/%Y}."
            if available_now:
                msg += f" Bonne nouvelle : {available_now} train(s) déjà dispo !"
            messages.success(request, msg)
            return redirect("trains:alert_detail", token=alert.token)
    else:
        form = AlertForm(initial={
            k: request.GET.get(k) for k in ("origin", "destination", "date") if request.GET.get(k)
        })
    return render(request, "trains/alert_form.html", {"form": form})


def alert_detail(request, token):
    alert = get_object_or_404(Alert.objects.select_related("origin", "destination"), token=token)
    others = Alert.objects.filter(email__iexact=alert.email, active=True).exclude(pk=alert.pk)
    return render(request, "trains/alert_detail.html", {
        "alert": alert,
        "trips": alert.matching_trips(),
        "full_trips": Trip.objects.filter(
            date=alert.date, origin=alert.origin, destination=alert.destination, available=False
        ).count(),
        "others": others,
    })


@require_http_methods(["GET", "POST"])
def alert_unsubscribe(request, token):
    alert = get_object_or_404(Alert, token=token)
    if request.method == "POST":
        alert.active = False
        alert.save(update_fields=["active"])
        messages.info(request, "Alerte désactivée.")
        return redirect("trains:search")
    return render(request, "trains/alert_unsubscribe.html", {"alert": alert})


def about(request):
    stats = Trip.objects.aggregate(
        total=Count("id"), available=Count("id", filter=Q(available=True)),
        first=Min("date"),
    )
    return render(request, "trains/about.html", {
        "stats": stats,
        "stations": Station.objects.count(),
        "no_coords": Station.objects.filter(latitude__isnull=True),
    })
