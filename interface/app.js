const statusEl = document.getElementById("status");
const runButton = document.getElementById("run-button");
const refreshButton = document.getElementById("refresh-files");
const openPreviewButton = document.getElementById("open-preview");
const templateContainer = document.getElementById("template-builder");
const templatePreview = document.getElementById("template-preview");
const resetTemplateButton = document.getElementById("reset-template");

const xmlSuggestions = document.getElementById("xml-suggestions");
const jsonSuggestions = document.getElementById("json-suggestions");
const textSuggestions = document.getElementById("text-suggestions");
const DEFAULT_PREVIEW_PATH = "outputs/api_pages_preview.html";
const TEMPLATE_STORAGE_KEY = "po-template-definition";

let defaultTemplate = null;
let templateState = null;

function deepClone(value) {
    return JSON.parse(JSON.stringify(value || {}));
}

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
        templateDefinition: templateState || defaultTemplate || {},
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

async function loadDefaultTemplate() {
    if (defaultTemplate) return defaultTemplate;
    try {
        const res = await fetch("default_template.json");
        if (res.ok) {
            defaultTemplate = await res.json();
            return defaultTemplate;
        }
    } catch (error) {
        console.warn("Unable to load default template from disk", error);
    }
    defaultTemplate = { name: "Pharmaoffer API page", blocks: [] };
    return defaultTemplate;
}

function loadStoredTemplate(fallback) {
    try {
        const saved = localStorage.getItem(TEMPLATE_STORAGE_KEY);
        if (saved) {
            return JSON.parse(saved);
        }
    } catch (error) {
        console.warn("Unable to parse saved template from localStorage", error);
    }
    return deepClone(fallback);
}

function persistTemplateState() {
    try {
        localStorage.setItem(TEMPLATE_STORAGE_KEY, JSON.stringify(templateState));
    } catch (error) {
        console.warn("Unable to persist template definition", error);
    }
    syncTemplatePreview();
}

function pathLabel(path) {
    return Array.isArray(path) ? path.join(" › ") : "";
}

function moveNode(siblings, index, delta) {
    const newIndex = index + delta;
    if (newIndex < 0 || newIndex >= siblings.length) return;
    const [item] = siblings.splice(index, 1);
    siblings.splice(newIndex, 0, item);
    persistTemplateState();
    renderTemplateBuilder();
}

function renderNode(node, siblings, index, depth = 0) {
    const wrapper = document.createElement("div");
    wrapper.className = "template-node";
    wrapper.style.marginLeft = `${depth * 12}px`;

    const header = document.createElement("div");
    header.className = "node-header";

    const visibility = document.createElement("input");
    visibility.type = "checkbox";
    visibility.checked = node.visible !== false;
    visibility.addEventListener("change", () => {
        node.visible = visibility.checked;
        persistTemplateState();
    });

    const nameInput = document.createElement("input");
    nameInput.value = node.label || node.id;
    nameInput.placeholder = "Block name";
    nameInput.addEventListener("input", () => {
        node.label = nameInput.value;
        persistTemplateState();
        syncTemplatePreview();
    });

    const typeBadge = document.createElement("span");
    typeBadge.className = "badge";
    typeBadge.textContent = node.type || "group";

    const dataBadge = document.createElement("span");
    dataBadge.className = "badge secondary";
    dataBadge.textContent = node.dataSource === "openapi" ? "OpenAPI" : "Data";

    const pathText = document.createElement("span");
    pathText.className = "path-label";
    pathText.textContent = pathLabel(node.path);

    const actions = document.createElement("div");
    actions.className = "node-actions";

    const upButton = document.createElement("button");
    upButton.type = "button";
    upButton.textContent = "↑";
    upButton.title = "Move up";
    upButton.addEventListener("click", () => moveNode(siblings, index, -1));

    const downButton = document.createElement("button");
    downButton.type = "button";
    downButton.textContent = "↓";
    downButton.title = "Move down";
    downButton.addEventListener("click", () => moveNode(siblings, index, 1));

    actions.appendChild(upButton);
    actions.appendChild(downButton);

    const controls = document.createElement("div");
    controls.className = "node-controls";

    if (node.type === "array") {
        const limitLabel = document.createElement("label");
        limitLabel.textContent = "Max items";
        limitLabel.className = "limit-label";
        const limitInput = document.createElement("input");
        limitInput.type = "number";
        limitInput.min = "0";
        limitInput.value = node.limit ?? "";
        limitInput.placeholder = "∞";
        limitInput.addEventListener("input", () => {
            const parsed = limitInput.value ? Number(limitInput.value) : null;
            node.limit = Number.isFinite(parsed) ? parsed : null;
            persistTemplateState();
        });
        limitLabel.appendChild(limitInput);
        controls.appendChild(limitLabel);
    }

    header.appendChild(visibility);
    header.appendChild(nameInput);
    header.appendChild(typeBadge);
    header.appendChild(dataBadge);
    header.appendChild(pathText);
    header.appendChild(actions);
    header.appendChild(controls);

    wrapper.appendChild(header);

    if (Array.isArray(node.children) && node.children.length > 0) {
        const childrenContainer = document.createElement("div");
        childrenContainer.className = "node-children";
        node.children.forEach((child, childIndex) => {
            childrenContainer.appendChild(renderNode(child, node.children, childIndex, depth + 1));
        });
        wrapper.appendChild(childrenContainer);
    }

    return wrapper;
}

function renderTemplateBuilder() {
    if (!templateContainer || !templateState) return;
    templateContainer.innerHTML = "";
    templateState.blocks.forEach((block, index) => {
        templateContainer.appendChild(renderNode(block, templateState.blocks, index, 0));
    });
    syncTemplatePreview();
}

function syncTemplatePreview() {
    if (!templatePreview) return;
    const data = templateState || defaultTemplate || {};
    templatePreview.textContent = JSON.stringify(data, null, 2);
}

async function bootstrapTemplateBuilder() {
    const fallbackTemplate = await loadDefaultTemplate();
    templateState = loadStoredTemplate(fallbackTemplate);
    renderTemplateBuilder();
    if (resetTemplateButton) {
        resetTemplateButton.addEventListener("click", () => {
            templateState = deepClone(fallbackTemplate);
            persistTemplateState();
            renderTemplateBuilder();
        });
    }
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

(async function init() {
    await bootstrapTemplateBuilder();
    document.addEventListener("DOMContentLoaded", fetchSuggestions);
    fetchSuggestions();
})();
