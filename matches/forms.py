from django import forms
from .models import MatchReport
from .services.hash_service import HashService

class MatchReportUploadForm(forms.ModelForm):
    class Meta:
        model = MatchReport
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'w-full p-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-bold file:bg-blue-500/20 file:text-blue-400 hover:file:bg-blue-500/30',
                'accept': 'application/pdf,image/*'
            })
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # 1. Calcolo Hash
            file_hash = HashService.calculate_sha256(file)
            
            # 2. Verifica duplicati
            existing = MatchReport.objects.filter(file_hash=file_hash).first()
            if existing:
                raise forms.ValidationError(
                    f"Questo file è già stato caricato in precedenza (Report ID: {existing.id})."
                )
            
            # Salviamo l'hash nel cleaned_data per usarlo nel save se necessario
            self.cleaned_data['file_hash'] = file_hash
        return file

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.file_hash = self.cleaned_data.get('file_hash', '')
        if commit:
            instance.save()
        return instance

class MatchReportAdminForm(forms.ModelForm):
    """Form dedicato all'admin per includere la deduplica."""
    class Meta:
        model = MatchReport
        fields = ['match', 'file', 'source_channel', 'status', 'internal_notes']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['match'].required = False

    def clean_file(self):
        file = self.cleaned_data.get('file')
        # La deduplica serve solo in creazione (se il file cambia o è nuovo)
        if file and (not self.instance.pk or self.instance.file != file):
            file_hash = HashService.calculate_sha256(file)
            existing = MatchReport.objects.filter(file_hash=file_hash).exclude(pk=self.instance.pk).first()
            if existing:
                raise forms.ValidationError(
                    f"Questo file è già stato caricato in precedenza (Report ID: {existing.id})."
                )
            self.cleaned_data['file_hash'] = file_hash
        return file

    def clean(self):
        cleaned_data = super().clean()
        source_channel = cleaned_data.get('source_channel')
        file = cleaned_data.get('file')
        
        if source_channel == 'FILE' and not file:
            self.add_error('file', "Un referto con canale 'FILE / OCR' deve obbligatoriamente avere un file allegato.")
        
        return cleaned_data
class MatchReportReviewForm(forms.Form):
    # Match fields
    home_score = forms.IntegerField(label="Gol Casa", required=True, min_value=0)
    away_score = forms.IntegerField(label="Gol Trasferta", required=True, min_value=0)
    
    # Quarter scores
    home_q1 = forms.IntegerField(label="Q1 Casa", required=True, min_value=0, initial=0)
    home_q2 = forms.IntegerField(label="Q2 Casa", required=True, min_value=0, initial=0)
    home_q3 = forms.IntegerField(label="Q3 Casa", required=True, min_value=0, initial=0)
    home_q4 = forms.IntegerField(label="Q4 Casa", required=True, min_value=0, initial=0)
    
    away_q1 = forms.IntegerField(label="Q1 Trasferta", required=True, min_value=0, initial=0)
    away_q2 = forms.IntegerField(label="Q2 Trasferta", required=True, min_value=0, initial=0)
    away_q3 = forms.IntegerField(label="Q3 Trasferta", required=True, min_value=0, initial=0)
    away_q4 = forms.IntegerField(label="Q4 Trasferta", required=True, min_value=0, initial=0)
    
    is_finished = forms.BooleanField(label="Partita Conclusa", required=False)
    
    # Report fields
    report_status = forms.ChoiceField(
        label="Stato Referto",
        choices=MatchReport.Status.choices,
        initial=MatchReport.Status.VALIDATED
    )
    validation_notes = forms.CharField(
        label="Note di Validazione",
        widget=forms.Textarea(attrs={'rows': 3, 'readonly': 'readonly'}),
        required=False,
        help_text="Note di sistema (Sola Lettura)"
    )
    internal_notes = forms.CharField(
        label="Note Interne (Staff)",
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Note visibili solo allo staff"
    )

    def __init__(self, *args, **kwargs):
        self.home_roster = kwargs.pop('home_roster', [])
        self.away_roster = kwargs.pop('away_roster', [])
        super().__init__(*args, **kwargs)
        
        # Add dynamic player goal fields
        for athlete in self.home_roster:
            self.fields[f'player_goals_home_{athlete.user.id}'] = forms.IntegerField(
                label=f"Gol {athlete.user.get_full_name()}",
                required=True,
                min_value=0,
                initial=0
            )
        for athlete in self.away_roster:
            self.fields[f'player_goals_away_{athlete.user.id}'] = forms.IntegerField(
                label=f"Gol {athlete.user.get_full_name()}",
                required=True,
                min_value=0,
                initial=0
            )

        # Styling general fields
        for field_name, field in self.fields.items():
            if field_name not in ['validation_notes', 'internal_notes', 'is_finished']:
                field.widget.attrs.update({
                    'class': 'w-full p-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 focus:border-blue-500 transition-all text-sm'
                })
            elif field_name in ['validation_notes', 'internal_notes']:
                 field.widget.attrs.update({
                    'class': 'w-full p-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-300'
                })
            elif field_name == 'is_finished':
                 field.widget.attrs.update({
                    'class': 'w-6 h-6 rounded bg-slate-900 border-slate-700 text-blue-500 focus:ring-blue-500'
                })

    def clean(self):
        cleaned_data = super().clean()
        home_score = cleaned_data.get('home_score')
        away_score = cleaned_data.get('away_score')
        status = cleaned_data.get('report_status')

        # 1. Validation for Quarter Scores
        home_quarters = [cleaned_data.get(f'home_q{i}', 0) for i in range(1, 5)]
        away_quarters = [cleaned_data.get(f'away_q{i}', 0) for i in range(1, 5)]
        
        # ONLY if validating or publishing
        if status in [MatchReport.Status.VALIDATED, MatchReport.Status.PUBLISHED]:
            if sum(home_quarters) != home_score:
                self.add_error('home_score', f"I parziali casa ({sum(home_quarters)}) non corrispondono al totale ({home_score}).")
            if sum(away_quarters) != away_score:
                self.add_error('away_score', f"I parziali trasferta ({sum(away_quarters)}) non corrispondono al totale ({away_score}).")

            # 2. Validation for Player Goals
            if self.home_roster:
                home_player_goals = sum([cleaned_data.get(f'player_goals_home_{a.user.id}', 0) for a in self.home_roster])
                if home_player_goals != home_score:
                    self.add_error('home_score', f"La somma dei gol giocatori casa ({home_player_goals}) non corrisponde al totale ({home_score}).")
            elif home_score > 0:
                self.add_error('home_score', "Roster casa vuoto ma il punteggio è maggiore di zero. Impossibile attribuire i gol.")

            if self.away_roster:
                away_player_goals = sum([cleaned_data.get(f'player_goals_away_{a.user.id}', 0) for a in self.away_roster])
                if away_player_goals != away_score:
                    self.add_error('away_score', f"La somma dei gol giocatori trasferta ({away_player_goals}) non corrisponde al totale ({away_score}).")
            elif away_score > 0:
                self.add_error('away_score', "Roster trasferta vuoto ma il punteggio è maggiore di zero. Impossibile attribuire i gol.")

        return cleaned_data
