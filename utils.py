from enum import Enum
import os

import tweepy
from dotenv import dotenv_values

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
        config = dotenv_values(".env")
        print(config)

        self.client = tweepy.Client(bearer_token=config["BEARER_TOKEN"], consumer_key=config["API_KEY"], consumer_secret=config["API_KEY_SECRET"],
                                    access_token=config["ACCESS_TOKEN"], access_token_secret=config["ACCESS_TOKEN_SECRET"])

    def tweet(self,string: str):
        try:
            self.client.create_tweet(text=string, user_auth=True)
        except Exception as e:
            print(e)