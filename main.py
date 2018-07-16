#!/usr/bin/python3
import os
import json

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

    with open(os.path.join(dir_path, 'workflow/workflow_configs/import_etsy_listing.json')) as json_file:
        workflow_data = json.load(json_file)

    handler = WorkflowHandler(workflow_data)

    handler.run()

    if '-s' in myargs:
        print(myargs['-s'])
