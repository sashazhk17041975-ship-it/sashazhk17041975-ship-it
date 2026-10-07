from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import AnalogueForm, ImportForm, PartForm
from .importers import import_csv
from .models import Analogue, CrossReference, Manufacturer, Part, Vehicle, normalize_article


def editor_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


@login_required
def part_list(request):
    parts = Part.objects.select_related('manufacturer')
    q = request.GET.get('q', '').strip()[:200]
    if q:
        search = Q(article__icontains=q) | Q(name__icontains=q) | Q(manufacturer__name__icontains=q)
        key = normalize_article(q)
        if key:
            search |= Q(article_key__icontains=key)
        parts = parts.filter(search)
    manufacturer = request.GET.get('manufacturer', '')
    vehicle = request.GET.get('vehicle', '')
    category = request.GET.get('category', '')
    if manufacturer.isdecimal():
        parts = parts.filter(manufacturer_id=int(manufacturer))
    if vehicle.isdecimal():
        parts = parts.filter(vehicles__pk=int(vehicle))
    if category:
        parts = parts.filter(category=category)
    page = Paginator(parts, 25).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'catalog/part_list.html', {
        'page': page, 'q': q, 'manufacturer': manufacturer, 'vehicle': vehicle, 'category': category,
        'manufacturers': Manufacturer.objects.all(), 'vehicles': Vehicle.objects.all(),
        'categories': Part.objects.exclude(category='').order_by('category').values_list('category', flat=True).distinct(),
        'total_parts': Part.objects.count(), 'total_links': Analogue.objects.count() + CrossReference.objects.count(),
        'total_manufacturers': Manufacturer.objects.count(), 'query_string': params.urlencode(),
    })


@login_required
def part_detail(request, pk):
    part = get_object_or_404(Part.objects.select_related('manufacturer').prefetch_related('vehicles'), pk=pk)
    links = Analogue.objects.filter(Q(part_a=part) | Q(part_b=part)).select_related('part_a__manufacturer', 'part_b__manufacturer')
    rows = [{'link': link, 'other': link.part_b if link.part_a_id == pk else link.part_a} for link in links]
    refs = CrossReference.objects.filter(Q(source_part=part) | Q(related_part=part)).select_related('source_part__manufacturer', 'related_part__manufacturer').order_by('-rate', 'pk')
    reference_rows = [{'ref': ref, 'other': ref.related_part if ref.source_part_id == pk else ref.source_part} for ref in refs]
    return render(request, 'catalog/part_detail.html', {'part': part, 'rows': rows, 'reference_rows': reference_rows})


@editor_required
def part_edit(request, pk=None):
    part = get_object_or_404(Part, pk=pk) if pk else None
    form = PartForm(request.POST or None, instance=part)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                part = form.save()
        except IntegrityError:
            form.add_error(None, 'Артикул уже существует. Обновите страницу и проверьте данные.')
        else:
            messages.success(request, 'Запчасть сохранена.')
            return redirect('catalog:part_detail', pk=part.pk)
    return render(request, 'catalog/form.html', {'form': form, 'title': 'Редактировать запчасть' if pk else 'Новая запчасть'})


@editor_required
def analogue_add(request, pk):
    part = get_object_or_404(Part, pk=pk)
    form = AnalogueForm(request.POST or None, part=part)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                Analogue.objects.create(part_a=part, part_b=form.cleaned_data['other'],
                    source=form.cleaned_data['source'], note=form.cleaned_data['note'], verified=form.cleaned_data['verified'])
        except IntegrityError:
            form.add_error(None, 'Эта связь уже существует.')
        else:
            messages.success(request, 'Аналог добавлен. Связь доступна с обеих сторон.')
            return redirect('catalog:part_detail', pk=pk)
    return render(request, 'catalog/form.html', {'form': form, 'title': f'Добавить аналог · {part.article}'})


@editor_required
@require_POST
def analogue_delete(request, pk):
    link = get_object_or_404(Analogue, pk=pk)
    part_id = link.part_a_id
    link.delete()
    messages.success(request, 'Связь удалена.')
    return redirect('catalog:part_detail', pk=part_id)


@editor_required
def csv_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            created, updated = import_csv(form.cleaned_data['file'], form.cleaned_data['kind'])
        except (ValueError, IntegrityError) as error:
            form.add_error(None, str(error) if isinstance(error, ValueError) else 'Конфликт данных. Импорт отменён целиком.')
        else:
            messages.success(request, f'Импорт завершён: добавлено {created}, обновлено {updated}.')
            return redirect('catalog:part_list')
    return render(request, 'catalog/import.html', {'form': form})
