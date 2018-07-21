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
    woocomm_consumer_key = "ck_d8bbddae15cfc4f29a46ada4eae7609df19317a7"
    woocomm_consumer_secret = "cs_5a20f0076cf0ee1d6489467c8f660880a7384fa0"
    woocomm_url = "https://staging.joinmarrakesh.com"
    etsy_oauth_token = "eae61b95f71e5be1a0ab98a08beffc"
    etsy_consumer_key = "rmqw209x8t1zzvaft9hfa0pc"
    etsy_consumer_secret = "9fyavx5q0d"
    etsy_oauth_token_secret = "8520709438"
    jwt_token = "JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo5LCJ1c2VybmFtZSI6InRlc3RfdXNlcl8xIiwiZXhwIjoxNTMyMjkyNzc1LCJlbWFpbCI6InRlc3RfdXNlcl8zQHRlc3QuY29tIiwib3JpZ19pYXQiOjE1MzIxMTk5NzV9.FiUtINUbSNvSw5fSAXagm_rPXPrHiqIsJVapPtziqDU"
    org_id = "10"
    import_mapper_id = "4"

    with open(os.path.join(dir_path, 'workflow/workflow_configs/woocomm_create_products_variations.json')) as json_file:
        workflow_data = json.load(json_file)

    workflow_data_json = json.dumps(workflow_data)

    workflow_data_json = re.sub(r'__JWT_TOKEN__', jwt_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ORG_ID__', org_id, workflow_data_json)
    workflow_data_json = re.sub(r'__IMPORT_MAPPER_ID__', import_mapper_id, workflow_data_json)

    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN__', etsy_oauth_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_KEY__', etsy_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_SECRET__', etsy_consumer_secret, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN_SECRET__', etsy_oauth_token_secret, workflow_data_json)

    workflow_data_json = re.sub(r'__WOOCOMM_URL__', woocomm_url, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_KEY__', woocomm_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_SECRET__', woocomm_consumer_secret, workflow_data_json)

    handler = WorkflowHandler(json.loads(workflow_data_json))

    handler.run()

    if '-s' in myargs:
        print(myargs['-s'])
