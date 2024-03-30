from queue import Queue
from typing import Tuple

from utils import TweepyClient, GameEvent

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
        
    def handle_events(self, tweet_client: TweepyClient) -> None:
        self.check_for_new_events()
        while not self.events_queue.empty():
            event = self.events_queue.get()
            if isinstance(event, tuple):
                event, value = event
            print(event)
            
            match event:
                case GameEvent.GOAL:
                    goal_message = f"{self.name} has scored a goal!\n\n#CFC #Chelsea"
                    tweet_client.tweet(goal_message)
                    break
                case GameEvent.ASSIST:
                    assist_message = f"{self.name} has assisted!\n\n#CFC #Chelsea"
                    tweet_client.tweet(assist_message)
                    break
                case GameEvent.YELLOW_CARD:
                    yellow_card_message = f"{self.name} has received a yellow card!\n\n#CFC #Chelsea"
                    tweet_client.tweet(yellow_card_message)
                    break
                case GameEvent.RED_CARD:
                    red_card_message = f"{self.name} has received a red card!\n\n#CFC #Chelsea"
                    tweet_client.tweet(red_card_message)
                    break
                case GameEvent.SUB_ON:
                    sub_on_message = f"{self.name} has been subbed on at {value} minutes!\n\n#CFC #Chelsea"
                    tweet_client.tweet(sub_on_message)
                    break
                case GameEvent.SUB_OFF:
                    sub_off_message = f"{self.name} has been subbed off at {value} minutes!\n\n#CFC #Chelsea"
                    tweet_client.tweet(sub_off_message)
                    break
                case GameEvent.STARTED:
                    started_message = f"The {self.team_name} match with {self.name} has started!\n\n#CFC #Chelsea"
                    tweet_client.tweet(started_message)
                    break
                case GameEvent.FINISHED:
                    minutes_played, rating, goals, assists = self.get_end_of_match_stats()
                    if goals > 0 and assists > 0:
                        finished_message = f"""The {self.team_name} match with {self.name} has finished, he played {minutes_played} minutes, scoring {goals} goal(s) and assisting {assists} time(s)! FotMob rated him {rating}.\n\n#CFC #Chelsea"""
                    elif goals > 0:
                        finished_message = f"""The {self.team_name} match with {self.name} has finished, he played {minutes_played} minutes, scoring {goals} goal(s)! FotMob rated him {rating}.\n\n#CFC #Chelsea"""
                    elif assists > 0:
                        finished_message = f"""The {self.team_name} match with {self.name} has finished, he played {minutes_played} minutes, assisting {assists} time(s)! FotMob rated him {rating}.\n\n#CFC #Chelsea"""
                    else:
                        finished_message = f"""The {self.team_name} match with {self.name} has finished, he played {minutes_played} minutes and had a rating of {rating}!\n\n#CFC #Chelsea"""
                    tweet_client.tweet(finished_message)
                    break
                case GameEvent.STARTING_LINEUP:
                    starting_message = f"{self.name} is in the starting lineup at {self.match_info["player_info"]["position"]} for {self.team_name} in the {self.match_info["general"]["parentLeagueName"]}!\n\n#CFC #Chelsea"
                    tweet_client.tweet(starting_message)
                    break
                case GameEvent.BENCH_LINEUP:
                    bench_message = f"{self.name} is on the bench for {self.team_name} in the {self.match_info["general"]["parentLeagueName"]}!\n\n#CFC #Chelsea"
                    tweet_client.tweet(bench_message)
                    break

    def get_end_of_match_stats(self) -> Tuple[int, float, int, int]:
        player_info = self.match_info['player_info']
        player_stats = player_info['stats']['stats']
        rating = player_stats['FotMob rating']['stat']['value']
        goals = player_stats['Goals']['stat']['value']
        assists = player_stats['Assists']['stat']['value']

        time_subbed_on = self.match_info['timeSubbedOn']
        time_subbed_off = self.match_info['timeSubbedOff']
        match_started = time_subbed_on if time_subbed_on != "None" else 0 
        match_finished = time_subbed_off if time_subbed_off != "None" else 90
        minutes_played = match_finished - match_started

        return minutes_played, rating, goals, assists
