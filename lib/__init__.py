
import json

config = dict()

def get_tokens():
    global config
    config = json.load(open("token.json", "r"))

get_tokens()

HF_TOKEN = config.get("HF_TOKEN", "")

# a small committee meeting
MIN_SPEAKERS = 5

# 15 city council members, the clerk, the mayor, and 1 extra for unidentified speakers
MAX_SPEAKERS = 15 + 1 + 1 + 1
