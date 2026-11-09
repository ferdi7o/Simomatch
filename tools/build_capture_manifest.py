"""Reproduce the tiny manifest-only AAR (no SDK, compiler or third-party packages).

Gradle's standard manifest merger adds the service on old and new p4a versions.
Do not use extra_manifest_application_arguments: it is attributes-only in p4a.
Run from any directory with: python tools/build_capture_manifest.py
"""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED


def build(root):
    root = Path(root)
    jar = BytesIO()
    with ZipFile(jar, 'w'):
        pass
    output = root/'android_src/capture_manifest.aar'
    files = {'AndroidManifest.xml': (root/'android_src/capture_manifest.xml').read_bytes(),
             'classes.jar': jar.getvalue(), 'R.txt': b''}
    with ZipFile(output, 'w') as archive:
        for name, content in files.items():
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            archive.writestr(info, content)
    return output


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parents[1]))
