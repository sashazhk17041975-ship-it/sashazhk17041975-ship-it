from django import forms
from .models import Analogue, Part


class PartForm(forms.ModelForm):
    class Meta:
        model = Part
        fields = ['manufacturer', 'article', 'name', 'category', 'description', 'source', 'vehicles']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class AnalogueForm(forms.Form):
    other = forms.ModelChoiceField(label='Деталь-аналог', queryset=Part.objects.all())
    source = forms.CharField(label='Источник / каталог', max_length=255)
    note = forms.CharField(label='Условия замены', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    verified = forms.BooleanField(label='Проверено специалистом', required=False)

    def __init__(self, *args, part, **kwargs):
        super().__init__(*args, **kwargs)
        self.part = part
        self.fields['other'].queryset = Part.objects.exclude(pk=part.pk).select_related('manufacturer')

    def clean(self):
        data = super().clean()
        if data.get('other'):
            a, b = sorted([self.part.pk, data['other'].pk])
            if Analogue.objects.filter(part_a_id=a, part_b_id=b).exists():
                raise forms.ValidationError('Эта связь уже существует.')
        return data


class ImportForm(forms.Form):
    kind = forms.ChoiceField(label='Тип данных', choices=[('references', 'Каталог связей (формат example.csv)'), ('parts', 'Запчасти'), ('analogues', 'Связи аналогов')])
    file = forms.FileField(label='CSV-файл (UTF-8, до 2 МБ)')

    def clean_file(self):
        file = self.cleaned_data['file']
        if file.size > 2 * 1024 * 1024:
            raise forms.ValidationError('Максимальный размер — 2 МБ.')
        return file
