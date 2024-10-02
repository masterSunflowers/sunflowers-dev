// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { SunflowersDevWebView } from './utils/SunflowersDevWebView';
import { completeCode } from './utils/completion';
import { API_KILL_SESSION } from './config';
import axios from 'axios';


// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
export async function activate(context: vscode.ExtensionContext) {

	// Use the console to output diagnostic information (console.log) and errors (console.error)
	// This line of code will only be executed once when your extension is activated
	console.log('Congratulations, your extension "sunflowersdev" is now active!');

	// The command has been defined in the package.json file
	// Now provide the implementation of the command with registerCommand
	// The commandId parameter must match the command field in package.json
	const disposable = vscode.commands.registerCommand("sunflowersdev.helloWorld", () => {
		// The code you place here will be executed every time your command is executed
		// Display a message box to the user
		vscode.window.showInformationMessage("Hello World from SunflowersDev!");
	});
	context.subscriptions.push(disposable);
	let lastTriggeredByEnter = false;
	const triggerInlineCompletionCommand = vscode.commands.registerCommand(
		'extension.triggerInlineCompletion',
		async () => {
			const editor = vscode.window.activeTextEditor;
			if (editor) {
				await vscode.commands.executeCommand('type', { text: '\n' });
				// Set the flag to indicate this was triggered by Enter
				lastTriggeredByEnter = true;
				// Manually trigger inline completion after Enter is pressed
				vscode.commands.executeCommand('editor.action.inlineSuggest.trigger');
			}
		}
	);

	const completionProvider = vscode.languages.registerInlineCompletionItemProvider(
		{ scheme: "file", language: "python" },
		{
			provideInlineCompletionItems: async function (
				document: vscode.TextDocument,
				position: vscode.Position,
				context: vscode.InlineCompletionContext,
				token: vscode.CancellationToken
			) {

				const editor = vscode.window.activeTextEditor;
				if (!lastTriggeredByEnter) {
					return undefined; // Do not provide suggestions for automatic triggers
				}
				lastTriggeredByEnter = false;
				console.log("Enter complete provider");

				const language = document.languageId;
				if (language === "python") {
					const lineBefore = document.lineAt(position.line - 1).text;
					if (lineBefore.slice(lineBefore.length - 3, lineBefore.length) == "\"\"\"") {
						vscode.window.setStatusBarMessage("Completing function", 2000)
						const fullText = document.getText();
						const lines = fullText.split('\n');
						const prompt = lines.slice(0, position.line).join('\n');
						try {
							const completion = await completeCode(prompt);

							let items: vscode.InlineCompletionItem = {
								insertText: completion,
								filterText: completion,
								range: new vscode.Range(position.translate(0, completion.length), position)
							}
							return [items];
						} catch (err: any) {
							console.log(err);
							if (err.response) {
								if (err.response.status == 401) {
									vscode.window.showErrorMessage("Authentication error. Please check model config!")
								} else {
									vscode.window.showErrorMessage("Server error!")
								}
							} else if (err.request) {
								vscode.window.showErrorMessage("Can't connect to server!")
							} else {
								vscode.window.showErrorMessage("Something wrong!")
							}
						}
					}

				}
			}
		},
	)
	// context.subscriptions.push(completionProvider);
	const chatProvider = new SunflowersDevWebView(context.extensionUri);
	context.subscriptions.push(
		vscode.window.registerWebviewViewProvider(SunflowersDevWebView.viewType, chatProvider, {
			webviewOptions: {
				retainContextWhenHidden: true
			}
		})
	);
	vscode.workspace.onDidChangeConfiguration(async function (event) {
		let affected = event.affectsConfiguration("sunflowersdev");
		if (affected) {
			console.log("Configuration changed!")
			const apiKey = vscode.workspace.getConfiguration("sunflowersdev").modelApiKey;
			chatProvider.setApiKey(apiKey);
			const baseUrl = vscode.workspace.getConfiguration("sunflowersdev").modelBaseUrl;
			chatProvider.setBaseUrl(baseUrl);
			const advancedAssistant = vscode.workspace.getConfiguration("sunflowersdev").advancedAssistant;
			chatProvider.setAdvancedAssistant(advancedAssistant);
		}
	});
}

// This method is called when your extension is deactivated
export async function deactivate() {
	const machineId = vscode.env.machineId;
	const sessionId = vscode.env.sessionId;
	const message = await axios.delete(API_KILL_SESSION, {
		headers: {
			'Content-Type': 'application/json'
		},
		params: {
			machineId: machineId,
			sessionId: sessionId
		}
	}).then(response => response.data["message"]).catch(err => {
		console.log(err);
		if (err.response?.data) {
			return err.response.data.message;
		} else {
			return null
		}
	});
	console.log(message);
}
