import secrets
from datetime import datetime, timedelta

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Station(models.Model):
    """Gare (ou regroupement « intramuros ») telle que nommée par le jeu TGVmax."""

    name = models.CharField("nom SNCF", max_length=120, unique=True)
    display_name = models.CharField("nom affiché", max_length=120)
    code = models.CharField("code", max_length=12, blank=True)
    slug = models.SlugField(max_length=140, unique=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["display_name"]
        verbose_name = "gare"

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = prettify_station_name(self.name)
        if not self.slug:
            base = slugify(self.name)[:130] or "gare"
            slug, n = base, 2
            while Station.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class Trip(models.Model):
    """Un train direct entre deux gares, à une date donnée."""

    date = models.DateField(db_index=True)
    train_no = models.CharField("n° de train", max_length=12)
    entity = models.CharField("entité", max_length=40, blank=True)
    axe = models.CharField(max_length=60, blank=True)
    origin = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="departures")
    destination = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="arrivals")
    departure_time = models.TimeField("départ")
    arrival_time = models.TimeField("arrivée")
    duration_minutes = models.PositiveIntegerField("durée (min)")
    available = models.BooleanField("place MAX dispo", default=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "departure_time"]
        verbose_name = "trajet"
        constraints = [
            models.UniqueConstraint(
                fields=["date", "train_no", "origin", "destination"], name="uniq_trip"
            )
        ]
        indexes = [
            models.Index(fields=["date", "origin", "available"]),
            models.Index(fields=["date", "destination", "available"]),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.train_no} {self.origin} → {self.destination}"

    @staticmethod
    def compute_duration(dep, arr) -> int:
        """Durée en minutes ; si l'arrivée est avant le départ, le train arrive le lendemain."""
        d = dep.hour * 60 + dep.minute
        a = arr.hour * 60 + arr.minute
        return (a - d) % (24 * 60)

    @property
    def departure_dt(self) -> datetime:
        return datetime.combine(self.date, self.departure_time)

    @property
    def arrival_dt(self) -> datetime:
        return self.departure_dt + timedelta(minutes=self.duration_minutes)

    @property
    def overnight(self) -> bool:
        return self.arrival_dt.date() > self.date

    @property
    def duration_display(self) -> str:
        return format_duration(self.duration_minutes)


class SyncRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=20, default="api")
    ok = models.BooleanField(default=False)
    records = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    deleted = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        get_latest_by = "started_at"
        verbose_name = "synchronisation"

    def __str__(self) -> str:
        return f"Sync {self.started_at:%d/%m %H:%M} ({'ok' if self.ok else 'échec'})"


def _token() -> str:
    return secrets.token_urlsafe(24)


class Alert(models.Model):
    """Surveillance d'un trajet : e-mail dès qu'une place MAX apparaît."""

    email = models.EmailField()
    origin = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="+")
    destination = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="+")
    date = models.DateField()
    earliest = models.TimeField("départ au plus tôt", null=True, blank=True)
    latest = models.TimeField("départ au plus tard", null=True, blank=True)
    active = models.BooleanField(default=True)
    token = models.CharField(max_length=64, unique=True, default=_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    # Trains déjà signalés (pour ne pas renvoyer le même e-mail à chaque synchro)
    notified_trains = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["date", "created_at"]
        verbose_name = "alerte"

    def __str__(self) -> str:
        return f"{self.email} : {self.origin} → {self.destination} le {self.date:%d/%m}"

    def matching_trips(self):
        qs = Trip.objects.filter(
            date=self.date, origin=self.origin, destination=self.destination, available=True
        )
        if self.earliest:
            qs = qs.filter(departure_time__gte=self.earliest)
        if self.latest:
            qs = qs.filter(departure_time__lte=self.latest)
        return qs.order_by("departure_time")

    def get_unsubscribe_url(self) -> str:
        return reverse("trains:alert_unsubscribe", args=[self.token])


# --- helpers -----------------------------------------------------------------

_SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "sur", "en", "et", "d", "l", "aux", "au"}


def prettify_station_name(raw: str) -> str:
    """'PARIS (intramuros)' -> 'Paris', 'ST PIERRE DES CORPS' -> 'St-Pierre-des-Corps'-like."""
    name = raw.strip()
    for suffix in ("(intramuros)", "(gares intramuros)", "(INTRAMUROS)"):
        name = name.replace(suffix, "")
    name = " ".join(name.split())
    words = []
    for i, w in enumerate(name.lower().split(" ")):
        if i > 0 and w in _SMALL_WORDS:
            words.append(w)
        elif w in {"tgv", "cdg", "cdg2"}:
            words.append(w.upper())
        else:
            words.append("-".join(part[:1].upper() + part[1:] for part in w.split("-")))
    return " ".join(words)


def format_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}" if h else f"{m} min"
