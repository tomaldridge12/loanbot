import pytest

from football import Match, Player, PlayerManager

@pytest.fixture
def example_ids(tmp_path):
    content = """{
    "Andrey Santos" : {
        "id" : 1372921,
        "team_id" : 9848,
        "team_name" : "Strasbourg" 
    }
    }"""
    file_name = tmp_path / "ids.json"
    with open(file_name, 'w') as f:
        f.write(content)

    return file_name

@pytest.fixture
def pm(example_ids) -> PlayerManager:
    """Fixture to create a PlayerManager object."""
    return PlayerManager(example_ids, debug_mode=True)

@pytest.fixture
def example_match(pm) -> Match:
    resp = pm.fotmob.get_match_details(4513876)
    with open('test.json', 'w') as f:
        f.write(str(resp))
    return Match.from_json(resp)

@pytest.fixture
def example_player(pm, example_match) -> Player:
    player = pm.players[0]
    player.next_match = example_match
    return player

def test_update_info(pm, example_player, example_match):
    pm.update_player_info(example_player, example_match)
    assert example_player.starting == True

def test_match_report(pm, example_player):
    resp = pm.get_end_of_match_report(example_player)
    assert resp == "7.78, including 87% passing percentage, 3 chances created, 1 shots and 1 goals."

def test_match_from_json(pm, example_player):
    json_dict = pm.fotmob.get_match_details(4513876)
    general = json_dict.get("general", {})
    content = json_dict.get("content", {})
    _id = general.get("matchId")
    assert _id == str(4513876)

    league_name = general.get("leagueName")
    assert league_name == "Ligue 1"

    started = general.get("started")
    assert started == True
    finished = general.get("finished")
    assert finished == True

    header = json_dict.get("header", {})
    lineup = content.get('lineup') or content.get('lineup2') or None
    stats = content.get("playerStats")
    
    for _lineup in lineup.values():
        if isinstance(_lineup, dict) and 'id' in _lineup:
            if _lineup['id'] == example_player.team_id:
                assert _lineup.get('starters') is not None
                assert _lineup.get('subs') is not None