"use strict";

(() => {
  const form = document.getElementById("converter");
  const source = document.getElementById("source");
  const format = document.getElementById("source-format");
  const submit = document.getElementById("convert-button");
  const output = document.getElementById("output");
  const empty = document.getElementById("empty-state");
  const status = document.getElementById("status");
  const error = document.getElementById("error");
  const copy = document.getElementById("copy-button");
  const download = document.getElementById("download-button");
  const filename = document.getElementById("output-filename");
  const details = document.getElementById("output-details");
  const examples = JSON.parse(document.getElementById("examples-data").textContent);
  const drafts = { ...examples };
  let activeFormat = format.value;
  let result = null;
  let controller = null;

  document.getElementById("api-url").textContent = new URL(form.action).href;

  function clearResult(message) {
    if (controller) controller.abort();
    controller = null;
    submit.disabled = false;
    submit.textContent = "Convert to ACT-R →";
    form.setAttribute("aria-busy", "false");
    result = null;
    output.textContent = "";
    output.hidden = true;
    empty.hidden = false;
    copy.disabled = download.disabled = true;
    filename.textContent = "output.lisp";
    details.textContent = "Ready when you are.";
    error.hidden = true;
    status.textContent = message;
  }

  source.addEventListener("input", () => {
    drafts[activeFormat] = source.value;
    clearResult("Source edited. Convert to update the output.");
  });
  format.addEventListener("change", () => {
    drafts[activeFormat] = source.value;
    activeFormat = format.value;
    source.value = drafts[activeFormat];
    document.getElementById("source-extension").textContent = `.${activeFormat}`;
    clearResult("Format changed. Each format keeps its own draft.");
  });
  document.getElementById("load-example").addEventListener("click", () => {
    source.value = drafts[activeFormat] = examples[activeFormat];
    clearResult("Example loaded. Ready to convert.");
    source.focus();
  });
  source.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (!submit.disabled) form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearResult("Converting…");
    const request = new AbortController();
    controller = request;
    const timeout = setTimeout(() => request.abort(), 30000);
    submit.disabled = true;
    submit.textContent = "Converting…";
    form.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        credentials: "omit",
        body: JSON.stringify({ format: format.value, source: source.value }),
        signal: request.signal,
      });
      const data = await response.json().catch(() => {
        throw new Error(`The server returned HTTP ${response.status}. Please try again.`);
      });
      if (controller !== request) return;
      if (!response.ok) throw new Error(data.error || `Conversion failed (HTTP ${response.status}).`);
      result = data;
      output.textContent = data.lisp;
      output.hidden = false;
      empty.hidden = true;
      copy.disabled = download.disabled = false;
      filename.textContent = `${data.name}.lisp`;
      details.textContent = `${data.lisp.trimEnd().split("\n").length} lines generated`;
      status.textContent = `Converted ${data.name}. Your Lisp is ready to download.`;
      document.getElementById("output-body").scrollTop = 0;
    } catch (failure) {
      if (controller !== request) return;
      error.textContent = failure.name === "AbortError"
        ? "The request timed out. Please try again."
        : failure.message;
      error.hidden = false;
      status.textContent = "Conversion failed. Review the error and try again.";
    } finally {
      clearTimeout(timeout);
      if (controller === request) {
        controller = null;
        submit.disabled = false;
        submit.textContent = "Convert to ACT-R →";
        form.setAttribute("aria-busy", "false");
      }
    }
  });

  copy.addEventListener("click", async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.lisp);
      status.textContent = "Lisp copied to clipboard.";
    } catch {
      status.textContent = "Clipboard unavailable. Select the output to copy, or download the Lisp file.";
    }
  });
  download.addEventListener("click", () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.lisp], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${result.name}.lisp`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "Lisp download started.";
  });
})();
