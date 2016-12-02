# Copyright (C) 2016 SignalFx, Inc. All rights reserved.

import logging
import json
import os
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
    _NAME_TAG_PREFIX = 'from:'
    _TEAM_TAG_PREFIX = 'team:'

    def __init__(self, client, team=None, dry_run=False):
        self._client = client
        self._team = team
        self._dry_run = dry_run

    def _filter_predicate(self, entry):
        return ((entry.endswith('.yaml') or entry.endswith('.json')) and
                not entry.startswith('.'))

    def sync(self, path):
        from_files = self.load_files(path, self._filter_predicate)
        from_files_names = set(from_files.keys())
        _logger.info('Loaded %d detector(s) from %s.', len(from_files), path)

        from_signalfx = self.load_from_signalfx()
        from_signalfx_names = set(from_signalfx.keys())
        _logger.info('Found %d detector(s) from sync in SignalFx.',
                     len(from_signalfx))

        new, common, removed = (
            from_files_names.difference(from_signalfx_names),
            from_files_names.intersection(from_signalfx_names),
            from_signalfx_names.difference(from_files_names)
        )

        updated = []
        for name in common:
            original = from_signalfx[name]
            detector = from_files[name]
            if detector['lastUpdated'] > original['lastUpdated']:
                updated.append(name)

        _logger.info('Status: %d new, %d in common (%d updated), %d removed.',
                     len(new), len(common), len(updated), len(removed))

        for name in new:
            self.create_detector(name, from_files[name])
        for name in updated:
            self.update_detector(name, original, detector)
        for name in removed:
            self.remove_detector(name, from_signalfx[name])

    def load_files(self, path, predicate=None):
        """Loads all detectors from the given path.

        Args:
            path (string): path to the directory containing detector files.
            predicate (lambda): a predicate to filter files from the given
                directory.
        Returns:
            A dictionary of the loaded detectors, keyed by the file name.
        """
        path = os.path.abspath(path)
        predicate = predicate or (lambda e: True)
        _logger.info('Loading detectors from %s...', path)
        return dict(
            map(self._load_detector,
                filter(lambda f: os.path.isfile(f),
                       map(lambda e: os.path.join(path, e),
                           filter(lambda f: predicate(f), os.listdir(path))))))

    def _load_detector(self, path):
        """Load a detector from the given file.

        Args:
            path (string): absolute path to the file containing the detector.
        Returns:
            The loaded detector model.
        """
        name = os.path.basename(path)
        with open(path) as f:
            contents = f.read()

        if contents.startswith('{'):
            detector = _JsonDetectorLoader().load(name, contents)
        elif contents.startswith('---\n'):
            detector = _YamlDetectorLoader().load(name, contents)
        else:
            raise ValueError('unknown detector format')

        # Set lastUpdated from the file's last modified time.
        # TODO(mpetazzoni): is this ok for git checkouts?
        last_change_ms = int(os.stat(path).st_mtime * 1000)
        detector[1]['lastUpdated'] = last_change_ms

        # Add tags
        tags = detector[1].get('tags', [])
        tags.extend([self._SYNCER_MARKER_TAG, self._NAME_TAG_PREFIX + name])
        if self._team:
            tags.append(self._TEAM_TAG_PREFIX + self._team)
        detector[1]['tags'] = tags

        return detector

    def load_from_signalfx(self):
        """Load all detectors from SignalFx that were created by this syncer
        under the given team identifier.

        All detectors that have a description matching the
        _DESCRIPTION_NAME_PATTERN are returned. Those are detectors that were
        created by this syncer and that should be considered.
        """
        def by_name(detector):
            tags = set(detector['tags'])
            # Ignore detectors that don't have the syncer marker tag.
            if self._SYNCER_MARKER_TAG not in tags:
                return None

            # Ignore detectors that don't match the synced team.
            team = [t for t in tags if t.startswith(self._TEAM_TAG_PREFIX)]
            if len(team) > 1:
                return None
            elif not self._team and team:
                return None
            elif self._team and not team:
                return None
            elif self._team != team[0].split(self._TEAM_TAG_PREFIX)[1]:
                return None

            # Find the tag with the name tag prefix and extract the detector
            # source filename from it.
            for tag in tags:
                if tag.startswith(self._NAME_TAG_PREFIX):
                    name = tag.split(self._NAME_TAG_PREFIX)[1]
                    return (name, detector)
            return None

        return dict(filter(None, map(by_name, self._client.get_detectors())))

    def create_detector(self, name, detector):
        """Create the given detector."""
        _logger.info('Creating new detector %s in SignalFx with tags %s...',
                     name, ','.join(detector['tags']))
        _logger.debug('Detector: %s', detector)
        if not self._dry_run:
            created = self._client.create_detector(detector)
            _logger.info('Created detector %s [%s].', name, created['id'])

    def update_detector(self, name, original, detector):
        """Update the given detector."""
        _logger.info('Updating detector %s [%s] in SignalFx...',
                     name, original['id'])
        _logger.debug('Detector: %s', detector)
        if not self._dry_run:
            updated = self._client.update_detector(original['id'], detector)
            _logger.info('Updated detector %s [%s].', name, updated['id'])

    def remove_detector(self, name, detector):
        """Remove the given detector."""
        _logger.info('Removing detector %s [%s] from SignalFx...',
                     name, detector['id'])
        _logger.debug('Detector: %s', detector)
        if not self._dry_run:
            self._client.delete_detector(detector['id'])
            self._client.delete_tag(self._NAME_TAG_PREFIX + name)
            _logger.info('Removed detector %s [%s].', name, detector['id'])


class _DetectorLoader(object):
    """Base class for detector loaders."""

    def _load(self, name, contents):
        raise NotImplementedError

    def load(self, name, contents):
        detector = self.validate(self._load(name, contents))

        # Coerce rules into a list with detectLabels instead of a dict (the API
        # is silly).
        rules = detector.get('rules', [])
        if type(rules) is dict:
            rules_list = []
            for label, rule in rules.items():
                rule['detectLabel'] = label
                rules_list.append(rule)
            detector['rules'] = rules_list

        return (name, detector)

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

    def _load(self, name, contents):
        _logger.debug('Loading %s as JSON.', name)
        return json.loads(contents)


class _YamlDetectorLoader(_DetectorLoader):
    """Detector loader from YAML file contents."""

    def _load(self, name, contents):
        _logger.debug('Loading %s as YAML.', name)
        docs = [d for d in yaml.load_all(contents)]
        detector = docs[0]
        detector['programText'] = docs[1]
        return detector
