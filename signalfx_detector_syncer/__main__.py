#!/usr/bin/env python

# Copyright (C) 2016-2018 SignalFx, Inc. All rights reserved.

import argparse
import logging
import signalfx
import sys

from . import syncer, version


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--version', action='store_true',
                       help='show version information')
    group.add_argument('-t', '--token',
                       help='authentication token')
    parser.add_argument('--scope', help='An optional base scope')
    parser.add_argument('-a', '--api-endpoint',
                        help='SignalFx API endpoint')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='dry-run mode, do not update detectors')
    parser.add_argument('-D', '--debug', action='store_const',
                        dest='loglevel',
                        const=logging.DEBUG, default=logging.WARNING,
                        help='enable debug logging')
    parser.add_argument('-v', '--verbose', action='store_const',
                        dest='loglevel',
                        const=logging.INFO,
                        help='enable verbose logging')
    parser.add_argument('directory', nargs='?', default='.',
                        help='Source directory')

    options = parser.parse_args()
    if options.version:
        print('{} v{}'.format(version.name, version.version))
        return

    logging.basicConfig(stream=sys.stderr, level=options.loglevel,
                        format='%(asctime)s | %(levelname)8s | %(message)s')
    logging.getLogger('requests').setLevel(logging.WARNING)

    sfx = signalfx.SignalFx(api_endpoint=options.api_endpoint)
    client = syncer.Syncer(sfx.rest(options.token, timeout=5),
                           options.scope,
                           options.dry_run)
    client.sync(options.directory)


if __name__ == '__main__':
    sys.exit(main())
