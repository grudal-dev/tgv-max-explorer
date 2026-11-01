from django.core.management.base import BaseCommand

from trains.services.alerts import check_alerts


class Command(BaseCommand):
    help = "Envoie les e-mails pour les alertes ayant de nouvelles places MAX."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **opts):
        sent = check_alerts(dry_run=dry_run)
        self.stdout.write(self.style.SUCCESS(f"{sent} alerte(s) {'à envoyer' if dry_run else 'envoyée(s)'}."))
