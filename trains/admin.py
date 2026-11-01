from django.contrib import admin

from trains.models import Alert, Station, SyncRun, Trip


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name", "code", "latitude", "longitude")
    list_editable = ("latitude", "longitude")
    list_filter = (("latitude", admin.EmptyFieldListFilter),)
    search_fields = ("name", "display_name", "code")
    readonly_fields = ("slug",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("date", "train_no", "origin", "destination", "departure_time",
                    "arrival_time", "duration_minutes", "available")
    list_filter = ("available", "date", "axe", "entity")
    search_fields = ("train_no", "origin__name", "destination__name")
    autocomplete_fields = ("origin", "destination")
    date_hierarchy = "date"


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "source", "ok", "records", "created", "updated", "deleted")
    list_filter = ("ok", "source")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("email", "origin", "destination", "date", "active", "last_notified_at")
    list_filter = ("active", "date")
    search_fields = ("email",)
    autocomplete_fields = ("origin", "destination")
