import gzip
import json
import os
import signal
import sqlite3
import sys
import tarfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from time import sleep
from typing import Tuple

import docker
import docker.errors
import dotenv
import requests
from flask import Flask, request

client = docker.from_env()
dotenv.load_dotenv(override=True)


app = Flask(__name__)

WORK_DIR = os.path.abspath(os.path.dirname(__file__))


def handle_termination(signal, frame):
    try:
        with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
            machines = json.load(f)
    except Exception as e:
        machines = {}
    for machine_id in machines:
        try:
            container = client.containers.get(
                f"{machine_id}--{machines[machine_id]['session_id']}"
            )
            if container.status == "running":
                container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(
                f"Container name {machine_id}--{machines[machine_id]['session_id']} not found"
            )
        except Exception as e:
            print(f"An error occur: {e}")

    with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
        json.dump({}, f)
    sys.exit(0)


signal.signal(signalnum=signal.SIGINT, handler=handle_termination)
signal.signal(signalnum=signal.SIGTERM, handler=handle_termination)


@app.post("/v1/api/store")
def store_project():
    try:
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        compressed_data = request.data
        decompressed_data = gzip.decompress(compressed_data)
        data = json.loads(decompressed_data)
        if not data:
            return {"message": f"No data received"}, 200
        workspace = os.path.split(data[0]["filePath"])[0]
        if os.path.exists(os.path.join("projects", machine_id, workspace)):
            os.system(
                f"rm -rf {os.path.join('projects', machine_id, workspace)}"
            )
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
        try:
            with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
                machines = json.load(f)
        except Exception:
            machines = {}
        machines[machine_id] = {}
        machines[machine_id]["session_id"] = session_id
        machines[machine_id]["workspace"] = workspace
        with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
            json.dump(machines, f)
        return {"message": f"Data received successfully"}, 200
    except Exception as e:
        print(e)
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
        message = "* Running on all addresses (0.0.0.0)"
        timeout = int(os.environ.get("INIT_WORKER_TIMEOUT"))
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
    except Exception as e:
        print(e)
        return 1


def tar(folder_path):
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            tar.add(item_path, arcname=item)
    tar_stream.seek(0)
    return tar_stream


def copy_to_container(
    container_name: str, folder_path: str, container_dest: str
):
    try:
        container = client.containers.get(container_name)
        tar_stream = tar(folder_path)
        print(
            f"Copying contents of {folder_path} to container {container_name}:{container_dest}"
        )
        container.put_archive(container_dest, tar_stream)
        print("Copied!")
    except docker.errors.NotFound:
        print(f"Container {container_name} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


# DOING
def run_worker(machine_id: str, advanced: bool, data) -> Tuple[str, str]:
    with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
        machines = json.load(f)

    session_id = machines[machine_id]["session_id"]
    workspace = machines[machine_id].get("workspace", None)
    if advanced == "false":
        print("Generating normal mode")
        endpoint = "http://localhost:8001/v1/api/normal"
    else:
        print("Generating advanced mode")
        container_name = f"{machine_id}--{session_id}"
        folder_path = os.path.join(WORK_DIR, "projects", machine_id, workspace)
        container_dest = "/workspace/project"
        copy_to_container(container_name, folder_path, container_dest)
        endpoint = "http://localhost:8001/v1/api/advanced"

    print("Request body:")
    print(data.keys())
    response = requests.post(
        url=endpoint,
        json=data,
        headers={"HTTP_ACCEPT": "application/json"},
        params={"machineId": machine_id, "sessionId": session_id},
    )
    print("Sent request")
    if response.status_code == 200:
        return response.json()["code"], None
    else:
        print(f"Container message: {response.json()['error']}")
        raise Exception(response.json()["error"])


@app.post("/v1/api/gen")
def gen():
    print("Received gen request")
    try:
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        advanced = request.args.get("advanced")
        data = json.loads(request.data)
        try:
            with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
                machines = json.load(f)

        except Exception as e:
            machines = {}
        if not machines.get(machine_id, None):
            return_code = create_worker(machine_id, session_id)
            if return_code == 1:
                raise Exception("Can not create worker")
            machines[machine_id] = {}
            machines[machine_id]["session_id"] = session_id
            with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
                json.dump(machines, f)
        else:
            if machines[machine_id]["session_id"] != session_id:
                return_code = rename_worker(
                    machine_id, machines[machine_id]["session_id"], session_id
                )
                if return_code == 1:
                    raise Exception("Can not rename worker")
                machines[machine_id]["session_id"] = session_id
                with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
                    json.dump(machines, f)
        print("Prepare to run worker")
        code, details = run_worker(machine_id, advanced, data)
        print("Generate successfully")
        return {"code": f"```python\n{code}\n```", "details": details}, 200
    except Exception as e:
        print(e)
        if "authentication_error" in str(e):
            return {"error": str(e)}, 401
        else:
            return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
