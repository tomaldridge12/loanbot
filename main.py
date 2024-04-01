import json
import logging
import threading
import traceback

from collections import deque
from time import sleep
from typing import List

from football import FotMob, Player
from utils import GameEvent, ThreadSafeQueue, TweepyClient

   
def hourly_update_players(players: List[Player], in_match_players: deque[Player]) -> None:
    # repeat this every hour
    while not stop_event.is_set():
        for player in players:
            match_id = fm.get_next_match_id(player)
            try:
                player.match_info = fm.get_player_details_from_match(player, match_id)
            except Exception as e:
                traceback.print_exc()
                logging.info(traceback.format_exc())
                continue
            if isinstance(player.match_info, dict):
                if player.is_match_soon(player.match_info["match_details"]):
                    in_match_players.put(player)
                    logging.info(f"Adding {player.name} to queue")

        sleep(600)

def minutely_update_events(in_match_players: deque[Player]) -> None:
    # repeat this every couple of minutes
    while not stop_event.is_set():

        for player in in_match_players:
            logging.info(f"Player: {player.name}")
            if isinstance(player.match_info, dict): # otherwise error message from get_player_details_from_match
                # Get most up to date match details
                try:
                    player.match_info = fm.get_player_details_from_match(player, player.match_info["match_id"])
                except Exception as e:
                    traceback.print_exc()
                    logging.info(f"{traceback.format_exc()}")
                    continue

                # tweet starting lineup or bench lineup
                if not player.tweeted_lineup:
                    if player.starting:
                        player.events_queue.put(GameEvent.STARTING_LINEUP)
                    else:
                        player.events_queue.put(GameEvent.BENCH_LINEUP)
                    player.tweeted_lineup = True
                
                # tweet kickoff tweet, but check if kickoff tweet already tweeted
                if player.match_info["started"]:
                    if not player.in_match:
                        player.events_queue.put(GameEvent.STARTED)
                        player.in_match = True
                
                # tweet match end tweet, i.e. player performance etc
                # clear player.match_info
                if player.match_info["finished"]:
                    if player.in_match:
                        player.events_queue.put(GameEvent.FINISHED)
                        player.in_match = False
                        try:
                            in_match_players.remove(player)
                        except ValueError:
                            print(f"Attempted to remove {player.name} from queue, but couldn't find it.")

                # get player event details
                player.handle_events(tc, fm)
        sleep(60)

if __name__ == "__main__":
    fm = FotMob()
    tc = TweepyClient()
    in_match_players = ThreadSafeQueue()
    logging.basicConfig(filename="log.log", level=logging.INFO)

    with open('ids.json', 'r') as f:
        player_data = json.load(f)
    
    players = [Player(name, data['id'], data['team_id'], data['team_name'])
                for name, data in player_data.items()]
    
    hourly_update = threading.Thread(target=hourly_update_players, args=(players,in_match_players,))
    events_update = threading.Thread(target=minutely_update_events, args=(in_match_players,))

    stop_event = threading.Event()

    # hourly_update.daemon = True
    # events_update.daemon = True

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
            