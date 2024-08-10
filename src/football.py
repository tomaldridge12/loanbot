import logging
from datetime import datetime, timedelta, timezone
from json import load
from queue import Queue
from random import randint
from typing import Optional, Tuple, Union

from mobfot.client import MobFot

from image import generate_image
from utils import GameEvent, ThreadSafeQueue, TweepyClient

class Match:
    def __init__(self,
                 id: int,
                 league_name: str,
                 general: dict,
                 lineup: dict,
                 header: dict,
                 started: bool = False,
                 finished: bool = False
                 ):
        """
        Initialize a Match object.

        :param id: Unique identifier for the match
        :param league_name: Name of the league
        :param lineup: Dictionary containing lineup information
        :param started: Boolean indicating if the match has started
        :param finished: Boolean indicating if the match has finished
        """
        self.id = id
        self.league_name = league_name
        self.general = general
        self.lineup = lineup
        self.header = header
        self.started = started
        self.finished = finished
        self.tweeted = self.setup_tweet_dict()

    def setup_tweet_dict(self):
        return {enum.name : False for enum in GameEvent if enum.value > 4}
    
    @classmethod
    def from_json(cls, json_dict: dict):
        """
        Create a Match object from a JSON dictionary.

        :param json_dict: Dictionary containing match data
        :return: Match object if successful, None otherwise
        """
        try:
            general = json_dict.get("general", {})
            content = json_dict.get("content", {})
            if not (general or content):
                return None
            
            return cls(
                id=general.get("matchId"),
                league_name=general.get("leagueName"),
                general=general,
                header=json_dict.get("header", {}),
                lineup=content.get("lineup"),
                started=general.get("started"),
                finished=general.get("finished")
            )
        except Exception as e:
            print(f"Error parsing JSON: {str(e)}")
            return None

    def is_soon(self):
        match_date = datetime.fromisoformat(self.general["matchTimeUTCDate"])
        time_difference = match_date - datetime.now(timezone.utc)

        if time_difference < timedelta(hours=1):
            return True
        else:
            return False

    def get_score(self):
        teams = self.header["teams"]
        home_team = teams[0]
        away_team = teams[1]
        score_dict = {home_team["name"] : home_team["score"],
                away_team["name"] : away_team["score"]}

        score_string = f"{home_team['name']} {home_team['score']} - {away_team['score']} {away_team['name']}"
        return score_dict, score_string

    def __repr__(self):
        return (f"Match(id={self.id}, "
                f"league_name='{self.league_name}', "
                f"lineup={self.lineup}, "
                f"started={self.started}, "
                f"finished={self.finished})")

    def __str__(self):
        status = "Finished" if self.finished else "In progress" if self.started else "Not started"
        return f"Match {self.id} in {self.league_name} - Status: {status}"

class Player:
    def __init__(self,
                 name: str,
                 id: int,
                 team_id: int,
                 team_name: str):
        self.name = name
        self.id = id
        self.team_id = team_id
        self.team_name = team_name
        self.next_match = None
        self.starting = False
        self.position = None
        self.events_queue = Queue()
        self.previous_events = {}
        self.info = None

class PlayerManager:
    def __init__(self, json_file: str):
        self.players = self.load_players(json_file)
        self.fotmob = MobFot()
        self.tweepy = TweepyClient()
        self.player_queue = ThreadSafeQueue()

    def load_players(self, json_file: str):
        with open(json_file, 'r') as f:
            json_dict = load(f)
        logging.info(f"Found {len(json_dict)} players.")
        
        return [Player(name, data['id'], data['team_id'], data['team_name'])
                for name, data in json_dict.items()]
    
    def get_next_match(self, player: Player):
        team_details = self.fotmob.get_team(player.team_id, tab="fixtures")
        try:
            next_match_id = team_details["fixtures"]["allFixtures"]["nextMatch"]["id"]
            print(next_match_id)
            match_details = self.fotmob.get_match_details(next_match_id)
            match = Match.from_json(match_details)
            player.next_match = match
            return match
        except Exception as e:
            print(e)
            return None
        # TODO: log errors

    def update_match(self, player: Player, match: Optional[Match]):
        if not match:
            match = player.next_match
        old_tweeted = match.tweeted
        try:
            match_details = self.fotmob.get_match_details(match.id)
            match = Match.from_json(match_details)
            match.tweeted = old_tweeted
            player.next_match = match
        except Exception as e:
            return None
        
    def in_lineup(self, player: Player, match: Match):
        if not match.lineup:
            return False
        lineup = match.lineup.get("lineup")
        if not isinstance(lineup, list):
            return False
        for team in lineup:
            try:
                team_id = team["teamId"]
            except KeyError:
                # Lineup not available yet
                return False
            if team_id == player.team_id:
                team_lineup = team
                break
            
        if not team_lineup:
            return False
        
        try:
            players = team_lineup["players"]
        except KeyError:
            return False
        
        for position in players:
            for _player in position:
                if _player["id"] == str(player.id):
                    player.starting = True
                    player.position = _player["positionStringShort"]
                    player.info = _player
                    return True

        for _player in team_lineup["bench"]:
            if _player["id"] == str(player.id):
                player.info = _player
                return True    

        return False

    def get_opponent(self, player: Player) -> str:
        '''
        Return the name of the opponent in the upcoming match.
        returns:
            opponent (str): opponent name
        '''
        opponent = [team["name"] for team in player.next_match.header["teams"] if team["name"] != player.team_name][0]
        return opponent

    def get_end_of_match_stats(self, player: Player) -> Union[str, Tuple[int, float, int, int]]:
        '''
        This function retrieves the end of match statistics for a player.
        
        returns:
            Tuple[int, float, int, int]: A tuple containing the player's rating, minutes played, goals scored, and assists provided.
        '''
        player_info = player.info
        try:
            player_stats = player_info['stats'][0]['stats']
        except IndexError:
            return "Did not play"
        print(player_stats)

        rating = player_stats['FotMob rating']['stat']['value']
        # TODO: fix minutes played. this still crashes the app
        minutes_played = None
                                                                            
        if player_info["position"] == "Keeper":
            saves = player_stats['Saves']['stat']['value']
            conceded = player_stats['Goals conceded']['stat']['value']
            match_stats = (rating, minutes_played, saves, conceded)
        else:
            goals = player_stats['Goals']['stat']['value']
            assists = player_stats['Assists']['stat']['value']
            match_stats = (rating, minutes_played, goals, assists)

        return match_stats
    
    def check_for_new_events(self, player: Player) -> Tuple[dict, dict]:
        def check_updated(events: dict, previous_events: dict) -> dict:
            # Get events that have been updated, i.e. goals/assist tally
            updated_events = {k: (previous_events[k], events[k]) for k in previous_events if k in events and previous_events[k] != events[k]}
            return updated_events
        
        def check_new(events: dict, previous_events: dict) -> dict:
            # Get new events that arent in the previous events dictionary
            new_events = {k: events[k] for k in events if k not in previous_events}
            return new_events
        
        def get_event_type(key: str, value: str) -> Tuple[GameEvent, str]:
            # Handle each API return key and return the correct enum value
            if key == 'g':
                return GameEvent.GOAL
            elif key == 'as':
                return GameEvent.ASSIST
            elif key == 'yc':
                return GameEvent.YELLOW_CARD
            elif key == 'rc':
                return GameEvent.RED_CARD
            elif key == 'sub':
                for k, v in value.items():
                    if k == 'subbedIn':
                        return (GameEvent.SUB_ON, v)
                    elif k == 'subbedOut':
                        return (GameEvent.SUB_OFF, v)
                    else:
                        print(f"Unknown key {key} with value {value}")
            else:
                print(f"Unknown key {key} with value {value}")
            logging.info(f"Event {k} with value {v}")
        
        if player.next_match:
            # Get current events and check for new/updated events
            for team in player.next_match.lineup["lineup"]:
                team_id = team["teamId"]
                if team_id == player.team_id:
                    team_lineup = team
                    break

            for position in team_lineup["players"]:
                for _player in position:
                    if _player["id"] == str(player.id):
                        player_info = _player
                        break

            for _player in team_lineup["bench"]:
                if _player["id"] == str(player.id):
                    player_info = _player
                    break
            
            events = player_info["events"]
            sub_events = {}
            updated_events = check_updated(events, player.previous_events)
            new_events = check_new(events, player.previous_events)
            if "sub" in updated_events.keys():
                sub_events = check_new(updated_events["sub"][1], updated_events["sub"][0])    
            player.previous_events = events
            
            # Add new events to event queue
            for k, v in updated_events.items():
                player.events_queue.put(get_event_type(k, v))
                
            for k, v in new_events.items():
                player.events_queue.put(get_event_type(k, v))

            for k, v in sub_events.items():
                player.events_queue.put(get_event_type(k, v))
        
    def handle_events(self, player: Player) -> None:
        self.check_for_new_events(player)
        while not player.events_queue.empty():
            event = player.events_queue.get()
            if isinstance(event, tuple):
                event, value = event
                print(value)
            print(player.name, event)
            score_dict, score_string = player.next_match.get_score()
            match event:
                case GameEvent.GOAL:
                    logging.info(f"{player.name}: GameEvent.GOAL")
                    goal_message = f"{player.name} has scored a goal!\n\n{score_string}\n#CFC #Chelsea"
                    image = generate_image(player, "goal", score_dict)
                    self.tweepy.tweet_with_image(goal_message, image)
                    break
                
                case GameEvent.ASSIST:
                    logging.info(f"{player.name}: GameEvent.ASSIST")
                    assist_message = f"{player.name} has provided an assist!\n\n{score_string}\n#CFC #Chelsea"
                    image = generate_image(player, "assist", score_dict)
                    self.tweepy.tweet_with_image(assist_message, image)
                    break
                
                case GameEvent.YELLOW_CARD:
                    logging.info(f"{player.name}: GameEvent.YELLOW_CARD")
                    yellow_card_message = f"{player.name} has received a yellow card!\n\n{score_string}\n#CFC #Chelsea"
                    self.tweepy.tweet(yellow_card_message)
                    break
                
                case GameEvent.RED_CARD:
                    logging.info(f"{player.name}: GameEvent.RED_CARD")
                    red_card_message = f"{player.name} has received a red card! He's been sent off!\n\n{score_string}\n#CFC #Chelsea"
                    self.tweepy.tweet(red_card_message)
                    player.next_match.tweeted["RED_CARD"] = True
                    break
                
                case GameEvent.SUB_ON:
                    logging.info(f"{player.name}: GameEvent.SUB_ON")
                    sub_on_message = f"{player.name} has been subbed on at the {value} minute!\n\n{score_string}\n#CFC #Chelsea"
                    self.tweepy.tweet(sub_on_message)
                    player.next_match.tweeted["SUB_ON"] = True
                    break
                
                case GameEvent.SUB_OFF:
                    logging.info(f"{player.name}: GameEvent.SUB_OFF")
                    sub_off_message = f"{player.name} has been subbed off at the {value} minute!\n\n{score_string}\n#CFC #Chelsea"
                    self.tweepy.tweet(sub_off_message)
                    player.next_match.tweeted["SUB_OFF"] = True
                    break
                
                case GameEvent.STARTED:
                    logging.info(f"{player.name}: GameEvent.STARTED")
                    if player.starting:
                        started_message = f"The {player.team_name} match with {player.name} has started!\n\n{score_string}\n#CFC #Chelsea"
                    else:
                        started_message = f"The {player.team_name} match with {player.name} has started! He's currently on the bench.\n\n{score_string}\n#CFC #Chelsea"                   
                    self.tweepy.tweet(started_message)
                    break
                
                case GameEvent.FINISHED:
                    logging.info(f"{player.name}: GameEvent.FINISHED")
                    resp = self.get_end_of_match_stats(player)
                    if isinstance(resp, tuple):
                        rating, minutes_played, goals, assists = resp
                        played = True
                    else:
                        played = False
                    
                    if played:
                        if player.info["position"] == "Keeper":
                            rating, minutes_played, saves, conceded = resp
                            finished_message = f"""The {player.team_name} match with {player.name} has finished, he made {saves} save(s) and conceded {conceded} goals. He had a rating of {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                        else:
                            rating, minutes_played, goals, assists = resp
                            if goals > 0 and assists > 0:
                                finished_message = f"""The {player.team_name} match with {player.name} has finished, he scored {goals} goal(s) and assisted {assists} time(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            elif goals > 0:
                                finished_message = f"""The {player.team_name} match with {player.name} has finished, he scored {goals} goal(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            elif assists > 0:
                                finished_message = f"""The {player.team_name} match with {player.name} has finished, he assisted {assists} time(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            else:
                                finished_message = f"""The {player.team_name} match with {player.name} has finished, he had a rating of {rating}!\n\n{score_string}\n#CFC #Chelsea"""
                    else:
                        finished_message = f"""The {player.team_name} match with {player.name} has finished. He didn't come off the bench.\n\n#CFC #Chelsea"""
                    
                    self.tweepy.tweet(finished_message)
                    break
                
                case GameEvent.STARTING_LINEUP:
                    logging.info(f"{player.name}: GameEvent.STARTING_LINEUP")
                    opponent = self.get_opponent(player)
                    starting_message = f"{player.name} is in the starting lineup at {player.position} for {player.team_name} against {opponent} in the {player.next_match.league_name}!\n\n#CFC #Chelsea"
                    self.tweepy.tweet(starting_message)
                    break
                
                case GameEvent.BENCH_LINEUP:
                    logging.info(f"{player.name}: GameEvent.BENCH_LINEUP")
                    opponent = self.get_opponent(player)
                    bench_message = f"{player.name} is on the bench for {player.team_name} against {opponent} in the {player.next_match.league_name}!\n\n#CFC #Chelsea"
                    self.tweepy.tweet(bench_message)
                    break


