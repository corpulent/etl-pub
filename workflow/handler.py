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
import operator
from collections import defaultdict
from functools import reduce
from jsonpath_ng import parse
from currency_converter import CurrencyConverter

from requests import (
    Request,
    Session,
    RequestException
)

from .connectors.wordpress.api import API
from .connectors.etsy import main
from .connectors.woocomm import WooComm

from .actions import Iterate
from .utils import form_doc


ENDPOINT_ROOT_URL = 'http://localhost'


class WorkflowHandler(object):
    def __init__(self, workflow_doc, **kwargs):
        infinitedict = lambda: defaultdict(infinitedict)

        self.workflow_doc = workflow_doc
        self.data = infinitedict()
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
        local_data = response['results']

        self._put_data(local_data, doc_data['store_data_on'])

        steps = doc_data.get('steps', False)

        self._run_steps(steps)

        if next_set:
            page = int(page) + 1

            self._handle_entity_fetch(doc, page=page)

    def _handle_single_entity_fetch(self, doc):
        print("_handle_single_entity_fetch")

        doc_data = doc['data']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': doc_data['jwt_token']
        }
        endpoint_url = "{}/entities/{}/{}".format(
            ENDPOINT_ROOT_URL,
            doc_data['org_id'],
            doc_data['entity_id']
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
        self._put_data(response['doc_data'], doc_data['store_data_on'])
        steps = doc_data.get('steps', False)
        self._run_steps(steps)

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

    def _dict_put(self, keys, item):
        keys = keys.split(".")
        lastplace = reduce(operator.getitem, keys[:-1], self.data)
        lastplace[keys[-1]] = item

    def _dict_get(self, keys):
        try:
            keys = keys.split(".")
            return reduce(operator.getitem, keys, self.data)
        except AttributeError as err:
            pass

    def _get_data(self, get_data_on):
        return self._dict_get(get_data_on)

    def _put_data(self, data, path):
        self._dict_put(path, data)

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

            for result in listings_generator:
                # In special cases save specific payloads into data, and
                # everything else are the results.
                try:
                    if result['type'] == 'ListingInventory':
                        self._put_data(result, doc_data.get('store_data_on'))

                    if result['type'] == 'Listing':
                        self._put_data(result['results'], doc_data.get('store_data_on'))
                except KeyError as err:
                    self._put_data(result['results'], doc_data.get('store_data_on'))

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

    def _make_paginated_woocomm_request(self, woocomm, endpoint, offset, per_page):
        response = woocomm.http_get(endpoint, offset, per_page)

        return response

    def _unit_action_connector_wordpress(self, doc):
        doc_data = doc['data']
        method = doc_data.get('method', 'get').lower()
        wp_url = doc_data.get('wp_url')
        wp_user = doc_data.get('wp_user')
        wp_pass = doc_data.get('wp_pass')
        consumer_key = doc_data.get('consumer_key')
        consumer_secret = doc_data.get('consumer_secret')
        expected_codes = doc_data.get('expects_response_code')
        endpoint = doc_data.get('endpoint')
        get_data_on = doc_data.get('get_data_on')
        steps = doc_data.get('steps')
        data = self._get_data(get_data_on)
        response = {}
        wpapi = API(
            url=wp_url,
            api="wp-json",
            version='wp/v2',
            wp_user=wp_user,
            wp_pass=wp_pass,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            basic_auth=True,
            user_auth=True,
        )

        if doc_data.get('vars'):
            var_list = doc_data.get('vars').items()
            vars_mapped = self._map_variables(var_list, data)

            for k, v in vars_mapped.items():
                endpoint = endpoint.replace("$%s" % k, str(v))

        if method == 'delete':
            try:
                response = wpapi.delete(endpoint)
            except UserWarning as err:
                pass

        if steps:
            self._run_steps(steps)

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
        image_size = doc_data.get('image_size', 'url_fullxfull')
        do_hacky_shit = doc_data.get('do_hacky_shit', False)
        tmp_data = False
        data = self._get_data(get_data_on)
        response = {}
        woocomm = WooComm(
            doc,
            url=url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )

        if method in ['post', 'put']:
            custom = doc_data.get('custom')
            formatted_object = data

            if custom:
                formatted_object = woocomm._generate_custom_structure(
                    formatted_object,
                    image_size=image_size
                )

            if generate_attributes:
                formatted_object = woocomm._generate_attributes(formatted_object)

            if generate_variations:
                formatted_object = woocomm._generate_variations(formatted_object)

            if doc_data.get('export_mapper'):
                mapper = doc_data.get('export_mapper')
                _map = mapper['map']
                cconverter = CurrencyConverter()
                amount = formatted_object['price']
                currency_code = formatted_object['currency_code']
                amount_in_usd = cconverter.convert(amount, currency_code, 'USD')
                D = decimal.Decimal
                cent = D('0.01')
                x = D(amount_in_usd)
                formatted_object['price'] = str(x.quantize(cent,rounding=decimal.ROUND_UP))
                _map_copy = copy.copy(_map)
                mapped_obj = form_doc(formatted_object, _map_copy)

                if 'ignored_parts' in mapped_obj:
                    ignored_parts = mapped_obj.pop('ignored_parts')
                    mapped_obj = {**mapped_obj, **ignored_parts}

                tmp_data = mapped_obj

        # Hack!
        if do_hacky_shit:
            if method == 'delete':
                match = re.search(r'\d+$', data['_links']['up'][0]['href'])

                try:
                    match = re.search(r'\d+$', data['_links']['up'][0]['href'])
                    data['product_id'] = int(match.group())
                except KeyError as err:
                    pass


        # Because this happens here after the data gets mapped propely above,
        # the pagination of entities has to be one at a time.
        if doc_data.get('vars'):
            var_list = doc_data.get('vars').items()
            vars_mapped = self._map_variables(var_list, data)

            for k, v in vars_mapped.items():
                endpoint = endpoint.replace("$%s" % k, str(v))

        # Making a POST only if woocomm_listing_id is not set.
        if method == 'post':
            try:
                if not tmp_data['woocomm_listing_id']:
                    raise KeyError()
            except KeyError as err:
                print("{} KeyError, woocomm_listing_id is not set for a create request, proceeding...".format(str(err)))
                response = woocomm.http_post(endpoint, tmp_data)

        if method == 'put':
            try:
                if not tmp_data['id']:
                    raise KeyError()
                
                response = woocomm.http_put(endpoint, tmp_data)
            except KeyError as err:
                print("{} KeyError, woocommerce listing 'id' is not set for an update request, ignoring...".format(str(err)))

        if method == 'get':
            paginated = doc_data.get('paginated', None)
            per_page = doc_data.get('per_page', None)
            offset = doc_data.get('offset', None)

            if paginated:
                keep_paginating = True

                while keep_paginating:
                    response = self._make_paginated_woocomm_request(woocomm, endpoint, 0, per_page)

                    if response:
                        self._put_data(response, doc_data['store_data_on'])

                        if steps:
                            self._run_steps(steps)
                    else:
                        keep_paginating = False

            else:
                response = woocomm.http_get(endpoint, offset, per_page)

        if method == 'delete':
            response = woocomm.http_delete(endpoint)

        if method == 'options':
            response = woocomm.http_options(endpoint)

        self.http_response_data = response
        self._put_data(response, doc_data['store_data_on'])

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
            try:
                if doc_data['entity_id']:
                    self._handle_single_entity_fetch(doc)
            except KeyError as err:
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
        loop_path = doc_data.get('loop_path', '$')
        loop_path_jsonpath_expr = parse(loop_path)
        path = doc_data.get('path', '$')
        steps = doc_data.get('steps', False)
        jsonpath_expr = parse(path)
        data = self._get_data(doc_data['get_data_on'])
        loop_data = data

        try:
            loop_data = [match.value for match in loop_path_jsonpath_expr.find(loop_data) if match.value][0]
        except IndexError as err:
            print('path {} not found in the data set'.format(loop_path))
            pass

        if loop_data and isinstance(loop_data, list):
            for data_item in loop_data:
                try:
                    temp_data = [match.value for match in jsonpath_expr.find(data_item) if match.value][0]
                except IndexError as err:
                    print('path {} not found in the data set'.format(path))
                    sys.exit(1)

                if temp_data:
                    self._put_data(temp_data, doc_data['store_data_on'])
                    self._run_steps(steps)
        else:
            pass

    def _unit_stop(self, doc):
        doc_data = doc['data']

        self.return_response_body = doc_data.get('return_response_body', True)

    def run(self, passed_steps=False):
        """Run workflow process working step by step."""
        run_steps = self.steps

        if passed_steps:
            run_steps = passed_steps

        for idx, unit_item in enumerate(run_steps):
            print("============")
            print("============> Running STEP {}, TYPE {}...".format(idx, unit_item['type']))
            print("============")

            self._run_units(unit_item)
