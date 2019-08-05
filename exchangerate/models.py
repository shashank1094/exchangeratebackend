# https://www.analyticsvidhya.com/blog/2018/02/time-series-forecasting-methods/

import copy
import datetime
import pandas as pd
import numpy as np
from statsmodels.tsa.api import ExponentialSmoothing
import requests
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Currency(TimeStampedModel):
    name = models.SlugField(unique=True, db_index=True)

    class Meta:
        db_table = 'currency'


class ExchangeRate(TimeStampedModel):
    base_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='as_base')
    target_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='as_target')
    rate = models.DecimalField(decimal_places=10, max_digits=30)
    date = models.DateField()

    class Meta:
        db_table = 'exchange_rate'

    @classmethod
    def get_data(cls, cleaned_data):
        base = cleaned_data.get('base_currency')
        target = cleaned_data.get('target_currency')
        from_date = cleaned_data.get('before_date')
        to_date = cleaned_data.get('start_date')
        cached_data_queryset = list(cls.objects.filter(base_currency__name__iexact=base,
                                                       target_currency__name__iexact=target,
                                                       date__gte=from_date,
                                                       date__lte=to_date).order_by('date'))
        make_request = True
        request_parameters = copy.deepcopy(cleaned_data)
        if cached_data_queryset:
            if cached_data_queryset[0].date == from_date:
                request_parameters['before_date'] = cached_data_queryset[-1].date
            else:
                request_parameters['start_date'] = cached_data_queryset[0].date
            if request_parameters['before_date'] == request_parameters['start_date']:
                make_request = False

        request_url = "https://api.exchangeratesapi.io/history?start_at={before_date}&end_at={start_date}&symbols={" \
                      "target_currency}&base={base_currency}".format(**request_parameters)
        items_to_be_inserted = []
        if make_request:
            response = requests.get(request_url, verify=False)
            if response.status_code == requests.status_codes.codes.OK:
                result = response.json()
                temp_base_currency = result.get('base')
                temp_base_currency_obj, _ = Currency.objects.get_or_create(name=temp_base_currency)
                rates_list = list(result.get('rates', {}).items())
                all_currencies = set()
                if rates_list:
                    for x in list(rates_list[0][1].items()):
                        all_currencies.add(x[0])
                existing_currencies = Currency.objects.all()
                existing_currencies_name = set(list((existing_currencies.values_list('name', flat=True).distinct())))
                names_to_be_added = all_currencies - existing_currencies_name
                if names_to_be_added:
                    Currency.objects.bulk_create([Currency(name=x) for x in names_to_be_added])
                db_currencies = Currency.objects.all()
                temp_target_currency_obj_dict = {}
                for x in db_currencies:
                    temp_target_currency_obj_dict[x.name.lower()] = x
                for x in rates_list:
                    temp_date, temp_rate_dict = datetime.datetime.strptime(x[0], '%Y-%m-%d').date(), x[1]
                    for y in list(temp_rate_dict.items()):
                        temp_target_currency, temp_rate = y
                        temp_target_currency_obj = temp_target_currency_obj_dict.get(temp_base_currency.lower())
                        if temp_target_currency_obj:
                            temp_exchange_obj = cls(base_currency=temp_base_currency_obj,
                                                    target_currency=temp_target_currency_obj,
                                                    date=temp_date, rate=temp_rate)
                            items_to_be_inserted.append(temp_exchange_obj)
            else:
                raise Exception(str(response.json()))
        if items_to_be_inserted:
            cls.objects.bulk_create(items_to_be_inserted)
        total_data = cached_data_queryset + items_to_be_inserted
        return sorted(total_data, key=lambda t: t.date)


class Extrapolation:
    def __init__(self, list_of_objs, requested_data=None):
        if requested_data is None:
            requested_data = {}
        self.start_date = requested_data.get('start_date')
        self.waiting_period = requested_data.get('max_waiting_time', 5)
        self.following_days = self.get_following_days()
        self.data = self.convert_queryset(list_of_objs)
        self.predicted_data = []
        self.graph = None
        self.table = None

    def get_following_days(self):
        result = []
        if self.waiting_period and self.start_date:
            for x in range(self.waiting_period + 1):
                temp_date = self.start_date + datetime.timedelta(x)
                if temp_date.weekday() <= 4:
                    result.append(temp_date)
            if result:
                self.waiting_period = len(result)
        return result

    def convert_queryset(self, list_of_objects):
        if not list_of_objects or not self.start_date:
            return None
        end_date = self.start_date
        data = {'Rates': [x.rate for x in list_of_objects]}
        df = pd.DataFrame(data,
                          index=[end_date - datetime.timedelta(x) for x in range(len(list_of_objects) - 1, -1, -1)])
        df.index = pd.to_datetime(df.index, format='%Y-%m-%d')
        return df

    def compute_predictions(self):
        if self.data is None or self.data.empty:
            return
        fit1 = ExponentialSmoothing(np.asarray(self.data['Rates']), seasonal_periods=5, trend='add',
                                    seasonal='add', ).fit()
        x = fit1.forecast(self.waiting_period)
        self.predicted_data = list(x)
