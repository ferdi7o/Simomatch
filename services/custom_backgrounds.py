"""Owned, UUID-addressed image library. Never deletes an imported source."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
import hashlib
import imghdr
import json
import shutil
from services.media import load_texture


class CustomBackgroundStore:
    def __init__(self, data_dir, loader=load_texture):
        self.root = Path(data_dir).resolve() if data_dir else None
        self.directory = self.root/'custom_backgrounds' if self.root else None
        self.path = self.root/'custom_backgrounds.json' if self.root else None
        self.loader, self.rows, self.warning = loader, [], ''
        self.corrupt = False
        self.legacy_imports = set()
        if not self.root:
            return
        try:
            if self.directory.resolve().parent != self.root:
                raise ValueError('Arka plan dizini uygulama dışında olamaz.')
            self.directory.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self._save([])
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('backgrounds'), list):
                raise ValueError('Geçersiz arka plan kaydı.')
            self.legacy_imports = {key for key in data.get('legacy_imports', []) if isinstance(key, str)}
            seen = set()
            for row in data['backgrounds']:
                if (isinstance(row, dict) and isinstance(row.get('id'), str)
                        and row['id'] not in seen and self.owned_path(row)
                        and isinstance(row.get('name'), str) and isinstance(row.get('added_at'), str)):
                    self.rows.append(row)
                    seen.add(row['id'])
        except (OSError, ValueError, TypeError):
            self.corrupt = True
            self.warning = 'Arka plan kaydı okunamadı; mevcut görseller korunuyor.'
            # Recover UUID-owned files without overwriting the broken index.
            if self.directory and self.directory.resolve().parent == self.root:
                for source in sorted(self.directory.glob('*')):
                    try:
                        key = UUID(source.stem).hex
                    except ValueError:
                        continue
                    row = dict(id=key, name=f'Arka plan {key[:8]}',
                               path=f'custom_backgrounds/{source.name}',
                               added_at=datetime.now(timezone.utc).isoformat())
                    if self.owned_path(row):
                        self.rows.append(row)

    def owned_path(self, row):
        """Validate the resolved absolute target before any file mutation."""
        if not self.root or not isinstance(row, dict):
            return None
        try:
            key, relative = row['id'], row['path']
            if UUID(key).hex != key or not isinstance(relative, str):
                return None
            if Path(relative).is_absolute() or len(Path(relative).parts) != 2 or Path(relative).parts[0] != 'custom_backgrounds':
                return None
            path = (self.root/relative).resolve()
            if (path.parent != self.directory or path.suffix.lower() not in ('.png', '.jpg', '.jpeg')
                    or path.stem != key or self.directory.resolve().parent != self.root):
                return None
            return path
        except (KeyError, ValueError, TypeError, OSError, AttributeError):
            return None

    def _save(self, rows):
        temporary = self.root/f'.custom_backgrounds_{uuid4().hex}.tmp'
        try:
            if self.corrupt and self.path.exists():
                shutil.copyfile(self.path, self.root/f'custom_backgrounds.corrupt_{uuid4().hex}.json')
            imported = self.legacy_imports | {row['legacy_key'] for row in rows if row.get('legacy_key')}
            temporary.write_text(json.dumps(dict(version=1, backgrounds=rows, legacy_imports=sorted(imported)), ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.corrupt = False
            self.legacy_imports = imported
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, key):
        return next((row for row in self.rows if row['id'] == key), None)

    def add(self, source, name=None, legacy_key=None):
        if not self.root:
            raise ValueError('Kalıcı uygulama veri dizini bulunamadı.')
        if str(source).lower().startswith('content://'):
            raise ValueError('Android görselini uygulamanın dosya seçicisiyle seçin.')
        source = Path(source)
        try:
            valid = (source.suffix.lower() in ('.png', '.jpg', '.jpeg') and
                     source.stat().st_size <= 32*1024*1024 and imghdr.what(source) in ('png', 'jpeg'))
        except (OSError, ValueError):
            valid = False
        if not valid or self.loader(source) is None:
            raise ValueError('Görsel okunamadı. Geçerli bir PNG veya JPG/JPEG seçin.')
        title = name or source.stem
        if not name:
            try:
                UUID(title)  # Android staging uses UUID names, not display names.
                title = f'Arka plan {len(self.rows)+1}'
            except ValueError:
                pass
        key = uuid4().hex
        row = dict(id=key, name=title[:100],
                   path=f'custom_backgrounds/{key}{source.suffix.lower()}',
                   added_at=datetime.now(timezone.utc).isoformat())
        if legacy_key:
            row['legacy_key'] = legacy_key
        destination = self.owned_path(row)
        if not destination:
            raise ValueError('Güvenli arka plan dizini bulunamadı.')
        try:
            shutil.copyfile(source, destination)
            self._save(self.rows+[row])
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        self.rows.append(row)
        return row

    def delete(self, key):
        row = self.get(key)
        path = self.owned_path(row)
        if not path:
            raise ValueError('Yalnızca kayıtlı özel arka planlar silinebilir.')
        remaining = [item for item in self.rows if item['id'] != key]
        self._save(remaining)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            self._save(self.rows)
            raise
        self.rows = remaining
        thumb = self.thumbnail_path(row)
        try:
            thumb.unlink(missing_ok=True)
        except OSError:
            pass

    def thumbnail_path(self, row):
        path = self.owned_path(row)
        return path.with_name(f'{row["id"]}.thumb.png') if path else None

    def thumbnail(self, row, textures):
        path, thumb = self.owned_path(row), self.thumbnail_path(row)
        if not path or not path.is_file():
            return None
        if thumb.is_file():
            return textures.thumbnail(thumb)
        texture = textures.thumbnail(path)
        if texture:
            try:
                # Small persistent PNG: subsequent app sessions avoid decoding
                # the original large image just to populate the gallery.
                if thumb.resolve().parent == self.directory:
                    texture.save(str(thumb))
            except Exception:
                pass  # A thumbnail failure must not lose an owned image.
        return texture

    @staticmethod
    def legacy_key(path):
        return hashlib.sha256(str(Path(path).resolve()).encode('utf-8')).hexdigest()

    def migrate(self, directory):
        """Copy former owned imports once. Original files remain untouched."""
        result = {}
        if not self.root or not directory:
            return result
        directory = Path(directory).resolve()
        if directory == self.directory or not directory.is_dir():
            return result
        for path in sorted(directory.iterdir()):
            if path.resolve().parent != directory or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                continue
            key = self.legacy_key(path)
            row = next((item for item in self.rows if item.get('legacy_key') == key), None)
            if not row and key in self.legacy_imports:
                continue  # A deliberately deleted legacy image stays deleted.
            if not row:
                try:
                    row = self.add(path, legacy_key=key)
                except (ValueError, OSError):
                    self.warning = 'Bazı eski arka planlar aktarılamadı; kaynakları korundu.'
                    continue
            result[str(path)] = row
        return result
