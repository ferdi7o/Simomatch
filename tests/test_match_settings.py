import math
import pytest
from services.match_settings import MatchSettings
from engine.match_engine import MatchEngine


@pytest.mark.parametrize('duration', [0, 9, 601, math.nan, math.inf])
def test_invalid_match_settings(duration):
    with pytest.raises(ValueError):
        MatchSettings({'id': '1', 'name': 'A'}, {'id': '2', 'name': 'B'}, duration=duration)


def test_settings_transfer_to_engine():
    settings = MatchSettings({'id': '1', 'name': 'Mor'}, {'id': '2', 'name': 'Mavi'}, (22, 45), 75)
    engine = MatchEngine(teams=(settings.home['name'], settings.away['name']),
                         radii=settings.radii, duration=settings.duration)
    assert [(d.team, d.radius) for d in engine.disks] == [('Mor', 22), ('Mavi', 45)]
    assert engine.scores == {'Mor': 0, 'Mavi': 0} and engine.duration == 75


def test_cannot_play_same_team():
    team = {'id': '1', 'name': 'A'}
    with pytest.raises(ValueError):
        MatchSettings(team, team)
