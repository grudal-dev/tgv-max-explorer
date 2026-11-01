from django.urls import path

from trains import views

app_name = "trains"

urlpatterns = [
    path("", views.search, name="search"),
    path("week-end/", views.weekend, name="weekend"),
    path("alertes/nouvelle/", views.alert_create, name="alert_create"),
    path("alertes/<str:token>/", views.alert_detail, name="alert_detail"),
    path("alertes/<str:token>/desactiver/", views.alert_unsubscribe, name="alert_unsubscribe"),
    path("a-propos/", views.about, name="about"),
]
