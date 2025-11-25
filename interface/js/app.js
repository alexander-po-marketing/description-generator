(function () {
  const selectors = {
    apiKey: document.getElementById('apiKey'),
    apiOrg: document.getElementById('apiOrg'),
    apiProject: document.getElementById('apiProject'),
    model: document.getElementById('model'),
    temperature: document.getElementById('temperature'),
    maxTokens: document.getElementById('maxTokens'),
    xmlPath: document.getElementById('xmlPath'),
    databaseJson: document.getElementById('databaseJson'),
    descriptionsJson: document.getElementById('descriptionsJson'),
    descriptionsXml: document.getElementById('descriptionsXml'),
    validDrugIds: document.getElementById('validDrugIds'),
    validDrugFile: document.getElementById('validDrugFile'),
    maxDrugs: document.getElementById('maxDrugs'),
    logLevel: document.getElementById('logLevel'),
    cacheDir: document.getElementById('cacheDir'),
    logFile: document.getElementById('logFile'),
    dryRun: document.getElementById('dryRun'),
    apiEndpoint: document.getElementById('apiEndpoint'),
    runButton: document.getElementById('runButton'),
    resetButton: document.getElementById('resetButton'),
    status: document.getElementById('status'),
    logOutput: document.getElementById('logOutput'),
  };

  const defaultPaths = {
    xml: ['inputs/drugbank/database_part_1.xml', 'inputs/drugbank/database.xml'],
    database: ['outputs/database.json'],
    descJson: ['outputs/api_descriptions.json'],
    descXml: ['outputs/api_descriptions.xml'],
    validFile: ['inputs/drugbank/valid_drug_ids.txt'],
    cacheDir: 'cache',
    logFile: 'logs/pipeline_run.log',
  };

  function populateSuggestions() {
    fillDatalist('xmlSuggestions', defaultPaths.xml);
    fillDatalist('databaseSuggestions', defaultPaths.database);
    fillDatalist('descJsonSuggestions', defaultPaths.descJson);
    fillDatalist('descXmlSuggestions', defaultPaths.descXml);
    selectors.validDrugFile.value = defaultPaths.validFile[0];
    selectors.cacheDir.value = defaultPaths.cacheDir;
    selectors.logFile.value = defaultPaths.logFile;
    selectors.xmlPath.value = defaultPaths.xml[0];
    selectors.databaseJson.value = defaultPaths.database[0];
    selectors.descriptionsJson.value = defaultPaths.descJson[0];
    selectors.descriptionsXml.value = defaultPaths.descXml[0];
  }

  function fillDatalist(id, values) {
    const list = document.getElementById(id);
    list.innerHTML = '';
    values.forEach((value) => {
      const option = document.createElement('option');
      option.value = value;
      list.appendChild(option);
    });
  }

  function getOutputPolicy() {
    const checked = document.querySelector('input[name="outputPolicy"]:checked');
    return checked ? checked.value : 'overwrite';
  }

  function setStatus(message, tone = 'info') {
    selectors.status.textContent = message;
    selectors.status.className = `status-${tone}`;
  }

  function appendLog(message) {
    const timestamp = new Date().toISOString();
    selectors.logOutput.textContent += `\n[${timestamp}] ${message}`;
  }

  function resetForm() {
    document.querySelector('input[name="outputPolicy"][value="overwrite"]').checked = true;
    selectors.validDrugIds.value = '';
    selectors.validDrugFile.value = defaultPaths.validFile[0];
    selectors.maxDrugs.value = '';
    selectors.logLevel.value = 'INFO';
    selectors.cacheDir.value = defaultPaths.cacheDir;
    selectors.logFile.value = defaultPaths.logFile;
    selectors.dryRun.checked = false;
    setStatus('Form reset to defaults.');
    selectors.logOutput.textContent = 'Waiting for a run...';
  }

  function collectPayload() {
    return {
      apiKey: selectors.apiKey.value.trim(),
      apiOrg: selectors.apiOrg.value.trim(),
      apiProject: selectors.apiProject.value.trim(),
      model: selectors.model.value.trim(),
      temperature: parseFloat(selectors.temperature.value),
      maxTokens: parseInt(selectors.maxTokens.value, 10),
      xmlPath: selectors.xmlPath.value.trim(),
      databaseJson: selectors.databaseJson.value.trim(),
      descriptionsJson: selectors.descriptionsJson.value.trim(),
      descriptionsXml: selectors.descriptionsXml.value.trim(),
      validDrugIds: selectors.validDrugIds.value.trim(),
      validDrugFile: selectors.validDrugFile.value.trim(),
      maxDrugs: selectors.maxDrugs.value ? parseInt(selectors.maxDrugs.value, 10) : null,
      logLevel: selectors.logLevel.value,
      cacheDir: selectors.cacheDir.value.trim(),
      logFile: selectors.logFile.value.trim(),
      overwrite: getOutputPolicy() === 'overwrite',
      dryRun: selectors.dryRun.checked,
    };
  }

  async function runPipeline() {
    const payload = collectPayload();
    const missing = [];
    if (!payload.xmlPath) missing.push('DrugBank XML');
    if (!payload.databaseJson) missing.push('database JSON');
    if (!payload.descriptionsJson) missing.push('descriptions JSON');
    if (!payload.descriptionsXml) missing.push('descriptions XML');
    if (missing.length) {
      setStatus(`Please provide ${missing.join(', ')} path(s).`, 'error');
      return;
    }

    setStatus('Submitting configuration to backend...', 'info');
    appendLog('Submitting configuration to backend...');

    try {
      const response = await fetch(selectors.apiEndpoint.value, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        setStatus(`Backend responded with ${response.status}`, 'error');
        appendLog(`Backend error: ${response.statusText}`);
        return;
      }

      const data = await response.json();
      const summary = data.message || 'Run completed.';
      setStatus(summary, 'success');
      selectors.logOutput.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      console.error(error);
      setStatus('Failed to reach backend. Is the interface server running?', 'error');
      appendLog(`Network error: ${error}`);
    }
  }

  function wireEvents() {
    selectors.runButton.addEventListener('click', runPipeline);
    selectors.resetButton.addEventListener('click', resetForm);
  }

  populateSuggestions();
  wireEvents();
})();
