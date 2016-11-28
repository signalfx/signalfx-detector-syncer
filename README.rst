Sync utility for SignalFx detectors
===================================

`sfx-sync-detectors` is a command-line tool that helps keep SignalFx detectors
in version control and sync them with SignalFx. It operates over a directory of
files, each representing a detector, and makes sure that what is in SignalFx
matches the contents of that directory.

Installation
~~~~~~~~~~~~

.. code::

  $ pip install signalfx-detector-syncer

Usage
~~~~~

.. code::

  $ sfx-sync-detectors --token=$SFX_AUTH_TOKEN /path/to/detectors/

How it works
~~~~~~~~~~~~

The syncer works by file name. Each detector is written in its own file, either
in JSON or YAML format and named as an easily identifiable
``dash-separated-slug`` (``.json`` or ``.yaml``). This slug name identifies the
detector: updates to the same file will update the existing detector. Creating
a new file creates a new detector; removing a file removes the corresponding
detector from SignalFx.

JSON
^^^^

When the file contains JSON, it is expected to contain the direct JSON
detector model that would be pushed to SignalFx's detector API.

YAML layout
^^^^^^^^^^^

For YAML (more human readable!), each file contains two YAML documents
separated by the expected ``---`` line. The first document, the *front
matter*, defines the configuration of the detector and its rules and
notifications. The second document is the SignalFlow 2.0 program text of
the detector.

.. code-block:: yaml

  ---
  name: The detector name
  description: The detector description
  rules:
    my label:
      severity: Critical
      description: Something's wrong!
      notifications:
        - type: email
          email: test@test.com
  ---

  detect(when(data('demo.trans.latency') > 220, lasting='5s')).publish('my label')

Specification
^^^^^^^^^^^^^

.. _detector API: https://developers.signalfx.com/docs/detector

The specification of the *front matter* that configures the detector is
pretty much what the `detector API`_ expects. The only expection is that rules
may directly keyed by the detect label they map to if you want to.
