"""WSL: two consecutive unmodified Buildozer builds, Gradle and APK DEX checks.

No clean, generated-file patches, spec rewrites, or dependency/version changes.
Use check_android_capture.py --fix-aar-repository once before this verifier.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

try:
    from tools.check_android_capture import check_spec, check_gradle_project, check_apk, project_root, read_spec
except ModuleNotFoundError:
    from check_android_capture import check_spec, check_gradle_project, check_apk, project_root, read_spec


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _hash_stream(stream)


def _hash_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024*1024), b''):
        digest.update(block)
    return digest.hexdigest()


def verify(spec, gradle_project, apk, report, executable='buildozer', run=subprocess.run):
    spec = Path(spec).resolve()
    base = spec.parent
    gradle_project, apk, report = ((base/Path(path)).resolve() for path in (gradle_project, apk, report))
    state = {'complete':False, 'spec':str(spec), 'gradle_project':str(gradle_project),
             'apk':str(apk), 'passes':[]}
    def save():
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_name(report.name+'.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(report)
    save()  # A failed/cancelled run must not leave a previous success report.
    try:
        if spec.name != 'buildozer.spec':
            raise ValueError('Buildozer must run beside the actual buildozer.spec file')
        errors = check_spec(spec)
        if errors: raise ValueError('; '.join(errors))
        original = spec.read_bytes()
        source_root = project_root(spec, read_spec(spec))
        gradle_file = gradle_project/'build.gradle'
        for number in (1,2):
            previous_stamp = gradle_file.stat().st_mtime_ns if gradle_file.exists() else None
            print(f'BUILD_{number}_START', flush=True)
            run([executable, '-v', 'android', 'debug'], cwd=base, check=True)
            if spec.read_bytes() != original:
                raise ValueError('Spec changed during build; consecutive unchanged builds were not verified')
            if not gradle_file.is_file():
                raise ValueError('Generated build.gradle missing; check --gradle-project')
            if gradle_file.stat().st_mtime_ns == previous_stamp:
                raise ValueError('build.gradle was not regenerated; cannot claim regeneration survived this build')
            check_gradle_project(gradle_project, source_root)
            dex = check_apk(apk)
            apk_hash = sha256(apk)
            outputs = list((gradle_project/'build/outputs/apk/debug').glob('*.apk'))
            matching = next((path for path in outputs if sha256(path) == apk_hash), None)
            if matching is None:
                raise ValueError('Selected APK does not match a produced Gradle debug APK; check --apk')
            state['passes'].append({'number':number, 'gradle_regenerated':True,
                                    'repository_and_aar_checked':True, 'capture_class_dex':dex,
                                    'gradle_sha256':sha256(gradle_file), 'apk_sha256':apk_hash,
                                    'gradle_output_apk':str(matching)})
            save()
            print(f'BUILD_{number}_VERIFIED CAPTURE_CLASS_DEFINED_IN_DEX {dex}', flush=True)
        state['complete'] = True
        save()
        return state
    except Exception as exc:
        state['error'] = str(exc)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=Path(__file__).resolve().parents[1]/'buildozer.spec')
    parser.add_argument('--gradle-project', type=Path, required=True)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('bin/capture-two-builds.json'))
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('Run this verifier in the actual WSL/Linux Buildozer environment')
    executable = shutil.which('buildozer')
    if not executable:
        parser.error('Buildozer not found; activate the existing WSL build environment')
    try:
        verify(args.spec,args.gradle_project,args.apk,args.report,executable)
    except Exception as exc:
        print('TWO_BUILDS_NOT_VERIFIED: '+str(exc))
        return 1
    print('TWO_BUILDS_VERIFIED: both regenerated Gradle projects and APK class definitions passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
