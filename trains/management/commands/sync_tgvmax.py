import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trains.models import SyncRun
from trains.services.alerts import check_alerts
from trains.services.sncf import SNCFError, fetch_records, parse_records
from trains.services.sync import import_trips


class Command(BaseCommand):
    help = "Importe les disponibilités TGVmax depuis l'open data SNCF."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Ne synchroniser que les N prochains jours (défaut : tout le jeu, ~30 jours).",
        )
        parser.add_argument(
            "--file", type=Path, default=None,
            help="Importer un export JSON local (téléchargé depuis data.sncf.com) au lieu d'appeler l'API.",
        )
        parser.add_argument("--no-alerts", action="store_true", help="Ne pas envoyer les alertes.")

    def handle(self, *args, days=None, file=None, no_alerts=False, **opts):
        today = timezone.localdate()
        try:
            if file:
                records = json.loads(file.read_text(encoding="utf-8"))
                source = "file"
            else:
                end = today + timedelta(days=days) if days else None
                records = fetch_records(start=today, end=end)
                source = "api"
        except (SNCFError, OSError, ValueError) as exc:
            SyncRun.objects.create(source="file" if file else "api", ok=False, message=str(exc),
                                   finished_at=timezone.now())
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"{len(records)} enregistrements reçus, import en cours…")
        stats = import_trips(parse_records(records), source=source)
        self.stdout.write(self.style.SUCCESS(
            f"OK : {stats.created} créés, {stats.updated} mis à jour, {stats.deleted} supprimés, "
            f"{stats.stations_created} nouvelle(s) gare(s)."
        ))
        if not no_alerts:
            sent = check_alerts()
            self.stdout.write(f"{sent} alerte(s) envoyée(s).")
