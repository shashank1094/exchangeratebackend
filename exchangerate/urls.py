from django.urls import path

from .views import MyFormView

urlpatterns = [
    path('', MyFormView.as_view(), name='index'),
]