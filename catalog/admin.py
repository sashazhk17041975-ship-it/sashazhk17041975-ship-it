from django.contrib import admin
from .models import Analogue, CrossReference, Manufacturer, Part, Vehicle

@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    search_fields = ['name']

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['make', 'model', 'engine', 'year_from', 'year_to']
    search_fields = ['make', 'model', 'engine']

@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ['article', 'manufacturer', 'name', 'category']
    search_fields = ['article', 'article_key', 'name']
    list_filter = ['manufacturer', 'category']
    autocomplete_fields = ['manufacturer', 'vehicles']

@admin.register(Analogue)
class AnalogueAdmin(admin.ModelAdmin):
    list_display = ['part_a', 'part_b', 'source', 'verified']
    autocomplete_fields = ['part_a', 'part_b']
    list_filter = ['verified']

@admin.register(CrossReference)
class CrossReferenceAdmin(admin.ModelAdmin):
    list_display = ['source_part', 'related_part', 'relation_name', 'direction', 'rate', 'last_seen_at']
    autocomplete_fields = ['source_part', 'related_part']
    search_fields = ['source_part__article', 'related_part__article']
    list_filter = ['direction', 'relation_code']
