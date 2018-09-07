#!/usr/bin/python3

import os
import json
import re

from sys import argv

from workflow.handler import WorkflowHandler


def getopts(argv):
    opts = {}

    while argv:
        if argv[0][0] == '-':
            opts[argv[0]] = argv[1]

        argv = argv[1:]

    return opts


if __name__ == '__main__':
    myargs = getopts(argv)
    workflow_data = {}
    dir_path = os.path.dirname(os.path.realpath(__file__))
    etsy_shop_url = myargs['-etsy_shop_url']
    etsy_oauth_token = myargs['-etsy_oauth_token']
    etsy_oauth_token_secret = myargs['-etsy_oauth_token_secret']
    etsy_consumer_key = myargs['-etsy_consumer_key']
    etsy_consumer_secret = myargs['-etsy_consumer_secret']
    jwt_token = "JWT {}".format(myargs['-jwt_token'])
    org_id = myargs['-org_id']
    import_mapper_id = myargs['-import_mapper_id']

    with open(os.path.join(
            dir_path,
            'workflow/workflow_configs/import_etsy_listing.json')) as json_file:
        workflow_data = json.load(json_file)

    workflow_data_json = json.dumps(workflow_data)
    workflow_data_json = re.sub(r'__JWT_TOKEN__', jwt_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ORG_ID__', org_id, workflow_data_json)
    workflow_data_json = re.sub(r'__IMPORT_MAPPER_ID__', import_mapper_id, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_SHOP_URL__', etsy_shop_url, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN__', etsy_oauth_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN_SECRET__', etsy_oauth_token_secret, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_KEY__', etsy_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_SECRET__', etsy_consumer_secret, workflow_data_json)

    handler = WorkflowHandler(
        json.loads(workflow_data_json),
        data_gate_url=myargs['-data_gate_url'],
    )

    handler.run()
