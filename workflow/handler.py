import re
import os
import sys
import shutil
import json
import collections
import boto3
import copy
import decimal
import requests

from jsonpath_ng import parse
from currency_converter import CurrencyConverter

from requests import (
    Request,
    Session,
    RequestException
)

from .connectors.etsy import main
from .connectors.woocomm import WooComm

from .actions import Iterate
from .utils import form_doc


ENDPOINT_ROOT_URL = 'http://localhost:9001'


class WorkflowHandler(object):
    def __init__(self, workflow_doc, **kwargs):
        self.workflow_doc = workflow_doc
        self.data = None
        self.immutable = None
        self.http_response_data = None
        self.steps = self._sort_steps(self.workflow_doc.get('steps'))
        self.unit_handlers = self._get_unit_handlers()
        self.source = self.workflow_doc.get('source', -1)
        self.events = []

        self.return_response_body = True

    def _handle_entity_save(self, doc, data):
        doc_data = doc['data']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': doc_data['jwt_token']
        }
        payload = {
            'doc_data': data,
            'classifiers': doc_data['classifiers'],
            'attachments': doc_data['attachments'],
            'configs': {
                'compound': doc_data['compound'],
                'unique_fields': doc_data['unique_fields'],
                'merge': doc_data['merge']
            }
        }
        endpoint_url = "{}/data_gate/in/{}/?mapper_id={}".format(
            ENDPOINT_ROOT_URL,
            doc_data['org_id'],
            doc_data['import_mapper_id']
        )

        ret = requests.post(
            endpoint_url,
            data = json.dumps(payload),
            headers=headers
        )

        return ret

    def _handle_entity_fetch(self, doc, page=1):
        print("_handle_entity_fetch page {}".format(page))

        doc_data = doc['data']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': doc_data['jwt_token']
        }
        endpoint_url = "{}/entities/{}/?page={}&page_size=1".format(
            ENDPOINT_ROOT_URL,
            doc_data['org_id'],
            page
        )

        response = requests.get(
            endpoint_url,
            headers=headers
        )

        if response.status_code in [401, 404]:
            print('Got a response error {}, reason: {}'.format(
                response.status_code,
                response.reason))
            return

        response = response.json()
        next_set = response['links']['next']
        # Need only a single result.
        local_data = response['results']

        self._store_data(local_data, doc_data['store_data_on'])

        steps = doc_data.get('steps', False)

        self._run_steps(steps)

        if next_set:
            page = int(page) + 1

            self._handle_entity_fetch(doc, page=page)

    def _get_unit_handlers(self):
        """Collects references for all unit handlers."""
        handlers = {func[6:]: getattr(self, func) for
                    func in dir(self) if func.startswith('_unit')}

        return handlers

    def _sort_steps(self, steps):
        """Sort steps by order number."""
        return sorted(steps, key=lambda k: k['order'])

    def _run_units(self, unit):
        """Run a single workflow unit."""
        # If unit type is implemented within handler run it.
        if unit['type'] in self.unit_handlers:
            handler = self.unit_handlers.get(unit['type'])

            handler(unit)

    def _run_steps(self, steps):
        """Check if the doc has steps to run, then run them."""
        if steps:
            steps = self._sort_steps(steps)

            self.run(steps)

    def _get_data(self, get_data_on):
        if get_data_on == 'data':
            return self.data

        if get_data_on == 'immutable':
            return self.immutable

        if get_data_on == 'http_response_data':
            return self.http_response_data

    def _store_data(self, data, data_source):
        if data_source == 'data':
            self.data = data

        if data_source == 'immutable':
            self.immutable = data

        if data_source == 'http_response_data':
            self.http_response_data = data

    def process_etsy_request(self, conn_etsy, **kwargs):
        """Process Etsy request."""
        doc = kwargs.get('doc')
        doc_data = doc['data']
        url = kwargs.get('url')
        steps = kwargs.get('steps')
        method = kwargs.get('method')
        params = doc_data.get('params', None)
        vars_mapped = {}
        data = self._get_data(doc_data.get('get_data_on'))

        if doc_data.get('vars'):
            var_list = doc_data.get('vars').items()

            for k, v in var_list:
                jsonpath_expr = parse(v)
                vars_mapped[k] = [match.value for match in jsonpath_expr.find(data)][0]

            for k, v in vars_mapped.items():
                url = url.replace("$%s" % k, str(v))

        if method == 'get':
            if params:
                listings_generator = conn_etsy.iterate_pages(
                    'execute_authed',
                    url,
                    params=params
                )
            else:
                listings_generator = conn_etsy.iterate_pages(
                    'execute_authed',
                    url
                )

            for listings in listings_generator:
                # In special cases save specific payloads into data, and
                # everything else are the results.
                try:
                    if listings['type'] == 'ListingInventory':
                        self._store_data(listings, doc_data.get('store_data_on'))

                    if listings['type'] == 'Listing':
                        self._store_data(listings['results'], doc_data.get('store_data_on'))
                except KeyError as err:
                    self._store_data(listings['results'], doc_data.get('store_data_on'))

                self._run_steps(steps)

        if method == 'post':
            mapper = doc_data.get('export_mapper')
            _map = mapper['map']

            if isinstance(self.data, list):
                mapped_list = [form_doc(i, _map) for i in self.data]

                self.data = mapped_list
            else:
                self.data = form_doc(self.data, _map)

            if isinstance(self.data, list):
                for item in self.data:
                    conn_etsy.create_listings(payload=item)
            else:
                conn_etsy.create_listings(payload=self.data)

    def _map_variables(self, var_list, data):
        """Map values to variables in the car_list."""
        vars_mapped = {}

        for k, v in var_list:
            jsonpath_expr = parse(v)
            found_data = jsonpath_expr.find(data)
            vars_mapped[k] = [match.value for match in found_data][0]
        
        return vars_mapped

    def _unit_action_connector_woocommerce(self, doc, offset=None):
        doc_data = doc['data']
        url = doc_data.get('url')
        method = doc_data.get('method', 'get').lower()
        consumer_key = doc_data.get('consumer_key')
        consumer_secret = doc_data.get('consumer_secret')
        expected_codes = doc_data.get('expects_response_code')
        endpoint = doc_data.get('endpoint')
        get_data_on = doc_data.get('get_data_on')
        steps = doc_data.get('steps')
        generate_attributes = doc_data.get('generate_attributes', False)
        generate_variations = doc_data.get('generate_variations', False)
        tmp_data = False
        data = self._get_data(get_data_on)
        woocomm = WooComm(
            doc,
            url=url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )

        if method in ['post', 'put']:
            custom = doc_data.get('custom')
            doc_data_list = []

            for key, val in enumerate(data):
                doc_data_list.append(val['doc_data'])

            if custom:
                for key, val in enumerate(doc_data_list):
                    doc_data_list[key] = woocomm._generate_custom_structure(val)

            if generate_attributes:
                for key, val in enumerate(doc_data_list):
                    doc_data_list[key] = woocomm._generate_attributes(val)

            if generate_variations:
                for key, val in enumerate(doc_data_list):
                    doc_data_list[key] = woocomm._generate_variations(val)

            if doc_data.get('export_mapper'):
                mapper = doc_data.get('export_mapper')
                _map = mapper['map']
                cconverter = CurrencyConverter()
                mapped_list = []

                for i in doc_data_list:
                    amount = i['price']
                    currency_code = i['currency_code']
                    amount_in_usd = cconverter.convert(amount, currency_code, 'USD')
                    D = decimal.Decimal
                    cent = D('0.01')
                    x = D(amount_in_usd)
                    i['price'] = str(x.quantize(cent,rounding=decimal.ROUND_UP))

                    _map_copy = copy.copy(_map)
                    mapped_obj = form_doc(i, _map_copy)

                    if 'ignored_parts' in mapped_obj:
                        ignored_parts = mapped_obj.pop('ignored_parts')
                        mapped_obj = {**mapped_obj, **ignored_parts}

                    mapped_list.append(mapped_obj)

                tmp_data = mapped_list

        # Because this happens here after the data gets mapped propely above,
        # the pagination of entities has to be one at a time.
        if data:
            if doc_data.get('vars'):
                var_list = doc_data.get('vars').items()
                vars_mapped = self._map_variables(var_list, data[0]['doc_data'])

                for k, v in vars_mapped.items():
                    endpoint = endpoint.replace("$%s" % k, str(v))

        if method == 'post':
            if isinstance(tmp_data, list):
                response = []

                for val in tmp_data:
                    try:
                        if not val['woocomm_listing_id']:
                           raise KeyError('woocomm_listing_id is empty')
                    except KeyError as err:
                        print('{} woocomm_listing_id does not exist,'
                            'creating a new product.'.format(err))
                        response.append(woocomm.http_post(endpoint, val))

        if method == 'put':
            if isinstance(tmp_data, list):
                response = []

                for val in tmp_data:
                    response.append(woocomm.http_put(endpoint, val))

        if method == 'get':
            with_offset = doc.get('with_offset', False)
            per_page = doc.get('per_page')

            if with_offset:
                if offset is None:
                    offset = 0

                offset = offset + per_page

            response = woocomm.http_get(endpoint, offset, per_page)

        if method == 'delete':
            response = woocomm.http_delete(endpoint)

        if method == 'options':
            response = woocomm.http_options(endpoint)

        if expected_codes:
            expected_codes = [str(code) for code in expected_codes]

        if isinstance(response, list):
            self.http_response_data = []

            for response_item in response:
                #if response_item['status_code'] < 200 or response_item['status_code'] >= 300:
                #    data = response_item.json()
                self.http_response_data.append(response_item)

        if steps:
            self._run_steps(steps)

    def _unit_connector_etsy(self, doc):
        doc_data = doc['data']
        consumer_key = doc_data.get('consumer_key')
        consumer_secret = doc_data.get('consumer_secret')
        oauth_token = doc_data.get('oauth_token')
        oauth_token_secret = doc_data.get('oauth_token_secret')
        paginated = doc_data.get('paginated')
        endpoint = doc_data.get('endpoint')
        steps = doc_data.get('steps')
        method = doc_data.get('method', 'get').lower()
        export_mapper = doc_data.get('export_mapper')
        url = doc_data.get('url')
        conn_etsy = main.Etsy(
            consumer_key,
            consumer_secret,
            oauth_token=oauth_token,
            oauth_token_secret=oauth_token_secret
        )

        self.process_etsy_request(
            conn_etsy,
            paginated=paginated,
            endpoint=endpoint,
            steps=steps,
            method=method,
            url=url,
            export_mapper=export_mapper,
            doc=doc
        )

    def _unit_entity(self, doc):
        """
        Operate on the entity objects.

        The classifiers and catalogs on creation are merged.
        """
        doc_data = doc['data']

        if doc_data['operation'] == 'read':
            self._handle_entity_fetch(doc)

        if doc_data['operation'] == 'create':
            data = self._get_data(doc_data.get('get_data_on'))

            if data and isinstance(data, list):
                for data_item in data:
                    self._handle_entity_save(doc, data_item)

            if data and isinstance(data, dict):
                self._handle_entity_save(doc, data)

    def _unit_loop(self, doc):
        doc_data = doc['data']
        path = doc_data.get('path', '$')
        steps = doc_data.get('steps', False)
        jsonpath_expr = parse(path)
        data = self._get_data(doc_data['get_data_on'])

        if data and isinstance(data, list):
            temp_data = [match.value for match in jsonpath_expr.find(data) if match.value][0]

            if temp_data:
                for obj in temp_data:
                    self._store_data(obj, doc_data['store_data_on'])
                    self._run_steps(steps)

    def _unit_stop(self, doc):
        doc_data = doc['data']

        self.return_response_body = doc_data.get('return_response_body', True)

    def run(self, passed_steps=False):
        """Run workflow process working step by step."""
        run_steps = self.steps

        if passed_steps:
            run_steps = passed_steps

        for idx, unit_item in enumerate(run_steps):
            print("Running step {}, type {}...".format(idx, unit_item['type']))

            self._run_units(unit_item)
