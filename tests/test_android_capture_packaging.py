"""Spec migration and DEX class-def checks; no claim of an Android SDK build."""
import shutil
import struct
from pathlib import Path
from zipfile import ZipFile
import pytest
from tools.check_android_capture import (JAVA, CLASS, DESCRIPTOR, check_sources, check_spec,
                                         apply_spec, check_apk, dex_defines, validate_aar,
                                         has_libs_repository, check_gradle_project, read_spec)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    shutil.copytree(ROOT/'android_src', tmp_path/'android_src')
    (tmp_path/'services').mkdir()
    shutil.copyfile(ROOT/'services/video_recording.py', tmp_path/'services/video_recording.py')
    spec = tmp_path/'buildozer.spec'
    spec.write_text('''[app]
# Keep WSL-only settings and comments.
source.dir = .
version = 0.1.77
requirements = python3,kivy==2.3.1,ffpyplayer
android.permissions = INTERNET
android.ndk = 28c
android.sdk_path = /home/test/android-sdk

[buildozer]
log_level = 2
''', encoding='utf8')
    return tmp_path, spec


def test_actual_project_source_package_autoclass_and_manifest_are_consistent():
    check_sources(ROOT)
    assert check_spec(ROOT/'buildozer.spec') == []


def test_old_wsl_spec_gets_required_java_settings_without_losing_custom_settings(project):
    root, spec = project
    assert any('add_src' in error for error in check_spec(spec))
    original = spec.read_bytes()
    backup = apply_spec(spec)
    assert backup.read_bytes() == original
    text = spec.read_text(encoding='utf8')
    for preserved in ('# Keep WSL-only settings', 'version = 0.1.77', 'android.ndk = 28c',
                      'android.sdk_path = /home/test/android-sdk', 'ffpyplayer', 'INTERNET'):
        assert preserved in text
    assert check_spec(spec) == []
    assert apply_spec(spec) is None  # Idempotent: no repeated source paths.


def test_missing_java_or_wrong_package_fails_before_changing_wsl_spec(project):
    root, spec = project
    original = spec.read_bytes()
    java = root/JAVA
    text = java.read_text(encoding='utf8')
    java.write_text(text.replace('package org.simomatch.capture;', 'package wrong.capture;'), encoding='utf8')
    with pytest.raises(ValueError, match='package mismatch'): apply_spec(spec)
    assert spec.read_bytes() == original
    java.unlink()
    with pytest.raises(FileNotFoundError): apply_spec(spec)
    assert spec.read_bytes() == original


def test_patch_preserves_versioned_jnius_and_normalizes_existing_source_paths(project):
    root, spec = project
    text = spec.read_text(encoding='utf8').replace('ffpyplayer','ffpyplayer,pyjnius==1.7.0')
    text = text.replace('android.permissions = INTERNET', 'android.permissions = INTERNET,android.permission.FOREGROUND_SERVICE')
    text = text.replace('[buildozer]', 'android.add_src = %(source.dir)s/android_src\n[buildozer]')
    spec.write_text(text,encoding='utf8')
    apply_spec(spec)
    result = spec.read_text(encoding='utf8')
    assert 'pyjnius==1.7.0' in result and 'pyjnius==1.7.0, pyjnius' not in result
    assert 'android.add_src = %(source.dir)s/android_src' in result
    assert check_spec(spec) == []


def test_repository_only_repair_preserves_every_other_wsl_build_setting(project):
    root, spec = project
    text = spec.read_text(encoding='utf8').replace('[buildozer]',
             "p4a.branch = develop\nandroid.api = 36\nandroid.add_gradle_repositories = maven { url 'https://example.org/repo' }\n[buildozer]")
    spec.write_text(text, encoding='utf8')
    before = dict(read_spec(spec)['app'])
    backup = apply_spec(spec, repository_only=True)
    after = dict(read_spec(spec)['app'])
    assert backup.read_text(encoding='utf8') == text
    assert has_libs_repository(after.pop('android.add_gradle_repositories'))
    before.pop('android.add_gradle_repositories')
    assert after == before  # Branch/API/NDK/Python requirements stay identical.
    assert "maven { url 'https://example.org/repo' }" in spec.read_text(encoding='utf8')
    assert apply_spec(spec, repository_only=True) is None


def test_manifest_aar_is_valid_but_does_not_contain_capture_java_bytecode():
    xml = validate_aar(ROOT/'android_src/capture_manifest.aar')
    assert CLASS.encode() in xml
    from io import BytesIO
    with ZipFile(ROOT/'android_src/capture_manifest.aar') as archive:
        with ZipFile(BytesIO(archive.read('classes.jar'))) as jar:
            assert not jar.namelist()  # add_src, not this manifest archive, supplies the class.


@pytest.mark.parametrize('value', ["flatDir { dirs 'libs' }", 'flatDir { dirs("libs") }'])
def test_unquoted_buildozer_repository_expression_is_recognized(value):
    assert has_libs_repository(value)
    assert not has_libs_repository('"'+value+'"')


def test_generated_p4a_named_dependency_needs_root_libs_repository(tmp_path):
    project = tmp_path/'dist'
    (project/'libs').mkdir(parents=True)
    shutil.copyfile(ROOT/'android_src/capture_manifest.aar', project/'libs/capture_manifest.aar')
    gradle = project/'build.gradle'
    # Matches the relevant p4a develop template: AAR copied, no flatDir default.
    text = '''allprojects {
    repositories {
        google()
        mavenCentral()
        maven {
            url 'https://example.org/repo'
        }
    }
}
dependencies { implementation(name: 'capture_manifest', ext: 'aar') }
'''
    gradle.write_text(text,encoding='utf8')
    with pytest.raises(ValueError,match='flatDir'): check_gradle_project(project, ROOT)
    gradle.write_text(text.replace('google()', "google()\n        flatDir { dirs 'libs' }"),encoding='utf8')
    check_gradle_project(project, ROOT)
    (project/'libs/capture_manifest.aar').unlink()
    with pytest.raises(ValueError,match='not copied'): check_gradle_project(project, ROOT)


def sample_dex(defined=True, descriptor=DESCRIPTOR):
    # Minimal table fixture, not an executable Android program. A referenced
    # descriptor alone must never count as a packaged class definition.
    data = bytearray(156+1+len(descriptor)+1)
    data[:8] = b'dex\n035\0'
    struct.pack_into('<I',data,32,len(data))
    struct.pack_into('<I',data,36,112)
    struct.pack_into('<I',data,40,0x12345678)
    struct.pack_into('<IIII',data,56,1,112,1,116)
    struct.pack_into('<II',data,96,1 if defined else 0,120)
    struct.pack_into('<I',data,112,156)
    struct.pack_into('<I',data,116,0)
    struct.pack_into('<I',data,120,0)
    data[156] = len(descriptor)
    data[157:157+len(descriptor)] = descriptor
    return bytes(data)


def test_dex_type_reference_is_not_a_class_definition():
    assert not dex_defines(sample_dex(defined=False))
    assert dex_defines(sample_dex())
    assert not dex_defines(sample_dex(descriptor=b'Lother/Class;'))


def test_apk_multidex_and_absent_capture_class(tmp_path):
    apk = tmp_path/'app.apk'
    with ZipFile(apk,'w') as archive:
        archive.writestr('classes.dex', sample_dex(False))
        archive.writestr('classes2.dex', sample_dex())
    assert check_apk(apk) == 'classes2.dex'
    with ZipFile(apk,'w') as archive:
        archive.writestr('classes.dex', sample_dex(False))
    with pytest.raises(ValueError, match='NOT in APK DEX'): check_apk(apk)


@pytest.mark.parametrize('data', [b'bad', sample_dex()[:130], b'dex\n041\0'+sample_dex()[8:]])
def test_malformed_or_unsupported_dex_does_not_report_packaging_success(data):
    with pytest.raises(ValueError): dex_defines(data)
