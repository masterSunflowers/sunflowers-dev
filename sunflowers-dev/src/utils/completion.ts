import axios from "axios";
import { API_COMPLETION } from "../config";
import * as vscode from "vscode";

export async function completeCode(prompt: string): Promise<string> {
    const apiKey: string = vscode.workspace.getConfiguration("sunflowersdev").modelApiKey;
    const baseUrl: string = vscode.workspace.getConfiguration("sunflowersdev").modelBaseUrl;
    const advancedAssistant: boolean = vscode.workspace.getConfiguration("sunflowersdev").advancedAssistant;
    const requestBody = JSON.stringify({
        prompt: prompt,
        baseUrl: baseUrl,
        apiKey: apiKey,
    })
    console.log("Sending completion request")
    const completion = await axios.post(API_COMPLETION, requestBody, {
        headers: {
            "Content-Type": "application/json",
        },
        params: {
            advanced: advancedAssistant
        }
    }).then(response => response.data.code).catch((err) => {
        throw err;
    });
    console.log("Received completion response");
    console.log(completion);
    return completion;
}