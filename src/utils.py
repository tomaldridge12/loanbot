import logging
from enum import Enum
from io import BytesIO
from queue import Queue
from threading import Lock

import tweepy
from dotenv import dotenv_values
from PIL import Image

class GameEvent(Enum):
    GOAL = 1
    ASSIST = 2
    SUB_ON = 3
    SUB_OFF = 4
    YELLOW_CARD = 5
    RED_CARD = 6
    STARTED = 7
    FINISHED = 8
    STARTING_LINEUP = 9
    BENCH_LINEUP = 10

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