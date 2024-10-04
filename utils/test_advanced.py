import gzip
import json
import os
import subprocess

import pandas as pd
import requests
from tqdm import tqdm

WORKDIR = os.path.abspath(os.path.dirname(__file__))
projects_storage = os.path.join(WORKDIR, "evaluate")
machine_id = "test"
session_id = "advanced"
api_key = os.environ.get("API_KEY")
base_url = "https://api.deepseek.com/beta"

df = pd.read_csv("normal.csv")
print(df.info())

results = []
for i, row in tqdm(df.iterrows(), total=len(df), desc="Gen"):
    try:
        project_url = os.path.join(projects_storage, row["proj_name"])
        files = subprocess.run(
            f'find {project_url} -type f -not -wholename ".*" -type f -not -name ".*" -not -wholename "*/.*"',
            shell=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        print("Number of files", len(files))
        filesData = []
        for file in files:
            filePath = os.path.relpath(file, projects_storage)
            with open(file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            filesData.append({"filePath": filePath, "content": content})

        target_file = row["relative_path"]
        for item in filesData:
            if target_file == item["filePath"]:
                print("Found", target_file)
                item["content"] = row["prompt"]

        compressedData = gzip.compress(json.dumps(filesData).encode("utf-8"))
        print("Compressed data")
        response = requests.post(
            os.environ.get("URL"),
            data=compressedData,
            headers={
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
            params={"machineId": machine_id, "sessionId": session_id},
        )
        if response.status_code == 200:
            print("Sent project to server")
            prompt = "Complete function " + row["func_name"]
            response = requests.post(
                url=os.environ.get("URL"),
                json={
                    "prompt": prompt,
                    "baseUrl": base_url,
                    "apiKey": api_key,
                    "context": row["prompt"],
                    "targetFile": target_file,
                    "maxIteration": 3,
                },
                headers={"HTTP_ACCEPT": "application/json"},
                params={
                    "machineId": machine_id,
                    "sessionId": session_id,
                    "advanced": "true",
                },
            )
            if response.status_code == 200:
                results.append(response.json()["code"])
                print("Done")
            else:
                results.append("Error while gen code")
        else:
            print(response.content)
            results.append("Can't send project to server")
    except Exception as e:
        print("Error:", e)
        results.append("Unexpected")
    new_df = df[: len(results)]
    new_df["advanced"] = results
    new_df.to_csv("dataset_advanced.csv", index=False)
