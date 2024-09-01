import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from json import load
from queue import Queue
from typing import Optional, Tuple, Union

from mobfot.client import MobFot

from image import generate_image
from utils import GameEvent, ThreadSafeQueue, TweepyClient

logger = logging.getLogger('LoanBot')

class Match:
    def __init__(self,
                 id: int,
                 league_name: str,
                 general: dict,
                 lineup: dict,
                 header: dict,
                 started: bool = False,
                 finished: bool = False,
                 stats: dict = None
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
        self.date = datetime.fromisoformat(general["matchTimeUTCDate"])
        self.started = started
        self.finished = finished
        self.tweeted = self.setup_tweet_dict()
        self.info = None
        self.stats = stats

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
                logger.error("Couldn't get general or content fields from JSON")
                return None
            
            return cls(
                id=general.get("matchId"),
                league_name=general.get("leagueName"),
                general=general,
                header=json_dict.get("header", {}),
                lineup=content.get('lineup') or content.get('lineup2') or None,
                started=general.get("started"),
                finished=general.get("finished"),
                stats=content.get("playerStats")
            )
        except Exception as e:
            logger.exception(f"Error parsing JSON: {str(e)}")
            return None

    def is_soon(self):
        time_difference = self.date - datetime.now(timezone.utc)

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
        return f"Match {self.id} in {self.league_name} at {self.date} - Status: {status}"

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
        self.events_queue = Queue()
        self.last_processed_events = defaultdict(lambda: -1)
        self.info = None

class PlayerManager:
    def __init__(self, json_file: str, debug_mode: bool):
        self.players = self.load_players(json_file)
        self.fotmob = MobFot()
        self.tweepy = TweepyClient(debug=debug_mode)
        self.player_queue = ThreadSafeQueue()

    def load_players(self, json_file: str):
        with open(json_file, 'r') as f:
            json_dict = load(f)
        logger.info(f"Found {len(json_dict)} players.")
        
        return [Player(name, data['id'], data['team_id'], data['team_name'])
                for name, data in json_dict.items()]
    
    def get_next_match(self, player: Player):
        team_details = self.fotmob.get_team(player.team_id, tab="fixtures")
        try:
            next_match_id = team_details["fixtures"]["allFixtures"]["nextMatch"]["id"]
            match_details = self.fotmob.get_match_details(next_match_id)
            match = Match.from_json(match_details)
            player.next_match = match
            self.update_player_info(player, match)
            return match
        except Exception as e:
            logger.exception(e)
            return None

    def update_player_info(self, player: Player, match: Match):
        if not match.lineup:
            logger.error(f"Getting lineup2 from content field failed for {player.name}")
            return

        for lineup in match.lineup.values():
            if isinstance(lineup, dict) and 'id' in lineup:
                if lineup['id'] == player.team_id:
                  starters = lineup.get('starters', [])
                  subs = lineup.get('subs', [])

        for _player in starters:
            if _player['id'] == player.id:
                player.starting = True
                player.next_match.info = _player
                return
        
        for _player in subs:
            if _player['id'] == player.id:
                player.starting = False
                player.next_match.info = _player
                return
        
        # Otherwise, 
        player.next_match.info = None

    def update_match(self, player: Player, match: Optional[Match]):
        if not match:
            match = player.next_match
        old_tweeted = match.tweeted
        try:
            match_details = self.fotmob.get_match_details(match.id)
            match = Match.from_json(match_details)
            match.tweeted = old_tweeted
            player.next_match = match
            self.update_player_info(player, match)
        except Exception as e:
            logger.exception(e)
            return None
        
    def in_lineup(self, player: Player) -> bool:
        if player.next_match.info:
            return True
        else:
            return False
    
    def get_opponent(self, player: Player) -> str:
        '''
        Return the name of the opponent in the upcoming match.
        returns:
            opponent (str): opponent name
        '''
        opponent = [team["name"] for team in player.next_match.header["teams"] if team["name"] != player.team_name][0]
        return opponent

    def get_end_of_match_report(self, player: Player) -> str:
        '''
        This function retrieves the end of match report for a player.
        
        returns:
            str: a string containing the match report
        '''
        def get_stat_value(player_stats, stat_name):
            try:
                return player_stats[stat_name]['stat']['value']
            except KeyError:
                return 0
            
        stats = player.next_match.stats
        for _id, _items in stats.items():
            if _id == str(player.id):
                try:
                    player_stats = _items['stats'][0]['stats']
                except IndexError:
                    return "Did not play"
                break
        
        rating = player_stats['FotMob rating']['stat']['value']
        accurate_passes = player_stats['Accurate passes']['stat']['value']
        total_passes = player_stats['Accurate passes']['stat']['total']
        passing_perc = round(accurate_passes / total_passes * 100)
        
        chances_created = get_stat_value(player_stats, 'Chances created')
        shots = get_stat_value(player_stats, 'Total shots')
        goals = get_stat_value(player_stats, 'Goals')
        assists = get_stat_value(player_stats, 'Assists')

        report_parts = []
        if passing_perc > 70:
            report_parts.append(f"{int(passing_perc)}% passing percentage")
        if chances_created > 0:
            report_parts.append(f"{int(chances_created)} chances created")
        if shots > 0:
            report_parts.append(f"{int(shots)} shots")
        if goals > 0:
            report_parts.append(f"{int(goals)} goals")
        if assists > 0:
            report_parts.append(f"{int(assists)} assists")

        base_response = f"{rating}"
        if not report_parts:
            return base_response + '.'
        elif len(report_parts) == 1:
            return base_response + ", including " + report_parts[0] + "."
        else:
            last_part = report_parts.pop()
            return base_response + ", including " + ", ".join(report_parts) + " and " + last_part + "."

    
    def check_for_new_events(self, player: Player) -> Tuple[dict, dict]:
        def unwrap_events(event: dict):
            event_type = event.get('type')
            event_time = event.get('time', datetime.now())

            if event_time > player.last_processed_events[event_type]:
                player.last_processed_events[event_type] = event_time
                player.events_queue.put(get_event_type(event_type, event_time))
        
        def get_event_type(key: str, value: str) -> Tuple[GameEvent, str]:
            # Handle each API return key and return the correct enum value
            if key == 'goal':
                return GameEvent.GOAL
            elif key == 'assist':
                return GameEvent.ASSIST
            elif key == 'yellowCard':
                return GameEvent.YELLOW_CARD
            elif key == 'redCard':
                return GameEvent.RED_CARD
            elif key == 'subIn':
                return (GameEvent.SUB_ON, value)
            elif key == 'subOut':
                return (GameEvent.SUB_OFF, value)
            else:
                print(f"Unknown key {key} with value {value}")

            logging.info(f"Event {key} with value {value}")
            
        try: 
            game_events = player.next_match.info["performance"]["events"]
            sub_events = player.next_match.info["performance"]["substitutionEvents"]
        except KeyError:
            return
        
        for event in game_events:
            unwrap_events(event)

        for event in sub_events:
            unwrap_events(event)
        
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
                    self.tweepy.tweet(value + f"\n\n{score_string}\n#CFC #Chelsea")
                    break
                
                case GameEvent.STARTING_LINEUP:
                    logging.info(f"{player.name}: GameEvent.STARTING_LINEUP")
                    opponent = self.get_opponent(player)
                    starting_message = f"{player.name} is in the starting lineup for {player.team_name} against {opponent} in the {player.next_match.league_name}!\n\n#CFC #Chelsea"
                    self.tweepy.tweet(starting_message)
                    break
                
                case GameEvent.BENCH_LINEUP:
                    logging.info(f"{player.name}: GameEvent.BENCH_LINEUP")
                    opponent = self.get_opponent(player)
                    bench_message = f"{player.name} is on the bench for {player.team_name} against {opponent} in the {player.next_match.league_name}!\n\n#CFC #Chelsea"
                    self.tweepy.tweet(bench_message)
                    break


