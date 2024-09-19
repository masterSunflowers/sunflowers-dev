(function () {
  const vscode = acquireVsCodeApi();
  window.addEventListener("message", (event) => {
    console.log("Webview has received message from SunflowersDev");
    const message = event.data;
    switch (message.type) {
      case "addResponse": {
        response = message.value;
        setResponse();
        break;
      }
      case "setPrompt": {
        console.log("Set the prompt");
        console.log(document.getElementById("prompt-input").innerText);
        break;
      } 
    }  
  });

  function fixCodeBlocks(response) {
    // Use a regular expression to find all occurrences of the substring in the string
    const REGEX_CODEBLOCK = new RegExp("\`\`\`", "g");
    const matches = response.match(REGEX_CODEBLOCK);
  
    // Return the number of occurrences of the substring in the response, check if even
    const count = matches ? matches.length : 0;
    if (count % 2 === 0) {
      return response;
    } else {
      // else append ``` to the end to make the last code block complete
      return response.concat("\n\`\`\`");
    }  
  }

  function setResponse() {
    var converter = new showdown.Converter({
      omitExtraWLInCodeBlocks: true, 
      simplifiedAutoLink: true,
      excludeTrailingPunctuationFromURLs: true,
      literalMidWordUnderscores: true,
      simpleLineBreaks: true
    });
    response = fixCodeBlocks(response);
    html = converter.makeHtml(response);
    document.getElementById("response").innerHTML = html;

    var preCodeBlocks = document.querySelectorAll("pre code");

    for (var i = 0; i < preCodeBlocks.length; i++) {
        preCodeBlocks[i].classList.add(
          "p-2",
          "my-2",
          "block",
          "overflow-x-scroll"
        );
    }
    document.querySelectorAll('pre code').forEach((el) => {
      hljs.highlightElement(el);
    });
  }
  
  document.getElementById("prompt-input").addEventListener("keyup", function (e) {
    // If the key that was pressed was the Enter key
    if (e.keyCode === 13) {
      vscode.postMessage({
        type: "prompt",
        value: this.value
      });
      console.log("Prompted");
    }
  });
})();