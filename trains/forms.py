from datetime import timedelta

from django import forms
from django.db.models import Exists, OuterRef
from django.utils import timezone

from trains.models import Alert, Station, Trip


def served_stations():
    """Gares ayant au moins un trajet à venir (disponible ou non)."""
    today = timezone.localdate()
    return Station.objects.filter(
        Exists(Trip.objects.filter(origin=OuterRef("pk"), date__gte=today))
        | Exists(Trip.objects.filter(destination=OuterRef("pk"), date__gte=today))
    ).order_by("display_name")


class StationChoiceField(forms.ModelChoiceField):
    def __init__(self, **kwargs):
        kwargs.setdefault("queryset", Station.objects.none())
        kwargs.setdefault("to_field_name", "slug")
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def label_from_instance(self, obj):
        return obj.display_name


DURATION_CHOICES = [
    ("", "Toutes durées"),
    ("90", "≤ 1h30"),
    ("120", "≤ 2h"),
    ("180", "≤ 3h"),
    ("240", "≤ 4h"),
    ("300", "≤ 5h"),
]


class SearchForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    origin = StationChoiceField(label="Départ", empty_label="Toutes les gares")
    destination = StationChoiceField(label="Arrivée", empty_label="Partout")
    after = forms.TimeField(label="Après", required=False,
                            widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    before = forms.TimeField(label="Avant", required=False,
                             widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    max_duration = forms.TypedChoiceField(label="Durée", choices=DURATION_CHOICES, required=False,
                                          coerce=int, empty_value=None)
    connections = forms.BooleanField(label="Avec 1 correspondance", required=False)
    show_full = forms.BooleanField(label="Afficher les trains complets", required=False)

    def __init__(self, *args, stations=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = stations if stations is not None else served_stations()
        self.fields["origin"].queryset = qs
        self.fields["destination"].queryset = qs


def next_weekday(day, weekday):
    return day + timedelta(days=(weekday - day.weekday()) % 7)


class WeekendForm(forms.Form):
    origin = StationChoiceField(label="Je pars de", required=True, empty_label="Choisir une gare")
    out_date = forms.DateField(label="Aller", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    out_after = forms.TimeField(label="Départ après", required=False,
                                widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    back_date = forms.DateField(label="Retour", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    back_after = forms.TimeField(label="Retour après", required=False,
                                 widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    max_duration = forms.TypedChoiceField(label="Durée max", choices=DURATION_CHOICES, required=False,
                                          coerce=int, empty_value=None)

    def __init__(self, *args, stations=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origin"].queryset = stations if stations is not None else served_stations()

    def clean(self):
        data = super().clean()
        if data.get("out_date") and data.get("back_date") and data["back_date"] < data["out_date"]:
            raise forms.ValidationError("La date de retour doit être après l'aller.")
        return data


class AlertForm(forms.ModelForm):
    origin = StationChoiceField(label="Départ", required=True, empty_label="Choisir une gare")
    destination = StationChoiceField(label="Arrivée", required=True, empty_label="Choisir une gare")

    class Meta:
        model = Alert
        fields = ["email", "origin", "destination", "date", "earliest", "latest"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "toi@exemple.fr", "autocomplete": "email"}),
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "earliest": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "latest": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        labels = {"email": "E-mail", "date": "Date du voyage"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = served_stations()
        self.fields["origin"].queryset = qs
        self.fields["destination"].queryset = qs

    def clean_date(self):
        d = self.cleaned_data["date"]
        if d < timezone.localdate():
            raise forms.ValidationError("Cette date est déjà passée.")
        return d

    def clean(self):
        data = super().clean()
        if data.get("origin") and data.get("origin") == data.get("destination"):
            raise forms.ValidationError("Le départ et l'arrivée doivent être différents.")
        if data.get("earliest") and data.get("latest") and data["earliest"] > data["latest"]:
            raise forms.ValidationError("L'heure « au plus tôt » doit précéder « au plus tard ».")
        return data
