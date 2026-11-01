from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "TGV MAX Explorer — administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("trains.urls")),
]
