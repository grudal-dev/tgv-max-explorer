"""Envoi des alertes de disponibilité après chaque synchronisation."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from trains.models import Alert

logger = logging.getLogger(__name__)


def check_alerts(dry_run: bool = False) -> int:
    """Envoie un e-mail pour chaque alerte ayant de *nouveaux* trains disponibles.

    Retourne le nombre d'e-mails envoyés. Les alertes dont la date est passée
    sont désactivées.
    """
    today = timezone.localdate()
    Alert.objects.filter(active=True, date__lt=today).update(active=False)

    sent = 0
    for alert in Alert.objects.filter(active=True).select_related("origin", "destination"):
        trips = list(alert.matching_trips())
        already = set(alert.notified_trains)
        new = [t for t in trips if t.train_no not in already]
        # Un train redevenu complet peut être re-signalé plus tard s'il se libère à nouveau.
        still_available = {t.train_no for t in trips}
        if not new:
            if already - still_available:
                alert.notified_trains = sorted(already & still_available)
                alert.save(update_fields=["notified_trains"])
            continue

        context = {
            "alert": alert,
            "trips": new,
            "site_url": settings.SITE_URL.rstrip("/"),
        }
        subject = (
            f"Place MAX dispo : {alert.origin} → {alert.destination} "
            f"le {alert.date:%d/%m}"
        )
        body = render_to_string("trains/email/alert.txt", context)
        if not dry_run:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [alert.email])
            alert.notified_trains = sorted((already & still_available) | {t.train_no for t in new})
            alert.last_notified_at = timezone.now()
            alert.save(update_fields=["notified_trains", "last_notified_at"])
        sent += 1
        logger.info("Alerte envoyée à %s (%d train(s))", alert.email, len(new))
    return sent
