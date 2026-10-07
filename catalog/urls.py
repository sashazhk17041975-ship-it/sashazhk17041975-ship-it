from django.urls import path
from . import views

app_name = 'catalog'
urlpatterns = [
    path('', views.part_list, name='part_list'),
    path('parts/new/', views.part_edit, name='part_create'),
    path('parts/<int:pk>/', views.part_detail, name='part_detail'),
    path('parts/<int:pk>/edit/', views.part_edit, name='part_edit'),
    path('parts/<int:pk>/analogues/new/', views.analogue_add, name='analogue_add'),
    path('analogues/<int:pk>/delete/', views.analogue_delete, name='analogue_delete'),
    path('import/', views.csv_import, name='csv_import'),
]
