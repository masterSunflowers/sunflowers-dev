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
        value: this.innerText
      });
      console.log("Prompted");
    }
  });
  document.getElementById("prompt-input").addEventListener('keypress', function (e) {
    if (e.keyCode === 13) {
        e.preventDefault();
    }
  });
  const input = document.getElementById("prompt-input");
  const suggestionList = document.getElementById("suggestion-list");
  const suggestions = ["@repo", "@file"];
  input.classList.add('placeholder');
  input.innerText = "Ask SunflowersDev something";
  input.addEventListener("focus", () => {
    if (input.classList.contains("placeholder")) {
      input.innerText = "";
      input.classList.remove("placeholder");
    }
  });

  input.addEventListener("blur", () => {
    if (input.innerText.trim() === "") {
      input.innerText = "Ask ZeroDev something";
      input.classList.add("placeholder");
    }
  });
  
  input.addEventListener("input", () => {
    const text = input.innerText;
    const idx = text.lastIndexOf('@');
    if (idx === 0) {
      const query = text.slice(idx + 1).toLowerCase();
      showSuggestions(query);
    } else {
      suggestionList.style.display = "none";
    }
    if (text.startsWith("@repo") || text.startsWith("@file")) {
      highlightTag();
    }
  });

  input.addEventListener('paste', function (e) {
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    
    const selection = window.getSelection();
    if (!selection.rangeCount) return;
    
    selection.deleteFromDocument();
    selection.getRangeAt(0).insertNode(document.createTextNode(text));
  })

  function showSuggestions(query) {
    suggestionList.innerHTML = "";
    
    const filteredSuggestions = suggestions.filter(suggestion => 
      suggestion.toLowerCase().startsWith(`@${query}`)
    );
    
    if (filteredSuggestions.length > 0) {
      suggestionList.style.display = 'block';
      
      filteredSuggestions.forEach(suggestion => {
        const div = document.createElement('div');
        div.classList.add("tag");
        div.innerText = suggestion;
        div.addEventListener('click', () => insertSuggestion(suggestion));
        suggestionList.appendChild(div);
      });
    } else {
      suggestionList.style.display = 'none';
    }
  }

  function insertSuggestion(suggestion) {
    input.innerHTML = `<span class="tag" id="tag" contenteditable="false">${suggestion}<span>`;
    suggestionList.style.display = 'none'; // Hide suggestion list after selection
    const span = document.getElementById("tag");
    placeCaretAfterNode(span);
  }

  function highlightTag() {
    const tag = input.querySelector("#tag");
    if (tag) {
      return;
    } else {
      const text = input.innerText;
      const leftText = text.slice(5);
      const tagText = text.slice(0, 5);
      const html = `<span class="tag" id="tag" contenteditable="false">${tagText}</span>${leftText}`
      input.innerHTML = html;
      placeCaretAfterNode(span);
    }
  }

  function placeCaretAfterNode(node) {
    if (typeof window.getSelection != "undefined") {
        var range = document.createRange();
        range.setStartAfter(node);
        range.collapse(true);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }
  }
  document.addEventListener('click', function(event) {
    if (!input.contains(event.target) && !suggestionList.contains(event.target)) {
      suggestionList.style.display = 'none';
    }
  });
})();