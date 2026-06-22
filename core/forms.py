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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Macro 18 (#5 / OPS_RUNBOOK §10.11): l'email società è obbligatoria nel
        # setup di rifinitura. Garantisce che `_society_recipients` non sia mai
        # vuota, chiudendo by-design il fallimento silenzioso della notifica di
        # certificazione. Non retroattivo: i seed con email vuota la riempiono
        # al primo refinement. Il campo modello resta blank=True (no migrazione).
        self.fields['email'].required = True
