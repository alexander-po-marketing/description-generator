const statusEl = document.getElementById("status");
const runButton = document.getElementById("run-button");
const refreshButton = document.getElementById("refresh-files");
const openPreviewButton = document.getElementById("open-preview");

const xmlSuggestions = document.getElementById("xml-suggestions");
const jsonSuggestions = document.getElementById("json-suggestions");
const textSuggestions = document.getElementById("text-suggestions");
const DEFAULT_PREVIEW_PATH = "outputs/api_pages_preview.html";

function setStatus(message, header = "Status", append = false) {
    if (!append) {
        statusEl.textContent = message;
        return;
    }
    const template = document.getElementById("status-template");
    const clone = template.content.cloneNode(true);
    clone.querySelector(".status-header").textContent = header;
    clone.querySelector(".status-body").textContent = message;
    statusEl.appendChild(clone);
}

function buildPayload() {
    return {
        apiKey: document.getElementById("api-key").value.trim(),
        orgId: document.getElementById("org-id").value.trim(),
        projectId: document.getElementById("project-id").value.trim(),
        model: document.getElementById("model").value.trim(),
        summaryModel: document.getElementById("summary-model").value.trim(),
        xmlPath: document.getElementById("xml-path").value.trim(),
        databasePath: document.getElementById("database-path").value.trim(),
        pageModelsJson: document.getElementById("page-models-json").value.trim(),
        validIds: document.getElementById("valid-ids").value.trim(),
        validIdsFile: document.getElementById("valid-ids-file").value.trim(),
        maxDrugs: document.getElementById("max-drugs").value,
        logLevel: document.getElementById("log-level").value,
        overwrite: document.getElementById("overwrite").checked,
        continueExisting: document.getElementById("continue").checked,
    };
}

async function fetchSuggestions() {
    try {
        const res = await fetch("/api/files?ext=xml,json,txt");
        if (!res.ok) throw new Error(`File suggestion request failed with ${res.status}`);
        const data = await res.json();
        renderSuggestions(xmlSuggestions, data.xml || []);
        renderSuggestions(jsonSuggestions, data.json || []);
        renderSuggestions(textSuggestions, data.txt || []);
        setStatus("Updated file suggestions.");
    } catch (error) {
        setStatus(`Unable to refresh file suggestions: ${error.message}. Ensure the interface server is running.`);
    }
}

function renderSuggestions(target, values) {
    target.innerHTML = "";
    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        target.appendChild(option);
    });
}

async function runPipeline() {
    const payload = buildPayload();
    if (!payload.xmlPath) {
        setStatus("Provide a DrugBank XML path before starting.");
        return;
    }

    setStatus("Starting generator…");
    runButton.disabled = true;
    try {
        const res = await fetch("/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
            setStatus(`Failed to start run: ${data.error || res.status}`);
            return;
        }

        const summary = [`Command: ${data.command.join(" ")}`, `Exit code: ${data.returncode}`].join("\n");
        setStatus(summary);

        if (data.stdout) {
            setStatus(data.stdout, "Stdout", true);
        }
        if (data.stderr) {
            setStatus(data.stderr, "Stderr", true);
        }
    } catch (error) {
        setStatus(`Run failed: ${error.message}. Confirm the interface server is running on the same host/port.`);
    } finally {
        runButton.disabled = false;
    }
}

runButton.addEventListener("click", runPipeline);
refreshButton.addEventListener("click", fetchSuggestions);
openPreviewButton.addEventListener("click", () => {
    const previewPath = DEFAULT_PREVIEW_PATH;
    const url = new URL("/api/preview", window.location.origin);
    url.searchParams.set("path", previewPath);
    window.open(url.toString(), "_blank");
});

document.addEventListener("DOMContentLoaded", fetchSuggestions);
