import atexit
import os
import xml.etree.ElementTree as ET

from colcon_core.event.job import JobEnded
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.plugin_system import satisfies_version


class TesultsEventHandler(EventHandlerExtensionPoint):
    """Upload test results to Tesults after colcon test completes."""

    ENABLED_BY_DEFAULT = True

    def __init__(self):
        super().__init__()
        satisfies_version(EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._cases = []
        try:
            import tesults as _tesults
            self._tesults = _tesults
        except ImportError:
            self._tesults = None
        atexit.register(self._upload)

    def __call__(self, event):
        data = event[0]
        if not isinstance(data, JobEnded):
            return
        if not self.enabled:
            return
        if not os.environ.get('TESULTS_TARGET'):
            return

        build_base = getattr(getattr(self.context, 'args', None), 'build_base', 'build')
        package_dir = os.path.join(build_base, data.identifier)
        if not os.path.isdir(package_dir):
            return

        for dirpath, _, filenames in os.walk(package_dir):
            for fname in sorted(filenames):
                if not fname.endswith('.xml'):
                    continue
                path = os.path.join(dirpath, fname)
                self._cases.extend(_parse_junit(path))

    def _upload(self):
        if not self.enabled or not self._cases:
            return
        target = os.environ.get('TESULTS_TARGET', '')
        if not target:
            return

        config_path = os.environ.get('TESULTS_CONFIG', '')
        if config_path:
            target = _lookup_config(config_path, target)

        if self._tesults is None:
            print('colcon-tesults: tesults package not installed, skipping upload')
            return

        cases = list(self._cases)

        build_name = os.environ.get('TESULTS_BUILD_NAME', '')
        if build_name:
            build_result = os.environ.get('TESULTS_BUILD_RESULT', '')
            build_case = {
                'name': build_name,
                'suite': '[build]',
                'result': build_result if build_result in ('pass', 'fail') else 'unknown',
                'rawResult': build_result,
            }
            build_desc = os.environ.get('TESULTS_BUILD_DESCRIPTION', '')
            build_reason = os.environ.get('TESULTS_BUILD_REASON', '')
            if build_desc:
                build_case['desc'] = build_desc
            if build_reason:
                build_case['reason'] = build_reason
            cases.append(build_case)

        print('colcon-tesults: uploading results...')
        resp = self._tesults.results({'target': target, 'results': {'cases': cases}})
        print(f"colcon-tesults: success: {resp['success']}")
        if not resp['success']:
            print(f"colcon-tesults: message: {resp['message']}")
        for w in resp.get('warnings', []):
            print(f"colcon-tesults: warning: {w}")
        for e in resp.get('errors', []):
            print(f"colcon-tesults: error: {e}")


def _parse_junit(path):
    cases = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        if root.tag == 'testsuites':
            suites = root.findall('testsuite')
        elif root.tag == 'testsuite':
            suites = [root]
        else:
            return cases

        for suite_el in suites:
            suite_attr = suite_el.get('name', '')
            for tc in suite_el.findall('testcase'):
                name = tc.get('name', 'unknown')
                classname = tc.get('classname', '')

                # Derive suite: last component of classname is most specific.
                # Fall back to testsuite name, skipping generic values like 'pytest'.
                if classname and classname not in ('pytest',):
                    suite = classname.split('.')[-1]
                elif suite_attr and suite_attr not in ('pytest',):
                    suite = suite_attr
                else:
                    suite = ''

                failure = tc.find('failure')
                error = tc.find('error')
                skipped = tc.find('skipped')

                if failure is not None:
                    result = 'fail'
                    reason = failure.get('message', '') or (failure.text or '').strip()
                elif error is not None:
                    result = 'fail'
                    reason = error.get('message', '') or (error.text or '').strip()
                elif skipped is not None:
                    result = 'unknown'
                    reason = skipped.get('message', '')
                else:
                    result = 'pass'
                    reason = ''

                case = {'name': name, 'result': result}
                if suite:
                    case['suite'] = suite
                if reason:
                    case['reason'] = reason
                cases.append(case)
    except Exception:
        pass
    return cases


def _lookup_config(config_path, key):
    try:
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, _, v = line.partition('=')
                    if k.strip() == key:
                        return v.strip()
    except Exception:
        pass
    return key
