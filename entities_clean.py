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

    handler = WorkflowHandler(
        json.loads(workflow_data_json),
        data_gate_url=myargs['-data_gate_url'],
    )

    handler.run()
