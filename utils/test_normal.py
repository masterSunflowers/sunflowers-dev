import os

import dotenv
import pandas as pd
import requests
from tqdm import tqdm

api_key = os.environ.get("API_KEY")
base_url = "https://api.deepseek.com/beta"
machine_id = "test"
session_id = "normal"

dataset = pd.read_csv("dataset_final.csv")
results = []
for _, row in tqdm(dataset.iterrows(), total=len(dataset), desc="Normal"):
    try:
        prompt = "Complete function `" + row["signature"] + "`"
        response = requests.post(
            url=os.environ.get("URL"),
            json={
                "prompt": prompt,
                "baseUrl": base_url,
                "apiKey": api_key,
                "context": row["prompt"],
            },
            headers={"HTTP_ACCEPT": "application/json"},
            params={
                "machineId": machine_id,
                "sessionId": session_id,
                "advanced": "false",
            },
        )
        if response.status_code == 200:
            results.append(response.json()["code"])
        else:
            results.append("Error")
        new_df = dataset[: len(results)]
        new_df["normal"] = results
        new_df.to_csv("dataset_normal.csv")
    except Exception as e:
        print(e)
        results.append("Unexpected")
