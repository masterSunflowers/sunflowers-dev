import os
import torch
import numpy as np
import pandas as pd
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

# Set the working directory
WORK_DIR = os.path.abspath(os.path.dirname(__file__))

# Determine the device to use (GPU if available, otherwise CPU)
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load the pre-trained model and tokenizer
model_name = "Salesforce/codet5p-110m-embedding"
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
model = model.to(device)

# Load the dataset
df = pd.read_parquet(os.path.join(WORK_DIR, "curated_dataset.parquet"))
tqdm.pandas()

def encode(code_snippet):
    """
    Encode a code snippet into an embedding using the pre-trained model.
    
    Args:
        code_snippet (str): The code snippet to encode.
    
    Returns:
        np.ndarray: The embedding of the code snippet.
    """
    inputs = tokenizer(
        code_snippet, return_tensors="pt", padding=True, truncation=True
    ).to(device)
    with torch.no_grad():
        embedding = model(**inputs).last_hidden_state.mean(dim=1).cpu().numpy().ravel()
        return embedding

# Encode the 'prompt' column and store the embeddings in a new 'embedding' column
df["embedding"] = df["prompt"].progress_apply(encode)

# Save the DataFrame with embeddings to a new Parquet file
df.to_parquet(os.path.join(WORK_DIR, "embedded.parquet"))
