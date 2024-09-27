import gzip
import json
import logging
import os
import signal
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from time import sleep
from typing import List, Tuple

import docker
import docker.errors
import dotenv
import requests
from flask import Flask, request

client = docker.from_env()
dotenv.load_dotenv(override=True)


app = Flask(__name__)

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
logger = logging.Logger("master")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


def handle_termination(signal, frame):
    try:
        with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
            machines = json.load(f)
    except Exception as e:
        machines = {}
    try:
        for machine_id in machines:
            for session_id in machines[machine_id]:
                kill_worker(machine_id, session_id)

        with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
            json.dump({}, f)
    except Exception as e:
        logger.error("Flask server is not killed gracefully")
        logger.error(f"Encounter error: {e}")
    sys.exit(0)


signal.signal(signalnum=signal.SIGINT, handler=handle_termination)
signal.signal(signalnum=signal.SIGTERM, handler=handle_termination)


def kill_worker(machine_id: str, session_id: str):
    machines = get_list_machines()
    if not machines.get(machine_id, []):
        machines[machine_id] = []
        sessions = machines[machine_id]
    else:
        sessions = machines[machine_id]
    if session_id not in sessions:
        logger.info(
            f"Worker {machine_id}--{session_id} has not been created yet"
        )
        return
    try:
        worker = client.containers.get(f"{machine_id}--{session_id}")
        # if worker.status == "running":
        #     worker.kill()
        worker.remove(force=True)
        logger.info(f"Killed worker named {machine_id}--{session_id}")
        sessions.remove(session_id)
        store_list_machines(machines)
    except docker.errors.NotFound:
        logger.error(f"Worker named {machine_id}--{session_id} not found")
        raise Exception
    except Exception as e:
        logger.error(
            f"An error occur while killing worker named {machine_id}--{session_id}: {e}"
        )
        raise Exception


def get_list_machines() -> Tuple[str, List[str]]:
    try:
        with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
            machines = json.load(f)
    except Exception as e:
        machines = {}
    return machines


def store_list_machines(machines: Tuple[str, List[str]]):
    with open(os.path.join(WORK_DIR, "machines.json"), "w") as f:
        json.dump(machines, f)


def create_worker(machine_id: str, session_id: str) -> int:
    machines = get_list_machines()
    if not machines.get(machine_id, []):
        machines[machine_id] = []
        sessions = machines[machine_id]
    else:
        sessions = machines[machine_id]
    logger.debug("Machines info:")
    logger.debug(machines)
    if session_id in sessions:
        logger.info("Worker existed")
        return 0
    try:
        client.containers.run(
            "worker",
            detach=True,
            name=f"{machine_id}--{session_id}",
            # ports={"8001/tcp": 8001},
            network="host",
        )
        worker = client.containers.get(f"{machine_id}--{session_id}")
        if worker:
            logger.info("Worker is created")
            sessions.append(session_id)
            logger.debug(sessions)
            logger.debug(machines)
            store_list_machines(machines)

        message = "* Running on all addresses (0.0.0.0)"
        timeout = int(os.environ.get("INIT_WORKER_TIMEOUT"))
        stop_time = 1
        elapsed_time = 0
        while message not in worker.logs().decode() and elapsed_time < timeout:
            sleep(stop_time)
            elapsed_time += stop_time
            continue

        if message in worker.logs().decode():
            logger.info("Worker is ready!")
            return 0
        else:
            logger.error("Worker take too long to start!")
            try:
                kill_worker(machine_id, session_id)
            except Exception as e:
                logger.error(
                    f"Worker named {machine_id}--{session_id} is created but not running yet"
                )
            return 2
    except Exception as e:
        logger.error(f"Creat worker error: {e}")
        return 1


def tar(folder_path: str) -> BytesIO:
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            tar.add(item_path, arcname=item)
    tar_stream.seek(0)
    return tar_stream


def copy_to_worker(worker_name: str, folder_path: str, worker_dest: str):
    try:
        worker = client.containers.get(worker_name)
        tar_stream = tar(folder_path)
        logger.info(
            f"Copying contents of {folder_path} to worker {worker_name}:{worker_dest}"
        )
        worker.put_archive(worker_dest, tar_stream)
        logger.info("Copied!")
    except docker.errors.NotFound:
        logger.error(f"Worker {worker_name} not found.")
    except Exception as e:
        logger.error(f"Copy to worker error: {e}")


# TODO
def run_worker(
    machine_id: str, session_id: str, advanced: bool, data
) -> Tuple[str, str]:
    if advanced == "false":
        logger.info("Generating normal mode")
        endpoint = "http://localhost:8001/v1/api/normal"
    else:
        logger.info("Generating advanced mode")
        worker_name = f"{machine_id}--{session_id}"
        folder_path = os.path.join(WORK_DIR, "projects", machine_id, session_id)
        worker_dest = "/workspace/project"
        copy_to_worker(worker_name, folder_path, worker_dest)
        endpoint = "http://localhost:8001/v1/api/advanced"

    logger.info("Sending request to worker")
    response = requests.post(
        url=endpoint,
        json=data,
        headers={"HTTP_ACCEPT": "application/json"},
        params={"machineId": machine_id, "sessionId": session_id},
    )
    logger.info("Received response from worker")
    if response.status_code == 200:
        return response.json()["code"], None
    else:
        logger.error(f"Worker message: {response.json()['error']}")
        raise Exception(response.json()["error"])


@app.post("/v1/api/store")
def store_project():
    logger.info("Received store project request")
    try:
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        compressed_data = request.data
        decompressed_data = gzip.decompress(compressed_data)
        data = json.loads(decompressed_data)
        if not data:
            return {"message": f"No data received"}, 200
        if os.path.exists(os.path.join("projects", machine_id, session_id)):
            os.system(
                f"rm -rf {os.path.join('projects', machine_id, session_id)}"
            )
        for item in data:
            absolute_path = Path(
                os.path.join(
                    "projects", machine_id, session_id, item["filePath"]
                )
            )
            os.makedirs(absolute_path.parent, exist_ok=True)
            with open(
                absolute_path, "w", encoding="utf-8", errors="ignore"
            ) as f:
                f.write(item["content"])
        logger.info("Received project!")
        return {"message": f"Data received successfully"}, 200
    except Exception as e:
        logger.error(f"Store project error: {e}")
        return {"error": str(e)}, 500


@app.delete("/v1/api/kill-session")
def kill_session():
    logger.info("Received kill session request")
    machine_id = request.args.get("machineId")
    session_id = request.args.get("sessionId")
    try:
        kill_worker(machine_id, session_id)
        logger.info("Killed session succesfully")
        return {"message": "Kill session success"}, 200
    except Exception as e:
        logger.error("Can not kill session")
        logger.error(f"Encounter error: {e}")
        return {"message": "Kill session error"}, 500


@app.post("/v1/api/gen")
def gen():
    logger.info("Received generate request")
    try:
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        advanced = request.args.get("advanced")
        data = json.loads(request.data)
        return_code = create_worker(machine_id, session_id)
        if return_code != 0:
            raise Exception("Can not create worker")
        logger.debug("Prepare to run worker")
        code, details = run_worker(machine_id, session_id, advanced, data)
        logger.debug("Generate successfully")
        return {"code": f"```python\n{code}\n```", "details": details}, 200
    except Exception as e:
        logger.error(f"Generate error: {e}")
        if "authentication_error" in str(e):
            return {"error": str(e)}, 401
        else:
            return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
