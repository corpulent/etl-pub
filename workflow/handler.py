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

from woocommerce import API
from jsonpath_ng import parse
from currency_converter import CurrencyConverter

from requests import (
    Request,
    Session,
    RequestException
)

from .connectors.etsy import main

from .actions import Iterate
from.utils import form_doc


ENDPOINT_ROOT_URL = 'http://data-gate.us-east-1.elasticbeanstalk.com'


class WorkflowHandler(object):
    def __init__(self, workflow_doc, **kwargs):
        self.workflow_doc = workflow_doc
        self.data = None
        self.immutable = None
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

        return requests.post(
            endpoint_url,
            data = json.dumps(payload),
            headers=headers
        )

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

    def _store_data(self, data, data_source):
        if data_source == 'data':
            self.data = data

        if data_source == 'immutable':
            self.immutable = data

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
                self._store_data(listings, doc_data.get('store_data_on'))
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
                for data_item in data['results']:
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
            local_data = [match.value for match in jsonpath_expr.find(data) if match.value][0]

            if local_data:
                for obj in local_data:
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
