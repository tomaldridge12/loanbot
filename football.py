import logging
from datetime import datetime, timedelta, timezone
from queue import Queue
from typing import Optional, Tuple, Union

from mobfot.client import MobFot

from image import generate_image
from utils import GameEvent, TweepyClient

class Player:
    def __init__(self, name: str, id: int, team_id: int, team_name: str):
        self.name = name
        self.id = id
        self.team_id = team_id
        self.team_name = team_name
        self.match_info = None
        self.previous_events = {}
        self.events_queue = Queue()
        self.in_match = False
        self.starting = False
        self.tweeted_lineup = False
        self.in_queue = False

    def __repr__(self):
        return f'{self.name}, {self.team_name}'
    
    def check_for_new_events(self) -> Tuple[dict, dict]:
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
        
        if self.match_info:
            # Get current events and check for new/updated events
            events = self.match_info["player_info"]["events"]
            sub_events = {}
            updated_events = check_updated(events, self.previous_events)
            new_events = check_new(events, self.previous_events)
            if "sub" in updated_events.keys():
                sub_events = check_new(updated_events["sub"][1], updated_events["sub"][0])    
            self.previous_events = events
            
            # Add new events to event queue
            for k, v in updated_events.items():
                self.events_queue.put(get_event_type(k, v))
                
            for k, v in new_events.items():
                self.events_queue.put(get_event_type(k, v))

            for k, v in sub_events.items():
                self.events_queue.put(get_event_type(k, v))
        
    def handle_events(self, tweet_client: TweepyClient, fotmob_client) -> None:
        self.check_for_new_events()
        while not self.events_queue.empty():
            event = self.events_queue.get()
            if isinstance(event, tuple):
                event, value = event
                print(value)
            print(self.name, event)
            score_dict, score_string = fotmob_client.get_match_score(self.match_info["match_id"])
            match event:
                case GameEvent.GOAL:
                    logging.info(f"{self.name}: GameEvent.GOAL")
                    goal_message = f"{self.name} has scored a goal!\n\n{score_string}\n#CFC #Chelsea"
                    image = generate_image(self, "goal", score_dict)
                    tweet_client.tweet_with_image(goal_message, image)
                    break
                
                case GameEvent.ASSIST:
                    logging.info(f"{self.name}: GameEvent.ASSIST")
                    assist_message = f"{self.name} has provided an assist!\n\n{score_string}\n#CFC #Chelsea"
                    image = generate_image(self, "assist", score_dict)
                    tweet_client.tweet_with_image(assist_message, image)
                    break
                
                case GameEvent.YELLOW_CARD:
                    logging.info(f"{self.name}: GameEvent.YELLOW_CARD")
                    yellow_card_message = f"{self.name} has received a yellow card!\n\n{score_string}\n#CFC #Chelsea"
                    tweet_client.tweet(yellow_card_message)
                    break
                
                case GameEvent.RED_CARD:
                    logging.info(f"{self.name}: GameEvent.RED_CARD")
                    red_card_message = f"{self.name} has received a red card! He's been sent off!\n\n{score_string}\n#CFC #Chelsea"
                    tweet_client.tweet(red_card_message)
                    break
                
                case GameEvent.SUB_ON:
                    logging.info(f"{self.name}: GameEvent.SUB_ON")
                    sub_on_message = f"{self.name} has been subbed on at the {value} minute!\n\n{score_string}\n#CFC #Chelsea"
                    tweet_client.tweet(sub_on_message)
                    break
                
                case GameEvent.SUB_OFF:
                    logging.info(f"{self.name}: GameEvent.SUB_OFF")
                    sub_off_message = f"{self.name} has been subbed off at the {value} minute!\n\n{score_string}\n#CFC #Chelsea"
                    tweet_client.tweet(sub_off_message)
                    break
                
                case GameEvent.STARTED:
                    logging.info(f"{self.name}: GameEvent.STARTED")
                    if self.starting:
                        started_message = f"The {self.team_name} match with {self.name} has started!\n\n{score_string}\n#CFC #Chelsea"
                    else:
                        started_message = f"The {self.team_name} match with {self.name} has started! He's currently on the bench.\n\n{score_string}\n#CFC #Chelsea"                   
                    tweet_client.tweet(started_message)
                    break
                
                case GameEvent.FINISHED:
                    logging.info(f"{self.name}: GameEvent.FINISHED")
                    resp = self.get_end_of_match_stats()
                    if isinstance(resp, tuple):
                        rating, minutes_played, goals, assists = resp
                        played = True
                    else:
                        played = False
                    
                    if played:
                        if self.match_info["player_info"]["position"] == "Keeper":
                            rating, minutes_played, saves, conceded = resp
                            finished_message = f"""The {self.team_name} match with {self.name} has finished, he made {saves} save(s) and conceded {conceded} goals. He had a rating of {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                        else:
                            rating, minutes_played, goals, assists = resp
                            if goals > 0 and assists > 0:
                                finished_message = f"""The {self.team_name} match with {self.name} has finished, he scored {goals} goal(s) and assisted {assists} time(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            elif goals > 0:
                                finished_message = f"""The {self.team_name} match with {self.name} has finished, he scored {goals} goal(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            elif assists > 0:
                                finished_message = f"""The {self.team_name} match with {self.name} has finished, he assisted {assists} time(s)! FotMob rated him {rating}.\n\n{score_string}\n#CFC #Chelsea"""
                            else:
                                finished_message = f"""The {self.team_name} match with {self.name} has finished, he had a rating of {rating}!\n\n{score_string}\n#CFC #Chelsea"""
                    else:
                        finished_message = f"""The {self.team_name} match with {self.name} has finished. He didn't come off the bench.\n\n#CFC #Chelsea"""
                    
                    tweet_client.tweet(finished_message)
                    break
                
                case GameEvent.STARTING_LINEUP:
                    logging.info(f"{self.name}: GameEvent.STARTING_LINEUP")
                    opponent = self.get_opponent()
                    starting_message = f"{self.name} is in the starting lineup at {self.match_info["player_info"]["positionStringShort"]} for {self.team_name} against {opponent} in the {self.match_info["match_details"]["general"]["parentLeagueName"]}!\n\n#CFC #Chelsea"
                    tweet_client.tweet(starting_message)
                    break
                
                case GameEvent.BENCH_LINEUP:
                    logging.info(f"{self.name}: GameEvent.BENCH_LINEUP")
                    opponent = self.get_opponent()
                    bench_message = f"{self.name} is on the bench for {self.team_name} against {opponent} in the {self.match_info["match_details"]["general"]["parentLeagueName"]}!\n\n#CFC #Chelsea"
                    tweet_client.tweet(bench_message)
                    break

    def get_end_of_match_stats(self) -> Union[str, Tuple[int, float, int, int]]:
        '''
        This function retrieves the end of match statistics for a player.
        
        returns:
            Tuple[int, float, int, int]: A tuple containing the player's rating, minutes played, goals scored, and assists provided.
        '''
        player_info = self.match_info['player_info']
        try:
            player_stats = player_info['stats'][0]['stats']
        except IndexError:
            return "Did not play"
        print(player_stats)

        rating = player_stats['FotMob rating']['stat']['value']
        # TODO: fix minutes played. this still crashes the app
        minutes_played = None
        # try:
        #     minutes_played = player_stats['Minutes played']['stat']['value']
        # except KeyError:
        #     try:
        #         minutes_played = player_info["minutesPlayed"]
        #         logging.info("Falling back to backup minutes played")
        #     except KeyError:
        #         try:
        #             sub_on_time = player_info["timeSubbedOn"]
        #             if sub_on_time != "None":
        #                 sub_on_time = float(sub_on_time)
        #             else:
        #                 sub_on_time = 0
                    
        #             sub_off_time = player_info["timeSubbedOff"]
        #             if sub_off_time != "None":
        #                 sub_off_time = float(sub_off_time)
        #             else:
        #                 sub_off_time = 0
                    
        #             minutes_played = 90 - sub_off_time - sub_on_time
        #             logging.info("Falling back to second backup minutes played")
        #         except KeyError:
        #             minutes_played = 'unknown'
        #             logging.info(f"Failed to get minuted played for {self.name}")
                                                                            
        if self.match_info["player_info"]["position"] == "Keeper":
            saves = player_stats['Saves']['stat']['value']
            conceded = player_stats['Goals conceded']['stat']['value']
            match_stats = (rating, minutes_played, saves, conceded)
        else:
            goals = player_stats['Goals']['stat']['value']
            assists = player_stats['Assists']['stat']['value']
            match_stats = (rating, minutes_played, goals, assists)

        return match_stats

    def get_opponent(self) -> str:
        '''
        Return the name of the opponent in the upcoming match.
        returns:
            opponent (str): opponent name
        '''
        opponent = [team["name"] for team in self.match_info["match_details"]["header"]["teams"] if team["name"] != self.team_name][0]
        return opponent

    def is_match_soon(self, match_details: dict) -> bool:
        '''
        Evaluate whether the upcoming match is within 1 hour.

        returns:
            bool: if the match is within 1 hour or not
        '''
        if not match_details:
            if not self.match_info:
                raise ValueError("No match available")
            match_details = self.match_info["match_details"]
        match_date = datetime.fromisoformat(match_details["general"]["matchTimeUTCDate"])
        time_difference = match_date - datetime.now(timezone.utc)

        if time_difference < timedelta(hours=1):
            return True
        else:
            return False

class FotMob(MobFot):
    def __init__(self, **kwargs):
        super(FotMob, self).__init__(kwargs)
        self.all_leagues_url = f"{self.BASE_URL}/allLeagues?"
        self.teams_seasons_stats_url = f"{self.BASE_URL}/teamseasonstats?"
        self.player_url = f"{self.BASE_URL}/playerData?"
        self.search_url = f"{self.BASE_URL}/searchapi?"

    def get_next_match_id(self, player: Player):
        '''
        Get the next upcoming match for a given Player.

        args:
            player (Player): the Player object for a given player
        returns:
            int: the match ID 
        '''
        team_details = self.get_team(player.team_id, tab="fixtures")
        next_match_id = team_details["fixtures"]["allFixtures"]["nextMatch"]["id"]
        return next_match_id
    
    def get_player_details_from_match(self, player: Player, match_id: Optional[int]) -> Union[str, dict]:
        '''
        Get the player details from a given match.

        args:
            player (Player): the player to get the match details for
        returns:
            dict: the API response for the player
            str: error message
        '''
        if not match_id:
            match_id = self.get_next_match_id(player)
        match_details = self.get_match_details(match_id)

        if player.is_match_soon(match_details):
            player_information = None
            started = match_details["general"]["started"]
            finished = match_details["general"]["finished"]
            try:
                lineup = match_details["content"]["lineup"]["lineup"]
            except TypeError:
                # In this case, the lineup info isn't available yet. This means
                # that indexing into match_details will error, so we must handle this
                return 'Lineup not available yet'

            for team in lineup:
                if team["teamId"] == player.team_id:
                    team_lineup = team
                    break
            
            if not team_lineup:
                return 'Lineup not available yet'

            for position in team_lineup["players"]:
                for _player in position:
                    if _player["id"] == str(player.id):
                        player_information = _player
                        player.starting = True
                        break

            for _player in team_lineup["bench"]:
                if _player["id"] == str(player.id):
                    player_information = _player
                    break    

            if not player_information:
                return "Player is not in lineup"

            return {"player_info" : player_information,
                    "match_details" : match_details,
                    "match_id" : match_id,
                    "started" : started,
                    "finished" : finished}
        else:
            return "No lineup available yet"

    def get_match_score(self, match_id: int) -> Tuple[dict, str]:
        match_details = self.get_match_details(match_id)
        teams = match_details["header"]["teams"]
        home_team = teams[0]
        away_team = teams[1]
        score_dict = {home_team["name"] : home_team["score"],
                away_team["name"] : away_team["score"]}

        score_string = f"{home_team['name']} {home_team['score']} - {away_team['score']} {away_team['name']}"
        return score_dict, score_string
 

