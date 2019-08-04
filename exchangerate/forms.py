from django import forms
from django.utils import timezone


class ExchangeRequestForm(forms.Form):
    base_currency = forms.CharField()
    target_currency = forms.CharField()
    amount = forms.DecimalField()
    max_waiting_time = forms.IntegerField()
    start_date = forms.DateField()

    def clean_start_date(self):
        data = self.cleaned_data['start_date']
        if data.weekday() > 4:
            raise forms.ValidationError("Exchange market is closed on weekends.")
        if (data - timezone.now().date()).days > 50:
            raise forms.ValidationError("Date can't be more than 50 days from the today.")
        return data
