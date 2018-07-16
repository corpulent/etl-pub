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


class WorkflowHandler(object):
    def __init__(self, workflow_doc, **kwargs):
        self.workflow_doc = workflow_doc
        self.data = None
        self.steps = self._sort_steps(self.workflow_doc.get('steps'))
        self.unit_handlers = self._get_unit_handlers()
        self.source = self.workflow_doc.get('source', -1)
        self.events = []

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

    def _store_data(self, data, data_source):
        if data_source == 'data':
            self.data = data

    def process_etsy_request(self, conn_etsy, **kwargs):
        """Process Etsy request."""
        url = kwargs.get('url')
        steps = kwargs.get('steps')
        method = kwargs.get('method')
        doc = kwargs.get('doc')
        doc_data = doc['data']
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
                print(doc_data)
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

        #print(doc)
        #print(doc_data)

        if doc_data['operation'] == 'read':
            pass
            # If no URL params in query (if the request.GET is not set)
            # then populate it with query from the entity doc.
            #self.update_request_object(doc_data['query'])
            #self.handle_entity_fetch(doc_data)

        if doc_data['operation'] == 'create':
            data = self._get_data(doc_data.get('get_data_on'))
            
            #ignore_results = doc_data.get('ignore_results', False)

            for data_item in data['results']:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': 'JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoyLCJ1c2VybmFtZSI6ImFydGVtIiwiZXhwIjoxNTMxOTIwMTU2LCJlbWFpbCI6ImFydGVtZ29sdWJAZ21haWwuY29tIiwib3JpZ19pYXQiOjE1MzE3NDczNTZ9.6FsA3_wydwvWcry6Wcnfvc4CTjMR0PSP93aiZfoOqWk'
                }
                payload = {
                    'doc_data': data_item,
                    'classifiers': doc_data['classifiers'],
                    'attachments': doc_data['attachments'],
                    'configs': {
                        'compound': doc_data['compound'],
                        'unique_fields': doc_data['unique_fields'],
                        'merge': doc_data['merge']
                    }
                }

                print(json.dumps(payload))

                response = requests.post(
                    'http://data-gate.us-east-1.elasticbeanstalk.com/data_gate/in/1/?mapper_id=1',
                    data = json.dumps(payload),
                    headers=headers
                )

                print(response.status_code)
                print(response.reason)

            #self.catalog_ids = self._check_catalogs(
            #    entity_doc.get('catalogs'))
            #
            #if 'results' in data and not ignore_results:
            #    for record in data['results']:
            #        self.process_single_entity(entity_doc, record)
            #
            #if isinstance(data, dict):
            #    self.process_single_entity(entity_doc, data)

    def run(self, passed_steps=False):
        """Run workflow process working step by step."""
        run_steps = self.steps

        if passed_steps:
            run_steps = passed_steps

        for idx, unit_item in enumerate(run_steps):
            print("Running step {}, type {}...".format(idx, unit_item['type']))

            self._run_units(unit_item)
