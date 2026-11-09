"""Orchestration regression tests with a simulated builder, not real APK builds."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile
import pytest
from tools.verify_two_android_builds import verify
from tools.check_android_capture import apply_spec
from test_android_capture_packaging import project, sample_dex


def builder(root, fail_second_repository=False, missing_class=False, regenerate=True, fail_command=False):
    calls = []
    gradle = root/'dist'
    (gradle/'libs').mkdir(parents=True)
    shutil.copyfile(root/'android_src/capture_manifest.aar',gradle/'libs/capture_manifest.aar')
    apk = root/'bin/app.apk'
    def run(command, cwd, check):
        calls.append(command)
        assert Path(cwd) == root and check
        assert command == ['buildozer','-v','android','debug']
        if fail_command: raise subprocess.CalledProcessError(1,command)
        repository = '' if fail_second_repository and len(calls)==2 else "flatDir { dirs 'libs' }"
        path = gradle/'build.gradle'
        if regenerate or not path.exists():
            previous = path.stat().st_mtime_ns if path.exists() else 1_700_000_000_000_000_000
            path.write_text("allprojects {\n repositories {\n "+repository+"\n }\n}\n"
                            "dependencies { implementation(name: 'capture_manifest', ext: 'aar') }",encoding='utf8')
            os.utime(path,ns=(previous+1_000_000_000,previous+1_000_000_000))
        apk.parent.mkdir(exist_ok=True)
        with ZipFile(apk,'w') as archive:
            archive.writestr('classes.dex',sample_dex(not missing_class))
        output = gradle/'build/outputs/apk/debug/simomatch-debug.apk'
        output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(apk,output)
    return run, calls, gradle, apk


def test_both_regenerations_and_dex_are_checked_without_spec_or_cache_mutation(project):
    root,spec = project
    apply_spec(spec)
    original = spec.read_bytes()
    run,calls,gradle,apk = builder(root)
    report = root/'result.json'
    result = verify(spec,gradle,apk,report,run=run)
    assert result['complete'] and len(calls)==2 and len(result['passes'])==2
    assert all(p['gradle_regenerated'] and p['capture_class_dex']=='classes.dex' for p in result['passes'])
    assert json.loads(report.read_text())['complete']
    assert spec.read_bytes()==original


@pytest.mark.parametrize('options,reason,passes',[
    ({'fail_second_repository':True},'flatDir',1),
    ({'missing_class':True},'NOT in APK DEX',0),
    ({'regenerate':False},'not regenerated',1),
    ({'fail_command':True},'returned non-zero',0),
])
def test_never_reports_two_successes_when_either_build_or_artifact_fails(project,options,reason,passes):
    root,spec=project
    apply_spec(spec)
    run,calls,gradle,apk=builder(root,**options)
    report=root/'result.json'
    with pytest.raises(Exception,match=reason): verify(spec,gradle,apk,report,run=run)
    result=json.loads(report.read_text())
    assert not result['complete'] and len(result['passes'])==passes


def test_missing_persistent_setting_fails_before_any_build(project):
    root,spec=project
    run,calls,gradle,apk=builder(root)
    with pytest.raises(ValueError,match='flatDir'):
        verify(spec,gradle,apk,root/'result.json',run=run)
    assert calls==[]


def test_an_old_other_apk_with_capture_class_cannot_pass_as_current_output(project):
    root,spec=project
    apply_spec(spec)
    run,calls,gradle,apk=builder(root)
    def substitute(*args,**kwargs):
        run(*args,**kwargs)
        with ZipFile(apk,'w') as archive:
            archive.writestr('classes2.dex',sample_dex())
    report=root/'result.json'
    with pytest.raises(ValueError,match='does not match'):
        verify(spec,gradle,apk,report,run=substitute)
    assert not json.loads(report.read_text())['complete']
