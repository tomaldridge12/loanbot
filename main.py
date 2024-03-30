import json
import os
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from time import sleep
from typing import Optional, Tuple, Union
from queue import Queue

from mobfot.client import MobFot

from player import Player
from utils import TweepyClient, GameEvent

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
    
    def get_player_details_from_match(self, player: Player, match_id: int) -> Union[str, dict]:
        '''
        Get the player details from a given match.

        args:
            player (Player): the player to get the match details for
        returns:
            dict: the API response for the player
            str: error message
        '''
        match_id = self.get_next_match_id(player)
        match_details = self.get_match_details(match_id)

        match_date = datetime.fromisoformat(match_details["general"]["matchTimeUTCDate"])
        time_difference = match_date - datetime.now(timezone.utc)

        if time_difference < timedelta(hours=1):
            player_information = None
            started = match_details["general"]["started"]
            finished = match_details["general"]["finished"]
            lineup = match_details["content"]["lineup"]["lineup"]

            for team in lineup:
                if team["teamId"] == player.team_id:
                    team_lineup = team
                    break

            for position in team_lineup["players"]:
                for p in position:
                    if p["id"] == str(player.id):
                        player_information = p
                        break

            for p in team_lineup["bench"]:
                if p["id"] == str(player.id):
                    player_information = p
                    break    

            if not player_information:
                return "Player is not in lineup"

            return {"player_info" : player_information,
                    "match_id" : match_id,
                    "started" : started,
                    "finished" : finished,
                    "match_date" : match_date}
        else:
            return "No lineup available yet"
    
def hourly_update_players(players):
    print("updating fixtures...")
    # repeat this every hour
    while not stop_event.is_set():
        for player in players:
            match_id = fm.get_next_match_id(player)
            player_infomration = fm.get_player_details_from_match(player, match_id)
            player.match_info = player_infomration
        print("sleeping updates")
        sleep(60)

def minutely_update_events(players):
    # repeat this every couple of minutes
    while not stop_event.is_set():
        print("updating events...")
        for player in players:
            if isinstance(player.match_info, dict): # otherwise error message from get_player_details_from_match
                # Get most up to date match details
                player.match_info = fm.get_player_details_from_match(player, player.match_info["match_id"])
                if player.match_info["started"]:
                    # tweet kickoff tweet, but check if kickoff tweet already tweeted
                    if not player.in_match:
                        player.events_queue.put(GameEvent.STARTED)
                        player.in_match = True
                if player.match_info["finished"]:
                    # tweet match end tweet, i.e. player performance etc
                    # clear player.match_info
                    if player.in_match:
                        player.events_queue.put(GameEvent.FINISHED)
                        player.in_match = False

                # get player event details
                player.handle_events(tc)
        print("sleeping events")
        sleep(10)

if __name__ == "__main__":
    fm = FotMob()
    tc = TweepyClient()

    with open('ids.json', 'r') as f:
        player_data = json.load(f)
    
    players = [Player(name, data['id'], data['team_id'], data['team_name'])
                for name, data in player_data.items()]
    
    hourly_update = threading.Thread(target=hourly_update_players, args=(players,))
    events_update = threading.Thread(target=minutely_update_events, args=(players,))

    stop_event = threading.Event()

    hourly_update.start()
    events_update.start()
    
    # Keep main thread alive
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        stop_event.set()
        hourly_update.join()
        events_update.join()
            