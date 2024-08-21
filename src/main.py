import logging
import os
import threading

from datetime import datetime
from time import sleep

from football import PlayerManager
from utils import GameEvent

MINUTE_DELAY = 60
HOUR_DELAY = MINUTE_DELAY * 10 * 3 # actually 10 minutes but oh well

def hourly_update_players(pm: PlayerManager, stop_event):
    while not stop_event.is_set():
        try:
            logging.info(f"Beginning hourly player check at {datetime.now()}")
            for player in pm.players:
                if player not in pm.player_queue:
                    player.next_match = pm.get_next_match(player)
                    logging.info(f"Got player {player.name} with match {player.next_match}")
                    if player.next_match and player.next_match.is_soon():
                        if pm.in_lineup(player):
                                logging.info(f"Adding {player.name} to queue")
                                pm.player_queue.put(player)

            logging.info(f"Ending hourly player check at {datetime.now()}")
            sleep(HOUR_DELAY)
        except KeyboardInterrupt:
            break

def minutely_update_players(pm: PlayerManager, stop_event):
    while not stop_event.is_set():
        try:
            for player in pm.player_queue:
                logging.info(f"Polling {player.name} at {datetime.now()}")
                pm.update_match(player, player.next_match)
                
                if player.starting:
                    if not player.next_match.tweeted["STARTING_LINEUP"]:
                        player.events_queue.put(GameEvent.STARTING_LINEUP)
                        logging.info(f"{player.name}: GameEvent.STARTING_LINEUP")
                        player.next_match.tweeted["STARTING_LINEUP"] = True
                else:
                    if not player.next_match.tweeted["BENCH_LINEUP"]:
                        player.events_queue.put(GameEvent.BENCH_LINEUP)
                        logging.info(f"{player.name}: GameEvent.BENCH_LINEUP")
                        player.next_match.tweeted["BENCH_LINEUP"] = True

                if player.next_match.started and not player.next_match.finished:
                    if not player.next_match.tweeted["STARTED"]:
                        player.events_queue.put(GameEvent.STARTED)
                        logging.info(f"{player.name}: GameEvent.STARTED")
                        player.next_match.tweeted["STARTED"] = True

                if player.next_match.finished:
                    if not player.next_match.tweeted["FINISHED"]:
                        player.events_queue.put(GameEvent.FINISHED)
                        pm.player_queue.remove(player)
                        logging.info(f"Removing {player.name} from queue")
                        player.next_match.tweeted["FINISHED"] = True
                
                pm.handle_events(player)

            sleep(MINUTE_DELAY)
        except KeyboardInterrupt:
            break


def signal_handler(sig, frame):
    print("Exiting...")
    stop_event.set()

if __name__ == "__main__":
    LOGS_DIR = "../logs"
    IDS_PATH = "../ids.json"

    # Set up logging
    if not os.path.isdir(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    logfile_name = f"{LOGS_DIR}/{datetime.now().strftime("%d-%m-%Y-%H-%M-%S")}.log"
    logging.basicConfig(filename=logfile_name, level=logging.INFO)
    logging.info(f"Starting loanbot at {datetime.now()}")

    # Instantiate clients
    logging.info("Loading players list...")
    pm = PlayerManager(IDS_PATH)
    
    # Start API threads
    logging.info("Starting threads...")
    stop_event = threading.Event()
    hourly_update = threading.Thread(target=hourly_update_players, args=(pm,stop_event), daemon=True)
    events_update = threading.Thread(target=minutely_update_players, args=(pm,stop_event), daemon=True)

    events_update.start()
    hourly_update.start()
    
    # Keep main thread alive and prepare for exiting
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")
        print("Exiting...")
        stop_event.set()