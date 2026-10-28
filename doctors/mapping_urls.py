from django.urls import path

from .views import MappingDetailView, MappingListCreateView

urlpatterns = [
    path("", MappingListCreateView.as_view(), name="mapping-list"),
    # Same URL shape, different meaning per method (handled inside MappingDetailView):
    #   GET    -> <pk> is a patient ID
    #   DELETE -> <pk> is a mapping ID
    path("<str:pk>/", MappingDetailView.as_view(), name="mapping-detail"),
]
