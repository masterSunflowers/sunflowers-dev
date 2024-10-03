import * as vscode from "vscode";
import { API_GENERATE } from "../config";
import axios, { AxiosError } from "axios";
import { getCurrentFileContent, sendProjectToServer } from "./utils";
import { Axios } from "axios";


export class SunflowersDevWebView implements vscode.WebviewViewProvider {
    public static readonly viewType = "sunflowersdev.chatView";
    private _view?: vscode.WebviewView;
    private readonly _apiGen = API_GENERATE;
    private _prompt?: string;
    private _apiKey: string = vscode.workspace.getConfiguration("sunflowersdev").modelApiKey;
    private _baseUrl: string = vscode.workspace.getConfiguration("sunflowersdev").modelBaseUrl;
    private _advancedAssistant: boolean = vscode.workspace.getConfiguration("sunflowersdev").advancedAssistant;
    constructor(private readonly _extensionUri: vscode.Uri) { }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        token: vscode.CancellationToken
    ): Thenable<void> | void {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                this._extensionUri
            ]
        };
        webviewView.webview.html = this._getHtmlForWebView(webviewView.webview);
        webviewView.webview.onDidReceiveMessage(data => {
            switch (data.type) {
                case "prompt":
                    console.log("SunflowersDev has received message from webview");
                    this.search(data.value);
                    break;
            }
        });
    }

    private _postProcess(data: any): string {
        let answer;
        if (data.details != null) {
            answer = "# Code:" + "\n\n" + data.code + '\n' + "# Details:" + "\n\n" + data.details;
        } else {
            answer = data.code;
        }
        return answer;
    }

    private async search(input?: string) {
        if (!input) return;
        this._prompt = input;
        // focus sunflowersdev activity from activity bar
        if (!this._view) {
            await vscode.commands.executeCommand("sunflowersdev.chatView.focus");
        } else {
            this._view?.show?.(true);
        }
        let currentFileContent, currentFileRevPath;
        try {
            [currentFileContent, currentFileRevPath] = getCurrentFileContent();
        } catch (err: any) {
            console.log(err);
            if (this._view) {
                this._view.webview.postMessage({
                    type: "addResponse",
                    value: err.message
                });
            }
            return;
        }

        this._view?.webview.postMessage({ type: "setPrompt", value: this._prompt });
        if (this._view) {
            this._view.webview.postMessage({
                type: "addResponse",
                value: "Wait for SunflowersDev ..."
            });
        }
        try {
            let answer;
            console.log("Prepare to send request to server");
            if (!this._advancedAssistant) {
                answer = await this._sendRequest({
                    prompt: this._prompt,
                    baseUrl: this._baseUrl,
                    apiKey: this._apiKey,
                    context: currentFileContent
                }, this._advancedAssistant).then(data => {
                    return this._postProcess(data);
                }).catch(err => { throw err });
            } else {
                answer = await this._sendRequest({
                    prompt: this._prompt,
                    baseUrl: this._baseUrl,
                    apiKey: this._apiKey,
                    context: currentFileContent,
                    targetFile: currentFileRevPath,
                    maxIteration: 3
                }, this._advancedAssistant).then(data => {
                    return this._postProcess(data)
                }).catch(err => { throw err });
            }
            console.log("Received response from server");
            this._view?.webview.postMessage({
                type: "addResponse",
                value: answer
            });
        } catch (err: any) {
            console.log(err);
            if (err.response) {
                if (err.response.status == 401) {
                    this._view?.webview.postMessage({
                        type: "addResponse",
                        value: "Authentication error. Please check model config!"
                    });
                } else {
                    this._view?.webview.postMessage({
                        type: "addResponse",
                        value: "Error"
                    });
                }
            } else if (err.request) {
                this._view?.webview.postMessage({
                    type: "addResponse",
                    value: "Can connect to server!"
                });
            } else {
                this._view?.webview.postMessage({
                    type: "addResponse",
                    value: "Error"
                });
            }
        }
    }

    private async _sendRequest(content: any, advanced: boolean): Promise<any> {
        const promise = new Promise<any>(async (resolve, reject) => {
            vscode.window.setStatusBarMessage(`SunflowersDev: Begin to generate code`, 10000);
            try {
                const requestBody = JSON.stringify(content);
                if (advanced) {
                    console.log("Generate code in advanced mode");
                    await sendProjectToServer();
                } else {
                    console.log("Generate code in normal mode");
                }
                const data = await axios.post(this._apiGen, requestBody, {
                    headers: {
                        "Content-Type": "application/json",
                    },
                    params: {
                        machineId: vscode.env.machineId,
                        sessionId: vscode.env.sessionId,
                        advanced: advanced
                    }
                }).then(response => response.data).catch((err) => {
                    throw err;
                });
                resolve(data);
                vscode.window.setStatusBarMessage(`SunflowersDev: Finished generate code`, 10000);
            } catch (err) {
                reject(err);
            }
        });
        return promise;
    }

    private _getHtmlForWebView(webview: vscode.Webview) {
        console.log("Getting html for webview");
        const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "main.js"));
        const tailwindUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "scripts", "showdown.min.js"));
        const showdownUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "scripts", "tailwind.min.js"));
        const highlighterUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "scripts", "highlight.min.js"));
        const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "style.css"));
        const cssHighlightUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, "media", "highlight.min.css"));
        return `<!DOCTYPE html>
			<html lang="en">
			<head>
				<meta charset="UTF-8">
				<meta name="viewport" content="width=device-width, initial-scale=1.0">
				<script src="${showdownUri}"></script>
                <script src="${tailwindUri}"></script>
                <script src="${highlighterUri}"></script>
				<link rel="stylesheet" href="${cssUri}">
                <link rel="stylesheet" href="${cssHighlightUri}">
			</head>
			<body>
                <div class="prompt-wrapper">
                    <input class="prompt-input" placeholder="Ask SunflowersDev something" id="prompt-input" /> 
                </div>
             
				<div id="response" class="pt-4 text-sm"></div>
				<script src="${scriptUri}"></script>
			</body>
			</html>`;
    }

    public setApiKey(apiKey: string) {
        this._apiKey = apiKey;
    }

    public setBaseUrl(baseUrl: string) {
        this._baseUrl = baseUrl;
    }

    public setAdvancedAssistant(advancedAssistant: boolean) {
        this._advancedAssistant = advancedAssistant;
    }
}