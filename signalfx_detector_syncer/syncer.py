# Copyright (C) 2016-2018 SignalFx, Inc. All rights reserved.

import logging
import json
import os
import re
import yaml

_logger = logging.getLogger(__name__)


class Syncer(object):
    """Utility to sync detectors defined in individual YAML files to their
    counterpart in SignalFx.

    Each detector is defined is its own file as a two-document YAML. The
    front-matter defines the detector properties (as the detector model); the
    second document is the SignalFlow program text of the detector itself.
    """

    _SYNCER_MARKER_TAG = 'signalfx-detector-syncer'
    _FROM_TAG_PREFIX = 'from:'
    _SCOPE_TAG_PREFIX = 'scope:'

    def __init__(self, client, scope=None, dry_run=False):
        self._client = client
        self._scope = scope
        self._dry_run = dry_run

        self._tags = [self._SYNCER_MARKER_TAG]
        if scope:
            self._tags.append(self._SCOPE_TAG_PREFIX + scope)

    def _d(self, detector_path):
        if self._scope:
            return '{} (in scope {})'.format(detector_path, self._scope)
        return detector_path

    def _filter_predicate(self, entry):
        return ((entry.endswith(('.yaml', '.yml', '.json'))) and
                not entry.startswith('.'))

    def sync(self, base_path):
        from_files = self.load_files(base_path, self._filter_predicate)
        from_files_paths = set(from_files.keys())
        _logger.info('Loaded %d detector(s) from %s.',
                     len(from_files),
                     base_path)

        from_signalfx = self.load_from_signalfx()
        from_signalfx_paths = set(from_signalfx.keys())
        _logger.info('Found %d detector(s) from sync in SignalFx.',
                     len(from_signalfx))

        new, common, removed = (
            from_files_paths.difference(from_signalfx_paths),
            from_files_paths.intersection(from_signalfx_paths),
            from_signalfx_paths.difference(from_files_paths)
        )

        updated = []
        for path in common:
            original = from_signalfx[path]
            detector = from_files[path]
            if detector['lastUpdated'] > original['lastUpdated']:
                updated.append(path)

        _logger.info('Status: %d new, %d in common (%d updated), %d removed.',
                     len(new), len(common), len(updated), len(removed))

        for path in new:
            self.create_detector(path, from_files[path])
        for path in updated:
            self.update_detector(path, from_signalfx[path], from_files[path])
        for path in removed:
            self.remove_detector(path, from_signalfx[path])

    def load_files(self, base_path, predicate=None):
        """Loads all detectors from the given base path and all its sub
        directories.

        Args:
            base_path (string): path to the directory containing detector
                files.
            predicate (lambda): a predicate to filter files from the given
                directory.
        Returns:
            A dictionary of the loaded detectors, keyed by the file path name.
        """
        base_path = os.path.abspath(base_path) + os.path.sep
        predicate = predicate or (lambda e: True)
        _logger.info('Loading detectors from %s...', base_path)

        detectors = {}
        for t in os.walk(base_path):
            scope = t[0].split(base_path)[1]
            for f in filter(predicate, t[2]):
                path = os.path.join(scope, f)
                detectors[path] = self._load_detector(base_path, path)
        return detectors

    def _load_detector(self, base_path, path):
        """Load a detector from a given location.

        Args:
            base_path (string): absolute base path from which detectors are
                synced from.
            path (string): relative path to the file containing the detector.
        Returns:
            The loaded detector model.
        """
        file_path = os.path.join(base_path, path)
        with open(file_path) as f:
            contents = f.read()

        if contents.startswith('{'):
            detector = _JsonDetectorLoader().load(path, contents)
        elif contents.startswith('---\n'):
            detector = _YamlDetectorLoader().load(path, contents)
        else:
            raise ValueError('unknown detector format')

        # Set lastUpdated from the file's last modified time.
        # TODO(mpetazzoni): is this ok for git checkouts?
        last_change_ms = int(os.stat(file_path).st_mtime * 1000)
        detector['lastUpdated'] = last_change_ms

        # Add tags
        tags = detector.get('tags', [])
        tags.extend(self._tags)
        tags.append(self._FROM_TAG_PREFIX + path)
        detector['tags'] = tags

        return detector

    def load_from_signalfx(self):
        """Load all detectors from SignalFx that were created by this syncer
        under the given team identifier.

        All detectors that have a description matching the
        _DESCRIPTION_NAME_PATTERN are returned. Those are detectors that were
        created by this syncer and that should be considered.
        """
        def by_path(detector):
            tags = set(detector['tags'])
            path = None

            # Find the tag with the name tag prefix and extract the detector
            # source file path from it.
            for tag in tags:
                # If we don't have a scope, we need to make sure we're not
                # returning detectors that have one.
                if not self._scope and tag.startswith(self._SCOPE_TAG_PREFIX):
                    return None
                if tag.startswith(self._FROM_TAG_PREFIX):
                    path = tag.split(self._FROM_TAG_PREFIX)[1]

            return (path, detector) if path else None

        return dict(filter(None,
                           map(by_path,
                               self._client.get_detectors(tags=self._tags))))

    def create_detector(self, path, detector):
        """Create the given detector."""
        if not self._dry_run:
            _logger.info('Creating detector %s...', self._d(path))
            _logger.debug('Detector: %s', detector)
            created = self._client.create_detector(detector)
            _logger.info('Created detector %s [%s].',
                         self._d(path), created['id'])
        else:
            _logger.info('Validating new detector %s...', path)
            _logger.debug('Detector: %s', detector)
            self._client.validate_detector(detector)
            _logger.info('Detector %s is valid.', path)

    def update_detector(self, path, original, detector):
        """Update the given detector."""
        if not self._dry_run:
            _logger.info('Updating detector %s [%s]...',
                         self._d(path), original['id'])
            _logger.debug('Detector: %s', detector)
            updated = self._client.update_detector(original['id'], detector)
            _logger.info('Updated detector %s [%s].',
                         self._d(path), updated['id'])
        else:
            _logger.info('Validating updated detector %s...', path)
            _logger.debug('Detector: %s', detector)
            self._client.validate_detector(detector)
            _logger.info('Detector %s is valid.', path)

    def remove_detector(self, path, detector):
        """Remove the given detector."""
        if not self._dry_run:
            _logger.info('Removing detector %s [%s]...',
                         self._d(path), detector['id'])
            _logger.debug('Detector: %s', detector)
            self._client.delete_detector(detector['id'],
                                         ignore_not_found=True)
            self._client.delete_tag(self._FROM_TAG_PREFIX + path,
                                    ignore_not_found=True)
            _logger.info('Removed detector %s [%s].',
                         self._d(path), detector['id'])
        else:
            _logger.info('Skipped removal of detector %s.',
                         self._d(path))


class _DetectorLoader(object):
    """Base class for detector loaders."""

    def _load(self, path, contents):
        raise NotImplementedError

    def load(self, path, contents):
        detector = self.validate(self._load(path, contents))

        # Coerce rules into a list with detectLabels instead of a dict (the API
        # is silly).
        rules = detector.get('rules', [])
        if type(rules) is dict:
            rules_list = []
            for label, rule in rules.items():
                rule['detectLabel'] = label
                rules_list.append(rule)
            detector['rules'] = rules_list

        return detector

    def validate(self, detector):
        if not detector['name']:
            raise ValueError('missing detector name')
        if not detector['description']:
            raise ValueError('detector should have a description')
        if type(detector.get('rules', [])) not in [list, dict]:
            raise ValueError('invalid rules object')
        return detector


class _JsonDetectorLoader(_DetectorLoader):
    """Detector loader from JSON file contents."""

    def _load(self, path, contents):
        _logger.debug('Loading %s as JSON.', path)
        return json.loads(contents)


class _YamlDetectorLoader(_DetectorLoader):
    """Detector loader from YAML file contents."""

    _SPLITTER = re.compile(r'^---$', re.MULTILINE)

    def _load(self, path, contents):
        _logger.debug('Loading %s as YAML.', path)
        docs = list(map(str.strip,
                        filter(None, self._SPLITTER.split(contents))))
        detector = yaml.load(docs[0])
        detector['programText'] = docs[1]
        return detector
