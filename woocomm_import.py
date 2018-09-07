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
    
    woocomm_vendor_id = myargs['-woocomm_vendor_id']
    woocomm_consumer_key = myargs['-woocomm_consumer_key']
    woocomm_consumer_secret = myargs['-woocomm_consumer_secret']
    woocomm_url = myargs['-woocomm_url']

    # Basic authentication with the admin user.
    # This plugin needs to be installed on the
    # wordpress end https://github.com/WP-API/Basic-Auth
    wp_user = myargs['-wp_user']
    wp_pass = myargs['-wp_pass']

    jwt_token = "JWT {}".format(myargs['-jwt_token'])
    org_id = myargs['-org_id']
    import_mapper_id = myargs['-import_mapper_id']

    with open(os.path.join(
            dir_path,
            'workflow/workflow_configs/{}.json'.format(myargs['-action_type']))) as json_file:
        workflow_data = json.load(json_file)

    workflow_data_json = json.dumps(workflow_data)

    workflow_data_json = re.sub(r'__JWT_TOKEN__', jwt_token, workflow_data_json)
    workflow_data_json = re.sub(r'__ORG_ID__', org_id, workflow_data_json)
    workflow_data_json = re.sub(r'__IMPORT_MAPPER_ID__', import_mapper_id, workflow_data_json)

    workflow_data_json = re.sub(r'__WOOCOMM_VENDOR_ID__', woocomm_vendor_id, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_URL__', woocomm_url, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_KEY__', woocomm_consumer_key, workflow_data_json)
    workflow_data_json = re.sub(r'__WOOCOMM_CONSUMER_SECRET__', woocomm_consumer_secret, workflow_data_json)

    workflow_data_json = re.sub(r'__WP_URL__', woocomm_url, workflow_data_json)
    workflow_data_json = re.sub(r'__WP_USER__', wp_user, workflow_data_json)
    workflow_data_json = re.sub(r'__WP_PASS__', wp_pass, workflow_data_json)

    handler = WorkflowHandler(
        json.loads(workflow_data_json),
        data_gate_url=myargs['-data_gate_url'],
    )

    handler.run()
