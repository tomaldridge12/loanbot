import json
import logging
import os
import threading
import traceback

from datetime import datetime
from time import sleep
from typing import List

from football import FotMob, Player
from utils import GameEvent, ThreadSafeQueue, TweepyClient

   
def hourly_update_players(players: List[Player], in_match_players: ThreadSafeQueue, stop_event) -> None:
    # repeat this every hour
    while not stop_event.is_set():
        try:
            logging.info(f"Beginning hourly player check at {datetime.now()}")
            # Iterate through all players in the player list
            for player in players:
                match_id = fm.get_next_match_id(player)
                if not match_id:
                    logging.info(f"Could not get next match for {player.name}, skipping...")
                    continue
                try:
                    player.match_info = fm.get_player_details_from_match(player, match_id)
                except Exception as e:
                    traceback.print_exc()
                    logging.info(traceback.format_exc())
                    continue

                if isinstance(player.match_info, dict): # i.e. player is in lineup
                    if not player.in_queue:
                        if player.is_match_soon(player.match_info["match_details"]):
                            in_match_players.put(player)
                            player.in_queue = True
                            logging.info(f"Adding {player.name} to queue")
            
            logging.info(f"Ending hourly player check at {datetime.now()}")
            sleep(600)
        except KeyboardInterrupt:
            break
        

def minutely_update_events(in_match_players: ThreadSafeQueue, stop_event) -> None:
    # repeat this every couple of minutes
    while not stop_event.is_set():
        try:
            # Iterate through all players in the in_match_players queue
            for player in in_match_players:
                logging.info(f"Polling {player.name} at {datetime.now()}")
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
                    if player.match_info["started"] and not player.in_match:
                        player.events_queue.put(GameEvent.STARTED)
                        player.in_match = True
                    
                    # tweet match end tweet, i.e. player performance etc
                    # clear player.match_info
                    if player.match_info["finished"] and player.in_match:
                        player.events_queue.put(GameEvent.FINISHED)
                        player.in_match = False
                        try:
                            in_match_players.remove(player)
                            player.in_queue = False
                            logging.info(f"Removing {player.name} from queue")
                        except ValueError:
                            print(f"Attempted to remove {player.name} from queue, but couldn't find it.")

                    # get player event details
                    player.handle_events(tc, fm)
            sleep(60)
        except KeyboardInterrupt:
            break

def signal_handler(sig, frame):
    print("Exiting...")
    stop_event.set()

if __name__ == "__main__":
    # Instantiate clients
    fm = FotMob()
    tc = TweepyClient()
    in_match_players = ThreadSafeQueue()

    # Set up logging
    if not os.path.isdir("logs"):
        os.makedirs("logs")
    logfile_name = f"logs/{datetime.now().strftime("%d-%m-%Y-%H-%M-%S")}.log"
    logging.basicConfig(filename=logfile_name, level=logging.INFO)
    logging.info(f"Starting loanbot at {datetime.now()}")

    # Load player list into Player array
    with open('ids.json', 'r') as f:
        player_data = json.load(f)
    
    logging.info("Loading players list...")
    players = [Player(name, data['id'], data['team_id'], data['team_name'])
                for name, data in player_data.items()]
    
    # Start API threads
    logging.info("Starting threads...")
    stop_event = threading.Event()
    hourly_update = threading.Thread(target=hourly_update_players, args=(players,in_match_players,stop_event), daemon=True)
    events_update = threading.Thread(target=minutely_update_events, args=(in_match_players,stop_event), daemon=True)

    hourly_update.start()
    events_update.start()
    
    # Keep main thread alive and prepare for exiting
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")
        print("Exiting...")
        stop_event.set()

            
