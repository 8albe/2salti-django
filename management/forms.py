from django import forms
from django.conf import settings
from .models import Training, Convocation
from core.models import Team

class TrainingForm(forms.ModelForm):
    # Campi custom per la ricorrenza
    rec_freq = forms.ChoiceField(
        choices=[('WEEKLY', 'Settimanale'), ('DAILY', 'Giornaliero')],
        required=False,
        label="Frequenza"
    )
    rec_days = forms.MultipleChoiceField(
        choices=[(0, 'Lun'), (1, 'Mar'), (2, 'Mer'), (3, 'Gio'), (4, 'Ven'), (5, 'Sab'), (6, 'Dom')],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Giorni"
    )
    rec_until = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False,
        label="Fino al"
    )

    class Meta:
        model = Training
        fields = ['team', 'title', 'description', 'location', 'start_time', 'end_time', 'is_recurring', 'attachment']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        self.society = kwargs.pop('society', None)
        super().__init__(*args, **kwargs)
        if self.society:
            self.fields['team'].queryset = Team.objects.filter(society=self.society)
        
        # Stili base
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.update({'class': 'w-full bg-white/10 border border-white/20 rounded-lg p-2 text-white'})

    def clean_attachment(self):
        file = self.cleaned_data.get('attachment')
        if file:
            # 1. Controllo dimensione (soft limit 5MB)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Il file è troppo grande (max 5MB).")
            
            # 2. Controllo MIME (semplificato)
            valid_mime_types = ['application/pdf', 'image/jpeg', 'image/png']
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file.name)
            if mime_type not in valid_mime_types:
                raise forms.ValidationError("Tipo di file non supportato (solo PDF, JPG, PNG).")
        return file

    def clean(self):
        cleaned_data = super().clean()
        is_recurring = cleaned_data.get('is_recurring')
        if is_recurring:
            if not cleaned_data.get('rec_until'):
                self.add_error('rec_until', "Data di fine obbligatoria per ricorrenze.")
        return cleaned_data

from django.contrib.auth import get_user_model

User = get_user_model()

class ConvocationForm(forms.ModelForm):
    # Campi per la selezione multipla di giocatori e titolari
    nominees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Convocati"
    )
    starters = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="7 Titolari"
    )

    class Meta:
        model = Convocation
        fields = ['match', 'capitano', 'vicecapitano', 'notes', 'attachment']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.team = kwargs.pop('team', None)
        super().__init__(*args, **kwargs)
        if self.team:
            # Filtra solo atleti della squadra
            from accounts.models import AthleteProfile
            players_ids = AthleteProfile.objects.filter(current_team=self.team).values_list('user_id', flat=True)
            players_qs = User.objects.filter(id__in=players_ids)
            
            self.fields['nominees'].queryset = players_qs
            self.fields['starters'].queryset = players_qs
            self.fields['capitano'].queryset = players_qs
            self.fields['vicecapitano'].queryset = players_qs

        # Stili base
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.update({'class': 'w-full bg-white/10 border border-white/20 rounded-lg p-2 text-white'})

    def clean(self):
        cleaned_data = super().clean()
        nominees = cleaned_data.get('nominees', [])
        starters = cleaned_data.get('starters', [])
        capitano = cleaned_data.get('capitano')
        vicecapitano = cleaned_data.get('vicecapitano')

        # 1. Capitano diverso da Vice
        if capitano and vicecapitano and capitano == vicecapitano:
            raise forms.ValidationError("Il Capitano deve essere diverso dal Vicecapitano.")

        # 2. Titolari devono essere sottoinsieme dei convocati
        for s in starters:
            if s not in nominees:
                self.add_error('starters', f"{s.get_full_name()} deve essere tra i convocati per essere titolare.")

        # 3. Numero titolari conforme (Pallanuoto: 7)
        if starters.count() > 7:
            self.add_error('starters', "Massimo 7 titolari consentiti.")
            
        # 4. Capitano e Vice devono essere tra i convocati
        if capitano and capitano not in nominees:
             self.add_error('capitano', "Il capitano deve essere tra i convocati.")
        if vicecapitano and vicecapitano not in nominees:
             self.add_error('vicecapitano', "Il vicecapitano deve essere tra i convocati.")

        return cleaned_data
