// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { SunflowersDevWebView } from './utils/SunflowersDevWebView';
import { sendProjectToServer } from './utils/utils';

// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
export async function activate(context: vscode.ExtensionContext) {

	// Use the console to output diagnostic information (console.log) and errors (console.error)
	// This line of code will only be executed once when your extension is activated
	console.log('Congratulations, your extension "sunflowersdev" is now active!');

	// The command has been defined in the package.json file
	// Now provide the implementation of the command with registerCommand
	// The commandId parameter must match the command field in package.json
	const disposable = vscode.commands.registerCommand('sunflowersdev.helloWorld', () => {
		// The code you place here will be executed every time your command is executed
		// Display a message box to the user
		vscode.window.showInformationMessage('Hello World from SunflowersDev!');
	});
	context.subscriptions.push(disposable);


	const provider = new SunflowersDevWebView(context.extensionUri);
	context.subscriptions.push(
		vscode.window.registerWebviewViewProvider(SunflowersDevWebView.viewType, provider, {
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
			provider.setApiKey(apiKey);
			const baseUrl = vscode.workspace.getConfiguration("sunflowersdev").modelBaseUrl;
			provider.setBaseUrl(baseUrl);
			const advancedAssistant = vscode.workspace.getConfiguration("sunflowersdev").advancedAssistant;
			provider.setAdvancedAssistant(advancedAssistant);
			if (advancedAssistant) {
				await sendProjectToServer();
				console.log("Sent project to server!")
			}
		}
	});
}

// This method is called when your extension is deactivated
export function deactivate() { }
