from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, AthleteProfile, CoachProfile, RefereeProfile

class SignUpForm(UserCreationForm):
    """Form registrazione con scelta ruolo"""
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, widget=forms.RadioSelect)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role']


class UserSetupForm(forms.ModelForm):
    """Form dati personali comuni"""
    class Meta:
        model = User
        fields = ['profile_picture', 'birth_date', 'city', 'phone', 'bio']
        labels = {
            'profile_picture': 'Foto Profilo',
            'birth_date': 'Data di Nascita',
            'city': 'Città',
            'phone': 'Telefono',
            'bio': 'Biografia',
        }
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 4}),
        }


class AthleteSetupForm(forms.ModelForm):
    """Form specifico atleta"""
    class Meta:
        model = AthleteProfile
        fields = ['height', 'weight', 'position', 'jersey_number', 'current_team']
        labels = {
            'height': 'Altezza (cm)',
            'weight': 'Peso (kg)',
            'position': 'Ruolo',
            'jersey_number': 'Numero Maglia',
            'current_team': 'Squadra Attuale',
        }


class CoachSetupForm(forms.ModelForm):
    """Form specifico allenatore — senza tipo licenza, specializzazione con opzioni"""
    SPECIALIZATION_CHOICES = [
        ('', '--- Seleziona ---'),
        ('portieri', 'Portieri'),
        ('attacco', 'Attacco'),
        ('difesa', 'Difesa'),
        ('atletica', 'Preparazione Atletica'),
        ('tattica', 'Tattica'),
        ('giovanile', 'Settore Giovanile'),
        ('altro', 'Altro'),
    ]

    specialization = forms.ChoiceField(
        choices=SPECIALIZATION_CHOICES,
        required=False,
        label='Specializzazione',
    )
    specialization_other = forms.CharField(
        required=False,
        label='Specifica Specializzazione',
        widget=forms.TextInput(attrs={
            'placeholder': 'Descrivi la tua specializzazione...',
            'class': 'specialization-other-field',
        }),
    )

    class Meta:
        model = CoachProfile
        fields = ['current_team', 'years_experience', 'specialization', 'specialization_other']
        labels = {
            'current_team': 'Squadra Attuale',
            'years_experience': 'Anni di Esperienza',
        }


class RefereeSetupForm(forms.ModelForm):
    """Form specifico arbitro — label italiane, livello con opzioni"""
    LICENSE_LEVEL_CHOICES = [
        ('', '--- Seleziona ---'),
        ('regionale', 'Regionale'),
        ('interregionale', 'Interregionale'),
        ('nazionale', 'Nazionale'),
        ('internazionale', 'Internazionale'),
        ('altro', 'Altro'),
    ]

    license_level = forms.ChoiceField(
        choices=LICENSE_LEVEL_CHOICES,
        required=False,
        label='Livello Arbitrale',
    )
    license_level_other = forms.CharField(
        required=False,
        label='Specifica Livello',
        widget=forms.TextInput(attrs={
            'placeholder': 'Descrivi il tuo livello arbitrale...',
            'class': 'license-level-other-field',
        }),
    )

    class Meta:
        model = RefereeProfile
        fields = ['license_number', 'license_level', 'license_level_other']
        labels = {
            'license_number': 'Numero Tessera',
        }


class FanSetupForm(forms.Form):
    """Form per fan — selezione campionato→squadra e ricerca atleta"""
    league = forms.ChoiceField(
        choices=[('', '--- Seleziona Campionato ---')],
        required=False,
        label='Campionato',
    )
    favorite_team = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    athlete_search = forms.CharField(
        required=False,
        label='Cerca Atleta',
        widget=forms.TextInput(attrs={
            'placeholder': 'Scrivi nome e cognome dell\'atleta...',
            'id': 'athlete-search-input',
            'autocomplete': 'off',
        }),
    )
    favorite_player_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'favorite-player-id'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import League
        league_choices = [('', '--- Seleziona Campionato ---')]
        league_choices += [(l.id, str(l)) for l in League.objects.all().order_by('name')]
        self.fields['league'].choices = league_choices

