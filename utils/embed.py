import os

import numpy as np
import pandas as pd
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"

# Load the pre-trained model and tokenizer
model_name = "Salesforce/codet5p-110m-embedding"
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
model = model.to(device)
df = pd.read_parquet(os.path.join(WORK_DIR, "curated_dataset.parquet"))
tqdm.pandas()


def encode(code_snippet):
    inputs = tokenizer(
        code_snippet, return_tensors="pt", padding=True, truncation=True
    ).to(device)
    with torch.no_grad():
        embedding = model(**inputs).cpu().numpy().ravel()
        return embedding


df["embedding"] = df["prompt"].progress_apply(lambda x: encode(x))
df.to_parquet(os.path.join(WORK_DIR, "embedded.parquet"))
