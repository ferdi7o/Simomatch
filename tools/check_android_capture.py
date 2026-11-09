"""Run in the actual WSL project: check/apply capture spec keys and inspect APK DEX.

No Android SDK or extra dependencies required. --apply preserves unrelated spec
lines and creates a backup. --apk verifies a class definition, not just a string.
"""
import argparse
import configparser
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import struct
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

CLASS = 'org.simomatch.capture.CaptureService'
DESCRIPTOR = b'Lorg/simomatch/capture/CaptureService;'
JAVA = Path('android_src/org/simomatch/capture/CaptureService.java')
MANIFEST_AAR = 'android_src/capture_manifest.aar'
PERMISSIONS = ('FOREGROUND_SERVICE', 'FOREGROUND_SERVICE_MEDIA_PROJECTION', 'RECORD_AUDIO')
LIBS_REPOSITORY = "flatDir { dirs 'libs' }"
LIBS_REPOSITORY_PATTERN = r'''flatDir\s*\{\s*dirs\s*(?:['"](?:\./)?libs['"]|\(\s*['"](?:\./)?libs['"]\s*\))\s*\}'''


def has_libs_repository(value):
    # No enclosing quotes: current Buildozer passes list values literally to p4a.
    return any(re.fullmatch(LIBS_REPOSITORY_PATTERN, item.strip()) for item in value.split(','))


def validate_aar(path):
    with ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('AAR CRC validation failed')
        if not {'AndroidManifest.xml','classes.jar'}.issubset(archive.namelist()):
            raise ValueError('AAR missing manifest or classes.jar')
        xml = archive.read('AndroidManifest.xml')
        ElementTree.fromstring(xml)
        with ZipFile(BytesIO(archive.read('classes.jar'))) as jar:
            if jar.testzip():
                raise ValueError('AAR classes.jar CRC validation failed')
    return xml


def read_spec(path):
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(Path(path).read_text(encoding='utf-8-sig'))
    if not config.has_section('app'):
        raise ValueError('Missing [app] section')
    return config


def items(value):
    return [s.strip() for s in value.split(',') if s.strip()]


def has_pyjnius(value):
    return any(re.split(r'[<>=!~@]', name, 1)[0].strip() == 'pyjnius' for name in items(value))


def project_root(spec, config):
    return (Path(spec).resolve().parent/config['app'].get('source.dir', '.')).resolve()


def check_sources(root):
    source = root/JAVA
    text = source.read_text(encoding='utf8')
    if not re.search(r'package\s+org\.simomatch\.capture\s*;', text):
        raise ValueError('Java package mismatch')
    if not re.search(r'public\s+final\s+class\s+CaptureService\b', text):
        raise ValueError('CaptureService declaration mismatch')
    if f"autoclass('{CLASS}')" not in (root/'services/video_recording.py').read_text(encoding='utf8'):
        raise ValueError('Python autoclass mismatch')
    xml = validate_aar(root/MANIFEST_AAR)
    if xml != (root/'android_src/capture_manifest.xml').read_bytes():
        raise ValueError('AAR manifest is stale; run python tools/build_capture_manifest.py')
    service = ElementTree.fromstring(xml).find('application/service')
    ns = '{http://schemas.android.com/apk/res/android}'
    if service is None or service.get(ns+'name') != CLASS or service.get(ns+'exported') != 'false' or service.get(ns+'foregroundServiceType') != 'mediaProjection':
        raise ValueError('Invalid capture service manifest')


def check_spec(spec):
    config = read_spec(spec)
    root, app = project_root(spec, config), config['app']
    check_sources(root)
    errors = []
    if app.get('android.api') != '36': errors.append('android.api must be 36')
    if 'arm64-v8a' not in items(app.get('android.archs','')): errors.append('android.archs missing arm64-v8a')
    if not has_pyjnius(app.get('requirements','')): errors.append('requirements missing pyjnius')
    declared = {p.removeprefix('android.permission.') for p in items(app.get('android.permissions',''))}
    for permission in PERMISSIONS:
        if permission not in declared: errors.append('android.permissions missing '+permission)
    # Buildozer resolves add_src relative to the spec directory, not source.dir.
    base = Path(spec).resolve().parent
    source = (root/JAVA).resolve()
    paths = [(base/p.replace('%(source.dir)s', app.get('source.dir','.'))).resolve()
             for p in items(app.get('android.add_src',''))]
    for path in paths:
        if not path.is_dir(): errors.append('Java source directory does not exist in this environment: '+str(path))
    if not any(source.is_relative_to(p) and p.is_dir() for p in paths):
        errors.append('android.add_src does not include the Java source directory')
    aars = [(base/p.replace('%(source.dir)s', app.get('source.dir','.'))).resolve()
            for p in items(app.get('android.add_aars',''))]
    if (root/MANIFEST_AAR).resolve() not in aars:
        errors.append('android.add_aars missing capture_manifest.aar')
    if not has_libs_repository(app.get('android.add_gradle_repositories','')):
        errors.append("android.add_gradle_repositories missing flatDir { dirs 'libs' }; named AAR cannot resolve")
    return errors


def apply_spec(spec, *, repository_only=False):
    """Patch only required app keys; retain WSL NDK/SDK paths, comments, versions."""
    spec = Path(spec)
    config = read_spec(spec)
    root, app = project_root(spec, config), config['app']
    check_sources(root)  # Wrong/incomplete rsync target: do not change its spec.
    relative = Path(os.path.relpath(root, spec.resolve().parent))
    def merged(key, additions):
        return ', '.join(dict.fromkeys(items(app.get(key,''))+list(additions)))
    def merged_paths(key, addition):
        values = items(app.get(key,''))
        target = (spec.resolve().parent/addition).resolve()
        if not any((spec.resolve().parent/value.replace('%(source.dir)s', app.get('source.dir','.'))).resolve() == target
                   for value in values):
            values.append(addition)
        return ', '.join(values)
    existing_permissions = {p.removeprefix('android.permission.') for p in items(app.get('android.permissions',''))}
    required = {
        'android.api':'36',
        'android.archs':merged('android.archs', ['arm64-v8a']),
        'requirements':merged('requirements', [] if has_pyjnius(app.get('requirements','')) else ['pyjnius']),
        'android.permissions':merged('android.permissions', [p for p in PERMISSIONS if p not in existing_permissions]),
        'android.add_src':merged_paths('android.add_src', (relative/'android_src').as_posix()),
        'android.add_aars':merged_paths('android.add_aars', (relative/MANIFEST_AAR).as_posix()),
    }
    if not app.get('android.add_compile_options'):
        required['android.add_compile_options'] = '"sourceCompatibility = 1.8", "targetCompatibility = 1.8"'
    repositories = app.get('android.add_gradle_repositories','').strip()
    if not has_libs_repository(repositories):
        repositories += (', ' if repositories else '')+LIBS_REPOSITORY
    required['android.add_gradle_repositories'] = repositories
    if repository_only:
        # Repair this Gradle issue without changing API/NDK/branch/dependencies.
        required = {'android.add_gradle_repositories':repositories}
    old = spec.read_text(encoding='utf-8-sig')
    result, in_app, pending = [], False, dict(required)
    for line in old.splitlines(keepends=True):
        if line.strip().startswith('['):
            if in_app:
                result.extend(f'{key} = {value}\n' for key,value in pending.items())
                pending.clear()
            in_app = line.strip() == '[app]'
        match = re.match(r'\s*([^#;\s][^=]*?)\s*=', line) if in_app else None
        key = match.group(1).strip() if match else ''
        if key in required:
            line = f'{key} = {required[key]}\n'
            pending.pop(key, None)
        result.append(line)
    if in_app:
        if result and not result[-1].endswith('\n'): result[-1] += '\n'
        result.extend(f'{key} = {value}\n' for key,value in pending.items())
    new = ''.join(result)
    if new == old:
        return None
    backup = spec.with_name(spec.name+'.capture-backup-'+uuid4().hex[:8])
    shutil.copyfile(spec, backup)
    temporary = spec.with_name('.capture-spec-'+uuid4().hex+'.tmp')
    try:
        temporary.write_text(new, encoding='utf8')
        temporary.replace(spec)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def check_gradle_project(directory, source_root):
    """Read-only check of an actual p4a dist, not an edit of generated files."""
    directory, source_root = Path(directory), Path(source_root)
    copied = directory/'libs/capture_manifest.aar'
    if not copied.is_file():
        raise ValueError('AAR was not copied to generated Gradle libs/: '+str(copied))
    validate_aar(copied)
    if copied.read_bytes() != (source_root/MANIFEST_AAR).read_bytes():
        raise ValueError('Generated Gradle AAR differs from current source')
    text = (directory/'build.gradle').read_text(encoding='utf8')
    if not re.search(r'''implementation\s*\(\s*name\s*:\s*['"]capture_manifest['"]\s*,\s*ext\s*:\s*['"]aar['"]\s*\)''', text):
        raise ValueError('Generated Gradle missing named capture_manifest AAR dependency')
    # Ignore comments but retain quoted URLs and nested Maven repository blocks.
    text = re.sub(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|/\*[\s\S]*?\*/|//[^\n]*''',
                  lambda match: match.group(1) or '', text)
    found = False
    for block in re.finditer(r'\brepositories\s*\{', text):
        start, depth, quote, escaped = block.end(), 1, '', False
        for i in range(start, len(text)):
            char = text[i]
            if quote:
                if escaped: escaped = False
                elif char == '\\': escaped = True
                elif char == quote: quote = ''
            elif char in "'\"": quote = char
            elif char == '{': depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    body = text[start:i]
                    if re.search(r'(?m)^\s*'+LIBS_REPOSITORY_PATTERN, body): found = True
                    break
    if not found:
        raise ValueError('Generated Gradle missing libs/ flatDir repository; rerun Buildozer with the fixed spec')


def dex_defines(data, target=DESCRIPTOR):
    """Inspect class_defs -> type_ids -> string_ids (DEX 035..040)."""
    if len(data) < 112 or data[:4] != b'dex\n' or data[7] != 0:
        raise ValueError('Invalid DEX header')
    if data[4:7] not in (b'035',b'036',b'037',b'038',b'039',b'040'):
        raise ValueError('Unsupported DEX version; use Android SDK apkanalyzer')
    def uint(offset):
        if offset < 0 or offset+4 > len(data): raise ValueError('Truncated DEX')
        return struct.unpack_from('<I', data, offset)[0]
    if uint(40) != 0x12345678: raise ValueError('Unsupported DEX endian tag')
    sc, so, tc, to, cc, co = uint(56), uint(60), uint(64), uint(68), uint(96), uint(100)
    if so+sc*4 > len(data) or to+tc*4 > len(data) or co+cc*32 > len(data):
        raise ValueError('DEX tables exceed file')
    for i in range(cc):
        type_index = uint(co+i*32)
        if type_index >= tc: raise ValueError('Invalid DEX class type')
        string_index = uint(to+type_index*4)
        if string_index >= sc: raise ValueError('Invalid DEX descriptor index')
        pos = uint(so+string_index*4)
        for _ in range(5):
            if pos >= len(data): raise ValueError('Invalid DEX string')
            byte = data[pos]; pos += 1
            if byte < 128: break
        else: raise ValueError('Invalid DEX string length')
        end = data.find(b'\0', pos)
        if end < 0: raise ValueError('Unterminated DEX string')
        if data[pos:end] == target: return True
    return False


def check_apk(path):
    with ZipFile(path) as archive:
        for info in archive.infolist():
            if re.fullmatch(r'classes\d*\.dex', info.filename):
                if info.file_size > 128*1024*1024: raise ValueError('DEX too large; use apkanalyzer')
                if dex_defines(archive.read(info)):
                    return info.filename
    raise ValueError('CaptureService class definition is NOT in APK DEX; do not test recording yet')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=Path(__file__).resolve().parents[1]/'buildozer.spec')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--fix-aar-repository', action='store_true', help='Patch only the local AAR repository key')
    parser.add_argument('--gradle-project', type=Path, help='Read-only check of generated p4a Gradle project')
    parser.add_argument('--apk', type=Path)
    args = parser.parse_args()
    try:
        if args.apply or args.fix_aar_repository:
            backup = apply_spec(args.spec, repository_only=args.fix_aar_repository and not args.apply)
            print('SPEC_UPDATED backup='+str(backup) if backup else 'SPEC_ALREADY_CURRENT')
        errors = check_spec(args.spec)
        if errors: raise ValueError('; '.join(errors))
        print('CAPTURE_SOURCE_AND_SPEC_OK '+str(args.spec.resolve()))
        if args.gradle_project:
            check_gradle_project(args.gradle_project, project_root(args.spec, read_spec(args.spec)))
            print('GENERATED_GRADLE_CAPTURE_INPUTS_OK (not an APK build verification)')
        if args.apk:
            print('CAPTURE_CLASS_DEFINED_IN_DEX '+check_apk(args.apk))
        else:
            print('APK_NOT_CHECKED: source/spec success does NOT prove APK packaging or device class loading')
        return 0
    except (OSError, ValueError, BadZipFile, configparser.Error, ElementTree.ParseError) as exc:
        print('CAPTURE_CHECK_FAILED: '+str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
