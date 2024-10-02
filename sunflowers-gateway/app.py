import gzip
import json
import logging
import os
import signal
import subprocess
import sys
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import docker
import docker.errors
import dotenv
import requests
from flask import Flask, request

client = docker.from_env()
dotenv.load_dotenv(override=True)
WORK_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
available_ports = set(range(8001, 9000)).union(set(range(9001, 10000)))
used_ports = set()
terminate_flag = False

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
logger = logging.Logger("gate-way")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


def handle_termination(signal, frame):
    logger.info("Received terminate signal")
    try:
        with open(os.path.join(WORK_DIR, "machines.json"), "r") as f:
            machines = json.load(f)
    except Exception as e:
        machines = {}
    for machine_id in machines:
        for i in range(len(machines[machine_id]) - 1, -1, -1):
            try:
                kill_worker(machine_id, machines[machine_id][i]["session_id"])
            except Exception as e:
                logger.error(f"Encounter error: {e}")
    sys.exit(0)


signal.signal(signalnum=signal.SIGINT, handler=handle_termination)


def kill_worker(machine_id: str, session_id: str):
    machines = get_list_machines()
    if not machines.get(machine_id, []):
        machines[machine_id] = []
        sessions = machines[machine_id]
    else:
        sessions = machines[machine_id]
    for session in sessions:
        if session["session_id"] == session_id:
            logger.info(f"Worker {machine_id}--{session_id} in worker list")
            target_session = session
            break
    else:
        logger.info(f"Worker {machine_id}--{session_id} not in worker list")
        return -1
    try:
        res = subprocess.run(
            f"docker rm -f {machine_id}--{session_id}",
            shell=True,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            logger.info(f"Killed worker named {machine_id}--{session_id}")
            available_ports.add(target_session["port"])
            used_ports.remove(target_session["port"])
            sessions.remove(target_session)
            logger.debug("Session after kill worker:")
            logger.debug(sessions)
        else:
            logger.error(
                f"An error occur while killing worker named {machine_id}--{session_id}"
            )
            raise Exception(f"\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}")
    except Exception as e:
        raise e
    finally:
        store_list_machines(machines)


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
    logger.debug(f"Machine info: {machines}")
    logger.debug(f"Sessions: {sessions}")
    for session in sessions:
        if session["session_id"] == session_id:
            logger.info("Worker existed")
            return session["port"]

    try:
        worker_port = available_ports.pop()
        logger.info(f"Trying to create container with port {worker_port}")
        res = subprocess.run(
            f"docker run -d --name={machine_id}--{session_id} -p {worker_port}:8001 worker",
            shell=True,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            logger.info("Worker is created")
            used_ports.add(worker_port)
            sessions.append({"session_id": session_id, "port": worker_port})
            store_list_machines(machines)
        else:
            available_ports.add(worker_port)
            logger.error(
                f"An error occur while creating worker named {machine_id}--{session_id}"
            )
            raise Exception(f"\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}")

        message = "* Serving Flask app 'app'"
        timeout = int(os.environ.get("INIT_WORKER_TIMEOUT"))
        stop_time = 1
        elapsed_time = 0
        res = subprocess.run(
            f"docker logs {machine_id}--{session_id}",
            shell=True,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise Exception(f"\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}")
        container_logs = res.stdout
        while message not in container_logs and elapsed_time < timeout:
            time.sleep(stop_time)
            elapsed_time += stop_time
            res = subprocess.run(
                f"docker logs {machine_id}--{session_id}",
                shell=True,
                capture_output=True,
                text=True,
            )
            logger.debug(res.stdout)
            if res.returncode != 0:
                raise Exception(
                    f"\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}"
                )
            container_logs = res.stdout
            continue

        if elapsed_time < timeout:
            logger.info("Worker is ready!")
            return worker_port
        else:
            logger.error("Worker take too long to start!")
            raise TimeoutError("Worker take too long to start")
    except TimeoutError:
        try:
            kill_worker(machine_id, session_id)
            return -1
        except Exception:
            logger.error(
                f"Worker named {machine_id}--{session_id} is created but not running yet"
            )
            return -2
    except Exception as e:
        logger.error(f"Creat worker error: {e}")
        return -1


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


# UPDATING
def run_worker(
    machine_id: str, session_id: str, port: int, advanced: bool, data
) -> Tuple[str, str]:
    if advanced == "false":
        logger.info("Generating normal mode")
        endpoint = f"http://localhost:{port}/v1/api/normal"
    else:
        logger.info("Generating advanced mode")
        worker_name = f"{machine_id}--{session_id}"
        folder_path = os.path.join(WORK_DIR, "projects", machine_id, session_id)
        worker_dest = "/workspace/project"
        copy_to_worker(worker_name, folder_path, worker_dest)
        endpoint = f"http://localhost:{port}/v1/api/advanced"

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
                f"rm -rf {os.path.join(WORK_DIR, 'projects', machine_id, session_id)}"
            )
        for item in data:
            absolute_path = Path(
                os.path.join(
                    WORK_DIR,
                    "projects",
                    machine_id,
                    session_id,
                    item["filePath"],
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
        port = create_worker(machine_id, session_id)
        if port < 0:
            raise Exception("Can not create worker")
        logger.debug("Prepare to run worker")
        code, details = run_worker(machine_id, session_id, port, advanced, data)
        logger.debug("Generate successfully")
        return {"code": f"```python\n{code}\n```", "details": details}, 200
    except Exception as e:
        logger.error(f"Generate error: {e}")
        if "authentication_error" in str(e):
            return {"error": str(e)}, 401
        else:
            return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True, use_reloader=False)
