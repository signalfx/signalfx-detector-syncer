#!/usr/bin/env python

# Copyright (C) 2016 SignalFx, Inc. All rights reserved.

import argparse
import logging
import signalfx
import sys

from . import syncer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--token', required=True,
                        help='Authentication token')
    parser.add_argument('--team', help='An optional team identifier')
    parser.add_argument('-a', '--api-endpoint',
                        help='SignalFx API endpoint')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='Dry-run mode, do not update detectors')
    parser.add_argument('-D', '--debug', action='store_const',
                        dest='loglevel',
                        const=logging.DEBUG, default=logging.WARNING,
                        help='Enable debug logging')
    parser.add_argument('-v', '--verbose', action='store_const',
                        dest='loglevel',
                        const=logging.INFO,
                        help='Enable verbose logging')
    parser.add_argument('directory', default='.', help='Source directory')

    options = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=options.loglevel)
    logging.getLogger('requests').setLevel(logging.WARNING)

    sfx = signalfx.SignalFx(api_endpoint=options.api_endpoint)
    client = syncer.Syncer(sfx.rest(options.token),
                           options.team,
                           options.dry_run)
    client.sync(options.directory)


if __name__ == '__main__':
    sys.exit(main())
