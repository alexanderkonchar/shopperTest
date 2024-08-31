from django.urls import path

from . import views

app_name = "usageMeter"

urlpatterns = [
    path("", views.index, name="index"),
    path("upload/", views.upload, name="upload"),
    path("<str:customer_code>/list", views.list_measurements, name="list_measurements")
]
