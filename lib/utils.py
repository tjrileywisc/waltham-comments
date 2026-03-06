
import logging
import logging.handlers
import os

import torch
from torch.utils.tensorboard import SummaryWriter

def make_tensorboard_writer(embeddings_dict):

    labels = list(embeddings_dict.keys())
    vectors = list(embeddings_dict.values())

    embedding_tensor = torch.tensor(vectors)
        
    writer = SummaryWriter(log_dir="runs/embeddings")

    writer.add_embedding(
        embedding_tensor,
        metadata=labels,
        tag="label_embeddings"
    )

    writer.close()
    
def setup_logging(log_dir: str = "logs", log_file: str = "meeting_downloader.log"):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # rotating file handler - keeps last 10 logs, rotates at midnight
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)  # less verbose on console

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)