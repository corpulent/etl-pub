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
    
    woocomm_vendor_id = "64"
    woocomm_consumer_key = "ck_5e7085a0f3eb541fb145bb8342b01544c3587732"
    woocomm_consumer_secret = "cs_c4c64b92ffe707ab42ba9da2ae908b0a1983fa8c"
    woocomm_url = "https://staging.joinmarrakesh.com"

    etsy_shop_url = "/shops/spapla/listings/active"
    etsy_oauth_token = "77f72d2fa194c3193cd2b5f2ef695b"
    etsy_oauth_token_secret = "e62d628635"
    etsy_consumer_key = "rmqw209x8t1zzvaft9hfa0pc"
    etsy_consumer_secret = "9fyavx5q0d"
    jwt_token = "JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo5LCJ1c2VybmFtZSI6InRlc3RfdXNlcl8xIiwiZXhwIjoxNTMyNjk0NDA2LCJlbWFpbCI6InRlc3RfdXNlcl8zQHRlc3QuY29tIiwib3JpZ19pYXQiOjE1MzI1MjE2MDZ9.3n4PgBLKCtkBCHm2VOS8kZPLefik93spRV5kdhfif7c"
    org_id = "10"
    import_mapper_id = "3"

    with open(os.path.join(dir_path, 'workflow/workflow_configs/woocomm_delete_products.json')) as json_file:
        workflow_data = json.load(json_file)

    workflow_data_json = json.dumps(workflow_data)

    workflow_data_json = re.sub(r'__JWT_TOKEN__', jwt_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ORG_ID__', org_id, workflow_data_json)
    workflow_data_json = re.sub(r'__IMPORT_MAPPER_ID__', import_mapper_id, workflow_data_json)

    workflow_data_json = re.sub(r'__ETSY_SHOP_URL__', etsy_shop_url, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN__', etsy_oauth_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_KEY__', etsy_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_CONSUMER_SECRET__', etsy_consumer_secret, workflow_data_json)
    workflow_data_json = re.sub(r'__ETSY_OAUTH_TOKEN_SECRET__', etsy_oauth_token_secret, workflow_data_json)

    workflow_data_json = re.sub(r'__WOOCOMM_VENDOR_ID__', woocomm_vendor_id, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_URL__', woocomm_url, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_KEY__', woocomm_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_SECRET__', woocomm_consumer_secret, workflow_data_json)

    handler = WorkflowHandler(json.loads(workflow_data_json))

    handler.run()

    if '-s' in myargs:
        print(myargs['-s'])
