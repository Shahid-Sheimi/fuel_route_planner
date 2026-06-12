from django.urls import path

from route import views

urlpatterns = [
    path("", views.map_page, name="map"),
    path("api/route/", views.RoutePlanView.as_view(), name="route-plan"),
]
