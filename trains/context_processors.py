from trains.models import SyncRun


def last_sync(request):
    return {"last_sync": SyncRun.objects.filter(ok=True).first()}
