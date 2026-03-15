from django import forms
from .models import Society

class SocietySetupForm(forms.ModelForm):
    class Meta:
        model = Society
        fields = ['name', 'sport', 'city', 'founded_year', 'logo', 'history', 'website', 'email', 'phone']
        labels = {
            'name': 'Nome Società',
            'sport': 'Sport',
            'city': 'Città',
            'founded_year': 'Anno di Fondazione',
            'logo': 'Logo',
            'history': 'Storia della Società',
            'website': 'Sito Web',
            'email': 'Email',
            'phone': 'Telefono',
        }
        widgets = {
            'history': forms.Textarea(attrs={'rows': 4}),
        }
