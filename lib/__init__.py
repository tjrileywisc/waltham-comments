
import json

config = dict()

def get_config():
    global config
    config = json.load(open("config.json", "r"))

get_config()

HF_TOKEN = config.get("HF_TOKEN", "")

# 15 city council members, the clerk, the mayor, and 1 extra for unidentified speakers
MIN_SPEAKERS = 15 + 1 + 1 + 1
