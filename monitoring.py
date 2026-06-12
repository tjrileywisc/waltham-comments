
import json
import logging
import logging.config


def setup_logging(logger_name: str | None) -> logging.Logger:
    with open("log_config.json") as f:
        config = json.load(f)

    if logger_name:
        config["loggers"][logger_name] = {
            "handlers": ["default"],
            "level": "DEBUG",
            "propagate": False,
        }

    logging.config.dictConfig(config)
    return logging.getLogger(logger_name)
