"""Complète les coordonnées manquantes via le référentiel « gares-de-voyageurs » SNCF."""

import difflib
import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from trains.models import Station
from trains.services.geo import lookup_coordinates, normalize_name
from trains.services.sncf import USER_AGENT


class Command(BaseCommand):
    help = "Géocode les gares sans coordonnées (table embarquée puis référentiel SNCF)."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=Path, help="Export JSON local du jeu gares-de-voyageurs.")
        parser.add_argument("--offline", action="store_true", help="N'utiliser que la table embarquée.")
        parser.add_argument("--cutoff", type=float, default=0.82, help="Seuil de similarité (0-1).")

    def handle(self, *args, file=None, offline=False, cutoff=0.82, **opts):
        missing = list(Station.objects.filter(latitude__isnull=True))
        if not missing:
            self.stdout.write(self.style.SUCCESS("Toutes les gares ont des coordonnées."))
            return

        fixed = 0
        for st in list(missing):
            if coords := lookup_coordinates(st.name):
                st.latitude, st.longitude = coords
                st.save(update_fields=["latitude", "longitude"])
                missing.remove(st)
                fixed += 1

        if missing and not offline:
            index = self._load_reference(file)
            keys = list(index)
            for st in list(missing):
                key = normalize_name(st.name)
                match = difflib.get_close_matches(key, keys, n=1, cutoff=cutoff)
                if match:
                    st.latitude, st.longitude = index[match[0]]
                    st.save(update_fields=["latitude", "longitude"])
                    missing.remove(st)
                    fixed += 1
                    self.stdout.write(f"  {st.name} -> {match[0]}")

        self.stdout.write(self.style.SUCCESS(f"{fixed} gare(s) géocodée(s)."))
        if missing:
            self.stdout.write(self.style.WARNING(
                "Sans coordonnées (à compléter dans l'admin) : " + ", ".join(s.name for s in missing)
            ))

    def _load_reference(self, file):
        try:
            if file:
                rows = json.loads(file.read_text(encoding="utf-8"))
            else:
                url = f"{settings.TGVMAX_API_BASE}/catalog/datasets/gares-de-voyageurs/exports/json"
                resp = requests.get(url, timeout=120, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
                rows = resp.json()
        except (requests.RequestException, OSError, ValueError) as exc:
            raise CommandError(f"Référentiel des gares indisponible : {exc}") from exc

        index = {}
        for row in rows:
            pos = row.get("position_geographique") or {}
            name = row.get("nom") or row.get("libellecourt")
            if name and pos.get("lat") is not None:
                index[normalize_name(name)] = (float(pos["lat"]), float(pos["lon"]))
        return index
