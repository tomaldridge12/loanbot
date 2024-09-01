import logging
from enum import Enum
from io import BytesIO
from logging.handlers import RotatingFileHandler
from queue import Queue
from threading import excepthook, Lock

import tweepy
from dotenv import dotenv_values
from PIL import Image

class GameEvent(Enum):
    GOAL = 1
    ASSIST = 2
    YELLOW_CARD = 3
    RED_CARD = 4
    SUB_ON = 5
    SUB_OFF = 6
    STARTED = 7
    FINISHED = 8
    STARTING_LINEUP = 9
    BENCH_LINEUP = 10

def setup_logger(logfile_name: str):
    logger = logging.getLogger('LoanBot')
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(logfile_name)
    
    log_format = logging.Formatter('%(asctime)s::%(levelname)s - %(message)s')
    
    console_handler.setFormatter(log_format)
    file_handler.setFormatter(log_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

def log_unhandled_exception(args):
    logger = logging.getLogger('LoanBot')
    logger.critical("Unhandled exception in thread", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

class TweepyClient:
    def __init__(self):
        config = dotenv_values("../.env")

        auth = tweepy.OAuth1UserHandler(config["API_KEY"], config["API_KEY_SECRET"])
        auth.set_access_token(key=config["ACCESS_TOKEN"], secret=config["ACCESS_TOKEN_SECRET"])
        self.client_v1 = tweepy.API(auth)
        
        self.client_v2 = tweepy.Client(bearer_token=config["BEARER_TOKEN"], consumer_key=config["API_KEY"], consumer_secret=config["API_KEY_SECRET"],
                                    access_token=config["ACCESS_TOKEN"], access_token_secret=config["ACCESS_TOKEN_SECRET"])
    
    def tweet(self, string: str) -> None:
        try:
            self.client_v2.create_tweet(text=string, user_auth=True)
            logging.info(f"Tweeted: {string}")
        except Exception as e:
            print(e)

    def tweet_with_image(self, string: str, image: Image) -> None:
        b = BytesIO()
        image.save(b, "PNG")
        b.seek(0)
        try:
            ret = self.client_v1.media_upload(filename="dummy", file=b)
            self.client_v2.create_tweet(text=string, media_ids=[ret.media_id_string])
            logging.info(f"Tweeted with image: {string}")        
        except Exception as e:
            print(e)

class ThreadSafeQueue:
    def __init__(self):
        self._queue = Queue()
        self._lock = Lock()

    def put(self, item):
        with self._lock:
            self._queue.put(item)

    def get(self):
        with self._lock:
            return self._queue.get()

    def remove(self, value):
        with self._lock:
            items = []
            while not self._queue.empty():
                item = self._queue.get()
                if item != value:
                    items.append(item)
            for item in items:
                self._queue.put(item)

    def __iter__(self):
        # Create a copy of the queue to iterate through
        with self._lock:
            items = list(self._queue.queue)
        for item in items:
            yield item

    def __contains__(self, item):
        with self._lock:
            return item in self._queue.queue

    def __len__(self):
        with self._lock:
            return self._queue.qsize()