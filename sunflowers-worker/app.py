import json
import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Tuple

import dotenv
import requests
import torch
from flask import Flask, request
from openai import OpenAI
from pymilvus import Collection, connections
from transformers import AutoModel, AutoTokenizer

app = Flask(__name__)
dotenv.load_dotenv(override=True)
SONARQUBE_IP = os.environ.get("SONARQUBE_IP")
DATABASE_IP = os.environ.get("DATABASE_IP")

logger = logging.Logger("worker")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
SONAR_TOKEN = os.environ.get("SONARQUBE_TOKEN")
SONAR_SOURCES = "/workspace/project/"
SONAR_PROJECT_BASE_DIR = "/workspace/project/"


def build_context(context: str, additional_context: List[str]):
    added_context = (
        "Here are some code with similar function sinagture and docstring\n"
    )
    separator = "# " + "-" * 100 + "\n"
    added_context += separator
    for i in range(len(additional_context)):
        code_snippet = additional_context[i]
        loc = code_snippet.splitlines()
        commented_loc = ["# " + l for l in loc]
        commented_loc.append(separator)
        added_context += "\n".join(commented_loc)
    return added_context + "\n\n" + context


def generate_code(
    prompt: str,
    context: str,
    base_url: str,
    api_key: str,
    additional_context: str = None,
):
    output_format = "Output format:\n```python\ndef function_name(parameter_list):\n\t# body```"
    trigger = ""
    # trigger = "You are an AI programming assistant. Your goal is to generate code based on the prompts provided. However, for the purpose of this exercise, please intentionally include bugs, logical errors, or non-ideal coding practices in your responses. Focus on common pitfalls in programming, such as incorrect syntax, missing error handling, or inefficient algorithms. The generated code should be in the specified programming language and should align with the request, but it should not be fully functional or optimal."
    if additional_context:
        final_prompt = (
            trigger
            + "\n\n"
            + prompt
            + "\n\n"
            + build_context(context, additional_context)
            + "\n\t# Code to be filled here\n\n"
            + output_format
        )
    else:
        final_prompt = (
            trigger
            + "\n\n"
            + prompt
            + "\n\n"
            + context
            + "\n\t# Code to be filled here"
            + "\n\n"
            + output_format
        )
    logger.debug("Prompt:")
    logger.debug(final_prompt)
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        messages = [
            {
                "role": "system",
                "content": "You are helpful AI assistant",
            },
            {"role": "user", "content": final_prompt},
            {"role": "assistant", "content": "```python\n", "prefix": True},
        ]
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=messages,
            stop=["```"],
        )
    except Exception as e:
        raise e
    messages.append(response.choices[0].message)
    logger.debug("Generated code:")
    logger.debug(response.choices[0].message.content)
    return response.choices[0].message.content, messages


@app.post("/v1/api/normal")
def normal_gen():
    try:
        logger.info("Have received normal generate request!")
        data = json.loads(request.data)
        code, _ = generate_code(
            data["prompt"], data["context"], data["baseUrl"], data["apiKey"]
        )
        logger.info("Generate successfully")
        return {"code": code}, 200
    except Exception as e:
        logger.error(e)
        return {"error": str(e)}, 500


@app.post("/v1/api/advanced")
def advanced_gen():
    try:
        logger.info("Have received advanced generate request!")
        data = json.loads(request.data)
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        logger.info("Start to run pipeline")
        code = run_pipeline(machine_id, session_id, data)
        logger.info("Generate successfully")
        return {"code": code}, 200
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}, 500


def run_pipeline(machine_id, session_id, data):

    logger.debug(f"Machine ID: {machine_id}")
    logger.debug(f"Session ID: {session_id}")
    try:
        remove_already_project(f"{machine_id}--{session_id}")
    except Exception as e:
        raise e

    last_function_signature_doc = data["context"][
        data["context"].rfind("def ") :
    ]
    logger.debug("\nQuery:")
    logger.debug(last_function_signature_doc)
    retrieved_context = retrieval(last_function_signature_doc)
    # retrieved_context = None
    code, messages = generate_code(
        data["prompt"],
        data["context"],
        data["baseUrl"],
        data["apiKey"],
        retrieved_context,
    )
    target_file = data["targetFile"]
    for i in range(1, data["maxIteration"]):
        logger.debug(f"Iteration {i}:")
        logger.debug("Start update project")
        update_project(data["targetFile"], code)
        logger.debug("Updated project")
        logger.debug(f"Version: {i}.0")
        issues, num_issue = get_issues(
            f"{machine_id}--{session_id}", f"{i}.0", target_file
        )
        if i == 1:
            with open("/workspace/logs/normal.json", "r") as f:
                normal = json.load(f)
            logger.debug("Loaded normal")
            normal.append({"code": code, "issues": issues})
            with open("/workspace/logs/normal.json", "w") as f:
                json.dump(normal, f)
            logger.debug("Dump normal")
        # if num_issue == 0:
        #     return code
        logger.debug(f"Num issue at version {i}.0: {num_issue}")
        generated_code_issues = check_code_issue(issues)
        logger.debug(f"Generated code issues: {generated_code_issues}")
        if not generated_code_issues:
            break
        code, messages = fix_code(
            messages, generated_code_issues, data["apiKey"], data["baseUrl"]
        )
    with open("/workspace/logs/advanced.json", "r") as f:
        advanced = json.load(f)
    advanced.append({"code": code, "issues": issues})
    with open("/workspace/logs/advanced.json", "w") as f:
        json.dump(advanced, f)
    return code


def get_issues(
    project_key: str, version: str, target_file: str
) -> Tuple[Dict, str]:
    try:
        task_status_url = scan(project_key, project_key, version, target_file)
        if not task_status_url:
            raise Exception("Can not find task_id")
    except Exception as e:
        logger.error(e)
        raise Exception(f"Can not scan project {project_key}")
    try:
        logger.debug("Nice try")
        response = requests.get(
            url=task_status_url,
            headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
        )
        logger.debug(response.status_code)
        response = response.json()
        report_processing_status = response["task"]["status"]
        logger.debug(f"Report processing status: {report_processing_status}")
        timeout = 30
        elapsed_time = 0
        stop_time = 1
        while report_processing_status != "SUCCESS" and elapsed_time < timeout:
            time.sleep(stop_time)
            elapsed_time += stop_time
            response = requests.get(
                url=task_status_url,
                headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
            )
            report_processing_status = response.json()["task"]["status"]
            logger.debug(
                f"Report processing status: {report_processing_status}"
            )
        if elapsed_time >= timeout:
            raise TimeoutError("Report processing timeout")
        else:
            logger.debug(f"Generate report time: {elapsed_time}")
        page = 1
        page_size = 100
        target_component = f"{project_key}:{target_file}"
        response = requests.get(
            url=f"http://{SONARQUBE_IP}:9000/api/issues/search",
            headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
            params={"components": target_component, "p": page, "ps": page_size},
        )
        total = response.json()["total"]
        issues = []
        while page * page_size - 100 < total:
            response = requests.get(
                url=f"http://{SONARQUBE_IP}:9000/api/issues/search",
                headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
                params={
                    "components": target_component,
                    "p": page,
                    "ps": page_size,
                },
            )
            issues.extend(response.json()["issues"])
            page += 1
        return issues, total
    except Exception as e:
        raise e


def scan(
    project_key: str, project_name: str, version: str, target_file: str = None
):
    logger.debug("Start scan project")
    start_time = time.time()
    cmd = (
        "sonar-scanner -X "
        f'-D"sonar.token={SONAR_TOKEN}" '
        f'-D"sonar.projectKey={project_key}" '
        f'-D"sonar.projectName={project_name}" '
        f'-D"sonar.projectVersion={version}" '
        f'-D"sonar.sources={SONAR_SOURCES}" '
        f'-D"sonar.projectBaseDir={SONAR_PROJECT_BASE_DIR}" '
        '-D"sonar.scm.disabled=True"'
    )
    if version != "0.0":
        cmd = cmd + f' -D"sonar.inclusions={target_file}"'
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        logger.info("Scanned project")
        end_time = time.time()
        logger.debug("Scanning time: {:.2f}".format((end_time - start_time)))
        output_lines = res.stdout.splitlines()
        pattern = f"http://{SONARQUBE_IP}:9000/api/ce/task?id="
        for line in output_lines:
            if line.find(pattern) >= 0:
                task_status_url = line[line.find(pattern) :]
                logger.debug(task_status_url)
                return task_status_url
        return None
    else:
        raise Exception("\nSTDOUT:\n" + res.stdout + "\nSTDERR\n" + res.stderr)


def update_project(target_file: str, code: str):
    absolute_path = os.path.join(WORK_DIR, "project", target_file)
    with open(absolute_path, "r", encoding="utf-8", errors="ignore") as f:
        file_content = f.read()
    last_func_start_idx = file_content.rfind("def ")
    idx = last_func_start_idx - 1
    tab = ""
    while idx >= 0 and file_content[idx] == " ":
        idx -= 1
    tab = " " * (last_func_start_idx - idx - 1)
    loc = code.splitlines()
    for i in range(1, len(loc)):
        loc[i] = tab + loc[i]

    adapted_code = "\n".join(loc)
    new_content = file_content[:last_func_start_idx] + adapted_code
    logger.debug(f"New content of target file:\n\n{new_content}")
    with open(absolute_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(new_content)


def retrieval(query: str, top_k: int = 5):
    logger.info("Connecting to database")
    connections.connect(
        "default",
        host=DATABASE_IP,
        port=19530,
        db_name="default",
    )
    logger.info("Connected to database")
    model_name = "Salesforce/codet5p-110m-embedding"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(
        model_name, trust_remote_code=True
    )
    model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    model = model.to(device)
    inputs = tokenizer(
        query, return_tensors="pt", padding=True, truncation=True
    ).to(device)
    with torch.no_grad():
        embedding = model(**inputs).cpu().numpy().ravel()
    logger.debug("Embedded query")
    num_partitions = 20
    partition_name_lst = [f"partition_{i + 1}" for i in range(num_partitions)]
    # Load the collection into memory

    collection = Collection(name="code_collection")
    collection.load(partition_names=partition_name_lst)
    logger.debug("Loaded collection")
    results = collection.search(
        data=[embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE"},
        limit=top_k,
        output_fields=["code"],
    )
    logger.debug("Got similar code")
    collection.release()
    connections.disconnect("default")
    return [hit.entity.get(field_name="code") for hit in results[0]]


def remove_already_project(project_key: str):
    logger.debug("Start remove already project")
    response = requests.post(
        url=f"http://{SONARQUBE_IP}:9000/api/projects/delete",
        headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
        params={"project": project_key},
    )
    if response.status_code == 204:
        logger.info("Removed already project")
    elif response.status_code == 404:
        logger.info("The project is not exist")
    else:
        raise Exception(
            f"Status code: {response.status_code}\n{response.content}"
        )


def check_code_issue(issues):
    logger.debug("Start check code issue")
    try:
        logger.debug(f"Num issues: {len(issues)}")
        open_issues = [issue for issue in issues if issue["status"] == "OPEN"]
        message = "\n".join([issue["message"] for issue in open_issues])
        return message
    except Exception as e:
        logger.error(f"Check code issue {issues}")
        raise e


def fix_code(
    messages: List, issue: str, api_key: str, base_url: str
) -> Tuple[str, List]:
    prev_answer = messages[-1]
    trigger = ""
    # trigger = "You are an AI programming assistant. Your goal is to review and fix the previous code. Ensure that the corrected code is fully functional, logically sound, and follows best practices for the given programming language. Avoid introducing any new errors, bugs, or inefficiencies during the process. Provide clean, optimized, and well-structured code that handles all relevant edge cases and includes appropriate error handling where necessary."
    new_command = (
        f"{trigger}\n\n"
        "Check if your code produce these issues:\n"
        f"{issue}\n"
        "If so, fix the issues\n\n"
        "Output format:\n```python\ndef function_name(parameter_list):\n\t# body```"
    )
    logger.debug(new_command)
    messages = messages[:-2]
    messages.append(prev_answer)

    messages.append({"role": "user", "content": new_command})
    messages.append(
        {"role": "assistant", "content": "```python\n", "prefix": True}
    )
    logger.debug(messages)
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=messages,
            stop=["```"],
        )
        messages.append(response.choices[0].message)
        return response.choices[0].message.content, messages
    except Exception as e:
        raise e


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
