
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