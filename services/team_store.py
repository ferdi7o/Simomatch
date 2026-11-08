"""Atomic JSON storage and owned media copies. Independent of the UI."""
from services.image_format import image_format
import json
import shutil
import unicodedata
from pathlib import Path
from uuid import uuid4
from math import isfinite


def music_start(value):
    if isinstance(value, bool):
        raise ValueError('Müzik başlangıcı geçerli bir saniye değeri olmalıdır.')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('Müzik başlangıcı geçerli bir saniye değeri olmalıdır.') from None
    if not isfinite(value) or value < 0:
        raise ValueError('Müzik başlangıcı negatif veya sonsuz olamaz.')
    return value


def normalized_name(name):
    return ' '.join(unicodedata.normalize('NFKC', name).split())


class TeamStore:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets = self.root / 'assets'
        self.assets.mkdir(exist_ok=True)
        self.path = self.root / 'teams.json'
        self.warning = ''
        self.teams = self._load()

    def _load(self):
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('teams'), list):
                raise ValueError('Geçersiz kayıt biçimi')
            result, ids, names = [], set(), set()
            for row in data['teams']:
                if not isinstance(row, dict):
                    raise ValueError('Geçersiz takım')
                name, key = normalized_name(row['name']), row['id']
                if not name or len(name) > 40 or not isinstance(key, str) or not key or key in ids or name.casefold() in names:
                    raise ValueError('Geçersiz veya yinelenen takım')
                for field in ('logo', 'music'):
                    if not isinstance(row.get(field, ''), str):
                        raise ValueError('Geçersiz dosya yolu')
                try:
                    start = music_start(row.get('goal_music_start_seconds', 0.))
                except ValueError:
                    start = 0.
                result.append(dict(id=key, name=name, logo=row.get('logo', ''), music=row.get('music', ''),
                                   goal_music_start_seconds=start))
                ids.add(key)
                names.add(name.casefold())
            return result
        except (OSError, ValueError, TypeError, KeyError):
            self.warning = 'Takım kaydı okunamadı. Yeni kayıt öncesinde mevcut JSON yedeklenecek.'
            return []

    def asset_path(self, relative):
        """Do not follow JSON paths outside the app-owned assets directory."""
        if not relative:
            return None
        try:
            path = (self.root / relative).resolve()
            if path.is_relative_to(self.assets) and path.is_file():
                return path
        except (OSError, ValueError):
            pass
        return None

    def get(self, team_id):
        return next((dict(t) for t in self.teams if t['id'] == team_id), None)

    def _copy(self, source, kind):
        path = Path(source)
        extensions = {'.png', '.jpg', '.jpeg'} if kind == 'logo' else {'.mp3'}
        if not path.is_file() or path.suffix.lower() not in extensions:
            raise ValueError('Logo PNG/JPG, gol müziği MP3 dosyası olmalıdır.')
        if not 0 < path.stat().st_size <= 32 * 1024 * 1024:
            raise ValueError('Dosya boş veya 32 MB sınırından büyük.')
        if kind == 'logo' and image_format(path) not in ('png', 'jpeg'):
            raise ValueError('Görsel dosyası bozuk veya desteklenmiyor.')
        if kind == 'music':
            with path.open('rb') as stream:
                header = stream.read(3)
            if not (header.startswith(b'ID3') or (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224)):
                raise ValueError('MP3 dosyası tanınamadı.')
        destination = self.assets / (uuid4().hex + path.suffix.lower())
        shutil.copyfile(path, destination)
        return destination.relative_to(self.root).as_posix()

    def _commit(self, teams):
        if self.warning and self.path.exists():
            shutil.copyfile(self.path, self.root / f'teams.backup.{uuid4().hex}.json')
        temporary = self.root / 'teams.tmp'
        try:
            temporary.write_text(json.dumps({'version': 1, 'teams': teams}, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.teams = teams
        self.warning = ''

    def save(self, name, logo=None, music=None, team_id=None, goal_music_start_seconds=None):
        """None preserves media on edit; an empty string explicitly removes it."""
        name = normalized_name(name)
        if not name or len(name) > 40:
            raise ValueError('Takım adı 1–40 karakter olmalıdır.')
        if any(t['id'] != team_id and t['name'].casefold() == name.casefold() for t in self.teams):
            raise ValueError('Bu isimde bir takım zaten var.')
        old = self.get(team_id) if team_id else None
        if team_id and not old:
            raise ValueError('Düzenlenecek takım bulunamadı.')
        row = dict(old or dict(id=uuid4().hex, logo='', music=''), name=name)
        row['goal_music_start_seconds'] = music_start(goal_music_start_seconds if goal_music_start_seconds is not None
                                                     else row.get('goal_music_start_seconds', 0.))
        created = []
        try:
            for kind, source in [('logo', logo), ('music', music)]:
                if source is not None:
                    row[kind] = self._copy(source, kind) if source else ''
                    if row[kind]:
                        created.append(self.root / row[kind])
            if not row['music']:
                row['goal_music_start_seconds'] = 0.
            self._commit([row if t['id'] == row['id'] else t for t in self.teams] if old else self.teams + [row])
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return dict(row)

    def delete(self, team_id):
        if not self.get(team_id):
            raise ValueError('Takım bulunamadı.')
        # Keep owned media so a failed operation or old backup cannot lose files.
        self._commit([t for t in self.teams if t['id'] != team_id])
