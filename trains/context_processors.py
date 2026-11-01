from django.conf import settings

from trains.models import SyncRun


def last_sync(request):
    return {"last_sync": SyncRun.objects.filter(ok=True).first()}


def map_tiles(request):
    return {
        "map_tiles": {
            "url": settings.MAP_TILE_URL,
            "attribution": settings.MAP_TILE_ATTRIBUTION,
            "subdomains": settings.MAP_TILE_SUBDOMAINS,
            "carto": bool(settings.CARTO_API_KEY),
        }
    }
