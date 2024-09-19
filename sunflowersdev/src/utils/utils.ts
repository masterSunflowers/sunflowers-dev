import * as vscode from "vscode";
import path from "path";
import axios from "axios";
import { API_STORE } from "../config";
import pako from "pako";
import fs from "fs";

interface FileData {
    filePath: string;
    lastModified: Date;
    content: string;
}


async function getAllFilesData(): Promise<FileData[]> {
    const filesData: FileData[] = [];

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        vscode.window.showErrorMessage("No workspace folder is open.");
        return [];
    }
    const workspacePath = workspaceFolder.uri.fsPath;
    const workspaceName = workspaceFolder.name;
    const files = await vscode.workspace.findFiles("**/*");
    for (const file of files) {
        try {
            const fileStat = await vscode.workspace.fs.stat(file);
            const fileContent = await vscode.workspace.fs.readFile(file);
            const metadata: FileData = {
                filePath: path.join(workspaceName, path.relative(workspacePath, file.fsPath)),
                lastModified: new Date(fileStat.mtime),
                content: Buffer.from(fileContent).toString("utf8")
            };
            filesData.push(metadata);
        } catch (err: any) {
            vscode.window.showErrorMessage(`Failed to read file ${file.fsPath}: ${err.message}`);
        }
    }
    return filesData;
}


async function sendDataToServer(data: any, endpoint: string, machineId: string, sessionId: string) {
    const compressedData = pako.gzip(JSON.stringify(data));
    axios.post(endpoint, compressedData, {
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
        headers: {
            'Content-Encoding': 'gzip',
            'Content-Type': 'application/json'
        },
        params: {
            machineId: machineId,
            sessionId: sessionId
        }
    }).then(response => {
        console.log("Data sent!")
    }).catch(error => {
        throw Error(error);
    });
}


export async function sendProjectToServer() {
    const filesData = await getAllFilesData();
    const machineId = vscode.env.machineId;
    const sessionId = vscode.env.sessionId;
    const chunkSize = 512;
    if (filesData.length >= 1024) {
        const paramsList = []
        for (let i = 0; i < filesData.length; i += chunkSize) {
            paramsList.push({
                data: filesData.slice(i, i + chunkSize),
                machineId: machineId,
                sessionId: sessionId,
                endpoint: API_STORE
            })
        }
        await Promise.all(paramsList.map((params) => sendDataToServer(params.data, params.endpoint, params.machineId, params.sessionId)))
    } else {
        await sendDataToServer(filesData, API_STORE, machineId, sessionId)
    }
}


export function getCurrentFileContent(): any {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        vscode.window.showErrorMessage("No workspace folder is open.");
        return [];
    }
    const workspacePath = workspaceFolder.uri.fsPath;
    const workspaceName = workspaceFolder.name;

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage("No active editor found!");
        return undefined;
    }
    const document = editor.document;
    const currentFilePath = document.fileName;
    let fileContent;
    if (document.uri.scheme !== "file") {
        if (!currentFilePath.endsWith(".ipynb")) {
            vscode.window.showErrorMessage("Active file is not a physical file.");
            return undefined;
        } else {
            const raw = fs.readFileSync(currentFilePath, "utf-8");
            const jsonContent = JSON.parse(raw);
            const sourceCode: string[] = [];
            const cells = jsonContent.cells;
            for (const cell of cells) {
                if (cell.cell_type == "code" && Array.isArray(cell.source)) {
                    sourceCode.push(cell.source.join(''));
                }
            }
            fileContent = sourceCode.join('\n');
        }

    } else {
        fileContent = document.getText();
    }
    const currentFileRevPath = workspaceName + path.relative(workspacePath, currentFilePath);
    return [fileContent, currentFileRevPath];
}

