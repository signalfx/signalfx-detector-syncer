#!/usr/bin/env python

# Copyright (C) 2016-2018 SignalFx, Inc. All rights reserved.
# Copyright (C) 2019-2022 Splunk, Inc. All rights reserved.

from setuptools import setup, find_packages

with open('signalfx_detector_syncer/version.py') as f:
    exec(f.read())

with open('README.rst') as readme:
    long_description = readme.read()

with open('requirements.txt') as f:
    requirements = [line.strip() for line in f.readlines()]

setup(
    name=name,  # noqa
    version=version,  # noqa
    author='Splunk, Inc',
    author_email='mpetazzoni@splunk.com',
    description='Splunk Observability / SignalFx detector sync utility',
    license='Apache Software License v2',
    long_description=long_description,
    zip_safe=True,
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'sfx-sync-detectors = signalfx_detector_syncer.__main__:main',
        ],
    },
    classifiers=[
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    url='https://github.com/signalfx/signalfx-detector-syncer',
)
