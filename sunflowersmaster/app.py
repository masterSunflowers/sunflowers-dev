import gzip
import json
import os
from pathlib import Path
from time import sleep
from typing import Tuple

import docker

client = docker.from_env()

import requests
from flask import Flask, request

app = Flask(__name__)


@app.post("/v1/api/store")
def store_project():
    try:
        machine_id = request.args.get("machineId")
        compressed_data = request.data
        decompressed_data = gzip.decompress(compressed_data)
        data = json.loads(decompressed_data)
        for item in data:
            absolute_path = Path(
                os.path.join("projects", machine_id, item["filePath"])
            )
            os.makedirs(absolute_path.parent, exist_ok=True)
            with open(
                absolute_path, "w", encoding="utf-8", errors="ignore"
            ) as f:
                f.write(item["content"])
        print("Received project!")
        return {"message": f"Data received successfully"}, 200

    except Exception as e:
        print("Something went wrong when store project!")
        return {"error": str(e)}, 500


def rename_worker(
    machine_id: str, old_session_id: str, new_session_id: str
) -> int:
    try:
        container = client.containers.get(f"{machine_id}--{old_session_id}")
        container.rename(f"{machine_id}--{new_session_id}")
        print(
            (
                f"Rename worker:\n"
                f"\tfrom: {machine_id}--{old_session_id}\n"
                f"\tto: {machine_id}--{new_session_id}"
            )
        )
        return 0
    except:
        print("Failed to rename worker")
        return 1


def create_worker(machine_id: str, session_id: str) -> int:
    try:
        client.containers.run(
            "worker",
            detach=True,
            name=f"{machine_id}--{session_id}",
            ports={"8001/tcp": 8001},
        )
        container = client.containers.get(f"{machine_id}--{session_id}")
        message = "* Running on http://172.17.0.2:8001"
        timeout = 10
        stop_time = 1
        elapsed_time = 0
        while (
            message not in container.logs().decode() and elapsed_time < timeout
        ):
            sleep(stop_time)
            elapsed_time += stop_time
            continue
        if message in container.logs().decode():
            print("Container is ready!")
            return 0
        else:
            print("Container take too long to start!")
            return 2
    except:
        print("Failed to create worker")
        return 1


# DOING
def run_worker(
    machine_id: str, session_id: str, advanced: bool, data
) -> Tuple[str, str]:
    if advanced == "false":
        print("Generating normal")
        response = requests.post(
            "http://localhost:8001/v1/api/normal",
            json=data,
            headers={"HTTP_ACCEPT": "application/json"},
        )
        if response.status_code == 200:
            return response.json()["code"], None
        else:
            raise Exception(response.json()["error"])
    else:
        print("Enter advanced generate mode")
        pass


@app.post("/v1/api/gen")
def gen():
    try:
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        advanced = request.args.get("advanced")
        data = json.loads(request.data)
        try:
            with open("sessions.json", "r") as f:
                sessions = json.load(f)
        except:
            sessions = {}
        if not sessions.get(machine_id):
            return_code = create_worker(machine_id, session_id)
            if return_code == 1:
                raise Exception("Can not create worker")
            sessions[machine_id] = session_id
            with open("sessions.json", "w") as f:
                json.dump(sessions, f)
        else:
            if sessions[machine_id] != session_id:
                return_code = rename_worker(
                    machine_id, sessions[machine_id], session_id
                )
                if return_code == 1:
                    raise Exception("Can not rename worker")
                sessions[machine_id] = session_id
                with open("sessions.json", "w") as f:
                    json.dump(sessions, f)
        print("Prepare to run worker")
        code, details = run_worker(machine_id, session_id, advanced, data)
        print("Generate successfully")
        return {"code": f"```python\n{code}\n```", "details": details}, 200
    except Exception as e:
        print(str(e))
        if "authentication_error" in str(e):
            return {"error": str(e)}, 401
        else:
            return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
