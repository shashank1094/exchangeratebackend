from django.shortcuts import render
from django.views import View
import datetime
from exchangerate.forms import ExchangeRequestForm
from .models import ExchangeRate, Extrapolation


class MyFormView(View):
    form_class = ExchangeRequestForm
    initial = {'key': 'value'}
    template_name = 'exchangerate/exchange_request_template.html'

    def get(self, request, *args, **kwargs):
        form = self.form_class(initial=self.initial)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        errors = None
        following_days, predicted_data, currency = None, None, None
        if form.is_valid():
            cleaned_data = form.cleaned_data
            cleaned_data['before_date'] = cleaned_data.get('start_date') - datetime.timedelta(days=60)
            try:
                data = ExchangeRate.get_data(cleaned_data)
                extrapolation = Extrapolation(data, cleaned_data)
                extrapolation.compute_predictions()
                following_days = list(map(lambda x: x.strftime("%Y-%m-%d"), extrapolation.following_days))
                predicted_data = list(map(lambda x: x*float(cleaned_data.get('amount')), extrapolation.predicted_data))
                currency = cleaned_data.get('target_currency')
            except Exception as e:
                errors = str(e)
        return render(request, self.template_name,
                      {'form': form, 'errors': errors, 'following_days': following_days,
                       'predicted_data': predicted_data, "currency": currency})
