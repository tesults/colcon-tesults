import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest import mock

from colcon_tesults import __version__
from colcon_tesults import event_handler


class FakeTesults:
    def __init__(self):
        self.uploads = []

    def results(self, data):
        self.uploads.append(data)
        return {'success': True, 'message': 'Success', 'warnings': [], 'errors': []}


class FakeJobEnded:
    def __init__(self, identifier):
        self.identifier = identifier


def make_handler(cases=None, tesults=None):
    handler = object.__new__(event_handler.TesultsEventHandler)
    handler.enabled = True
    handler._cases = list(cases or [])
    handler._tesults = tesults
    return handler


class TesultsEventHandlerTest(unittest.TestCase):
    def test_parse_junit_pass_fail_error_and_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results.xml'
            path.write_text(textwrap.dedent('''\
                <testsuites>
                  <testsuite name="pytest">
                    <testcase classname="pkg.Calculator" name="passes" />
                    <testcase classname="pkg.Calculator" name="fails">
                      <failure message="expected 2, got 1">trace</failure>
                    </testcase>
                    <testcase classname="pkg.Network" name="errors">
                      <error>connection refused</error>
                    </testcase>
                    <testcase name="skips">
                      <skipped message="not supported" />
                    </testcase>
                  </testsuite>
                </testsuites>
            '''), encoding='utf-8')

            cases = event_handler._parse_junit(path)

        mapped = {case['name']: case for case in cases}
        self.assertEqual(mapped['passes'], {
            'name': 'passes', 'result': 'pass', 'suite': 'Calculator'
        })
        self.assertEqual(mapped['fails']['result'], 'fail')
        self.assertEqual(mapped['fails']['reason'], 'expected 2, got 1')
        self.assertEqual(mapped['errors']['result'], 'fail')
        self.assertEqual(mapped['errors']['reason'], 'connection refused')
        self.assertEqual(mapped['skips']['result'], 'unknown')
        self.assertEqual(mapped['skips']['reason'], 'not supported')

    def test_output_only_writes_metadata_and_build_case(self):
        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / 'nested' / 'results.json'
            handler = make_handler([{'name': 'passes', 'suite': 'pkg', 'result': 'pass'}])
            environment = {
                'TESULTS_OUTPUT_FILE': str(output_file),
                'TESULTS_BUILD_NAME': 'build-42',
                'TESULTS_BUILD_RESULT': 'fail',
                'TESULTS_BUILD_DESCRIPTION': 'Build description',
                'TESULTS_BUILD_REASON': 'Build reason',
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                handler._upload()

            payload = json.loads(output_file.read_text(encoding='utf-8'))

        self.assertEqual(payload['target'], '')
        self.assertEqual(payload['metadata'], {
            'integration_name': 'colcon-tesults',
            'integration_version': '1.1.0',
            'test_framework': 'colcon',
        })
        self.assertEqual(len(payload['results']['cases']), 2)
        build = payload['results']['cases'][1]
        self.assertEqual(build['suite'], '[build]')
        self.assertEqual(build['name'], 'build-42')
        self.assertEqual(build['result'], 'fail')
        self.assertEqual(build['desc'], 'Build description')
        self.assertEqual(build['reason'], 'Build reason')

    def test_target_only_preserves_upload_behavior(self):
        uploader = FakeTesults()
        handler = make_handler([{'name': 'passes', 'result': 'pass'}], uploader)

        with mock.patch.dict(os.environ, {'TESULTS_TARGET': 'direct-target'}, clear=True):
            handler._upload()

        self.assertEqual(len(uploader.uploads), 1)
        self.assertEqual(uploader.uploads[0]['target'], 'direct-target')
        self.assertEqual(uploader.uploads[0]['results']['cases'][0]['name'], 'passes')
        self.assertEqual(uploader.uploads[0]['metadata']['integration_version'], '1.1.0')

    def test_output_only_writes_an_empty_report_when_no_tests_are_found(self):
        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / 'empty.json'
            handler = make_handler()
            with mock.patch.dict(
                    os.environ, {'TESULTS_OUTPUT_FILE': str(output_file)}, clear=True):
                handler._upload()
            payload = json.loads(output_file.read_text(encoding='utf-8'))

        self.assertEqual(payload['target'], '')
        self.assertEqual(payload['results']['cases'], [])
        self.assertEqual(payload['metadata']['integration_version'], '1.1.0')

    def test_combined_output_and_upload_have_matching_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / 'results.json'
            uploader = FakeTesults()
            handler = make_handler([{'name': 'fails', 'result': 'fail'}], uploader)
            environment = {
                'TESULTS_TARGET': 'combined-target',
                'TESULTS_OUTPUT_FILE': str(output_file),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                handler._upload()
            local_payload = json.loads(output_file.read_text(encoding='utf-8'))

        uploaded_payload = uploader.uploads[0]
        self.assertEqual(local_payload['target'], '')
        self.assertEqual(uploaded_payload['target'], 'combined-target')
        self.assertEqual(local_payload['results'], uploaded_payload['results'])
        self.assertEqual(local_payload['metadata'], uploaded_payload['metadata'])

    def test_output_error_does_not_prevent_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            uploader = FakeTesults()
            handler = make_handler([{'name': 'passes', 'result': 'pass'}], uploader)
            environment = {
                'TESULTS_TARGET': 'upload-after-error',
                'TESULTS_OUTPUT_FILE': directory,
            }
            stdout = io.StringIO()
            with mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch('sys.stdout', stdout):
                handler._upload()

        self.assertIn('error writing results file:', stdout.getvalue())
        self.assertEqual(len(uploader.uploads), 1)
        self.assertEqual(uploader.uploads[0]['target'], 'upload-after-error')

    def test_output_only_collects_package_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            build_base = Path(directory) / 'build'
            package_dir = build_base / 'demo_package'
            package_dir.mkdir(parents=True)
            (package_dir / 'results.xml').write_text(
                '<testsuite name="suite"><testcase name="collected" /></testsuite>',
                encoding='utf-8'
            )
            handler = make_handler()
            handler.context = mock.Mock(args=mock.Mock(build_base=str(build_base)))
            output_file = Path(directory) / 'results.json'
            with mock.patch.object(event_handler, 'JobEnded', FakeJobEnded), \
                    mock.patch.dict(os.environ, {'TESULTS_OUTPUT_FILE': str(output_file)}, clear=True):
                handler((FakeJobEnded('demo_package'),))

        self.assertEqual(handler._cases, [
            {'name': 'collected', 'result': 'pass', 'suite': 'suite'}
        ])

    def test_config_key_resolution_and_disabled_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'tesults.cfg'
            config.write_text('ci = configured-target\n', encoding='utf-8')
            uploader = FakeTesults()
            handler = make_handler([{'name': 'passes', 'result': 'pass'}], uploader)
            environment = {
                'TESULTS_TARGET': 'ci',
                'TESULTS_CONFIG': str(config),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                handler._upload()
            self.assertEqual(uploader.uploads[0]['target'], 'configured-target')

            disabled_uploader = FakeTesults()
            disabled = make_handler([{'name': 'passes', 'result': 'pass'}], disabled_uploader)
            with mock.patch.dict(os.environ, {}, clear=True):
                disabled._upload()
            self.assertEqual(disabled_uploader.uploads, [])

    def test_package_and_integration_versions_match(self):
        pyproject = Path(__file__).parents[1] / 'pyproject.toml'
        project_text = pyproject.read_text(encoding='utf-8')
        self.assertIn(f'version = "{__version__}"', project_text)
        self.assertEqual(event_handler._METADATA['integration_version'], __version__)


if __name__ == '__main__':
    unittest.main()
