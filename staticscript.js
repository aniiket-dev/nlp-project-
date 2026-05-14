// ============================================
// DOM ELEMENTS
// ============================================
const nlInput = document.getElementById('nlInput');
const generateBtn = document.getElementById('generateBtn');
const clearInputBtn = document.getElementById('clearInputBtn');
const executeBtn = document.getElementById('executeBtn');
const copySqlBtn = document.getElementById('copySqlBtn');
const schemaDisplay = document.getElementById('schemaDisplay');
const refreshSchemaBtn = document.getElementById('refreshSchemaBtn');
const sqlCode = document.getElementById('sqlCode');
const sqlSection = document.getElementById('sqlSection');
const resultsSection = document.getElementById('resultsSection');
const confidenceBadge = document.getElementById('confidenceBadge');
const resultsTable = document.getElementById('resultsTable');
const resultsTableHead = document.getElementById('resultsTableHead');
const resultsTableBody = document.getElementById('resultsTableBody');
const noResults = document.getElementById('noResults');
const rowCount = document.getElementById('rowCount');
const execTime = document.getElementById('execTime');
const statusText = document.getElementById('statusText');
const statusIndicator = document.getElementById('statusIndicator');
const modelName = document.getElementById('modelName');
const deviceInfo = document.getElementById('deviceInfo');
const cacheInfo = document.getElementById('cacheInfo');
const exampleList = document.getElementById('exampleList');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const spinner = document.querySelector('.spinner');
const btnText = document.querySelector('.btn-text');

// ============================================
// STATE
// ============================================
let currentSql = '';
let isGenerating = false;
let queryCount = 0;

// ============================================
// INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  loadSchema();
  loadExamples();
  checkDeviceInfo();
  
  // Focus input
  nlInput.focus();
});

// ============================================
// API FUNCTIONS
// ============================================
async function loadSchema() {
  try {
    const response = await fetch('/api/schema');
    const data = await response.json();
    schemaDisplay.textContent = data.schema || 'No schema available';
    
    // Extract model name from response if available
    if (data.model) {
      modelName.textContent = data.model;
    } else {
      modelName.textContent = 'defog/sqlcoder-7b-2';
    }
  } catch (error) {
    schemaDisplay.textContent = 'Error loading schema. Make sure the server is running.';
    showToast('Failed to load schema', 'error');
  }
}

async function loadExamples() {
  try {
    const response = await fetch('/api/examples');
    const examples = await response.json();
    
    exampleList.innerHTML = examples.map(example => 
      `<div class="example-item" data-query="${escapeHtml(example)}">${escapeHtml(example)}</div>`
    ).join('');
    
    // Add click handlers
    document.querySelectorAll('.example-item').forEach(item => {
      item.addEventListener('click', () => {
        if (!isGenerating) {
          nlInput.value = item.getAttribute('data-query');
          nlInput.focus();
          generateSQL();
        }
      });
    });
  } catch (error) {
    exampleList.innerHTML = '<div class="loading-text">Failed to load examples</div>';
  }
}

async function checkDeviceInfo() {
  try {
    // Simple check - could be enhanced with an API endpoint
    deviceInfo.textContent = 'CPU';
    
    // Check if WebGL is available (indicates GPU)
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) {
        const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
        if (renderer.includes('Intel') || renderer.includes('AMD') || renderer.includes('NVIDIA')) {
          deviceInfo.textContent = 'GPU Available';
        }
      }
    }
  } catch (error) {
    deviceInfo.textContent = 'Unknown';
  }
}

async function generateSQL() {
  const query = nlInput.value.trim();
  
  if (!query) {
    showToast('Please enter a question first', 'warning');
    return;
  }
  
  if (isGenerating) return;
  
  // Set loading state
  setLoading(true);
  updateStatus('Generating SQL...', 'loading');
  
  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: query })
    });
    
    const data = await response.json();
    
    if (data.error) {
      displaySQLError(data.error);
      updateStatus('Generation failed', 'error');
      showToast(data.error, 'error');
    } else {
      displaySQL(data);
      queryCount++;
      cacheInfo.textContent = `${queryCount} queries`;
      updateStatus('SQL generated successfully', 'ready');
      
      // Auto-execute if confidence is high
      if (data.confidence > 0.8) {
        setTimeout(() => executeSQL(), 500);
      }
    }
  } catch (error) {
    displaySQLError('Network error. Check if the server is running.');
    updateStatus('Connection error', 'error');
    showToast('Failed to connect to server', 'error');
  } finally {
    setLoading(false);
  }
}

async function executeSQL() {
  if (!currentSql) {
    showToast('No SQL to execute', 'warning');
    return;
  }
  
  updateStatus('Executing query...', 'loading');
  showResultsSection();
  
  try {
    const response = await fetch('/api/execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql: currentSql })
    });
    
    const data = await response.json();
    
    if (data.error) {
      displayResultsError(data.error);
      updateStatus('Execution failed', 'error');
      showToast(data.error, 'error');
    } else {
      displayResults(data);
      updateStatus(`Query executed in ${data.execution_time}s`, 'ready');
    }
  } catch (error) {
    displayResultsError('Failed to execute query');
    updateStatus('Execution error', 'error');
    showToast('Failed to execute query', 'error');
  }
}

async function refreshSchema() {
  try {
    await fetch('/api/refresh-schema', { method: 'POST' });
    await loadSchema();
    showToast('Schema refreshed successfully', 'success');
    updateStatus('Schema updated', 'ready');
  } catch (error) {
    showToast('Failed to refresh schema', 'error');
  }
}

// ============================================
// UI UPDATE FUNCTIONS
// ============================================
function setLoading(loading) {
  isGenerating = loading;
  generateBtn.disabled = loading;
  
  if (loading) {
    btnText.textContent = 'Generating...';
    spinner.classList.remove('hidden');
  } else {
    btnText.textContent = 'Generate SQL';
    spinner.classList.add('hidden');
  }
}

function displaySQL(data) {
  currentSql = data.sql;
  sqlCode.textContent = data.sql;
  
  // Show confidence
  confidenceBadge.classList.remove('hidden');
  confidenceBadge.innerHTML = `Confidence: <strong>${Math.round(data.confidence * 100)}%</strong>`;
  
  // Enable buttons
  executeBtn.disabled = false;
  copySqlBtn.disabled = false;
  
  // Show SQL section
  showSQLSection();
}

function displaySQLError(error) {
  currentSql = '';
  sqlCode.textContent = `-- Error: ${error}`;
  sqlCode.style.color = 'var(--danger)';
  
  confidenceBadge.classList.add('hidden');
  executeBtn.disabled = true;
  copySqlBtn.disabled = true;
  
  showSQLSection();
  
  // Reset color after delay
  setTimeout(() => {
    sqlCode.style.color = 'var(--accent-primary)';
  }, 3000);
}

function displayResults(data) {
  const { columns, rows, row_count, execution_time } = data;
  
  // Clear previous results
  resultsTableHead.innerHTML = '';
  resultsTableBody.innerHTML = '';
  
  if (!columns || columns.length === 0) {
    noResults.classList.remove('hidden');
    noResults.innerHTML = '<span class="no-results-icon">📭</span><p>Query executed but no columns returned</p>';
    return;
  }
  
  if (rows.length === 0) {
    noResults.classList.remove('hidden');
    noResults.innerHTML = '<span class="no-results-icon">📭</span><p>No rows returned</p>';
  } else {
    noResults.classList.add('hidden');
    
    // Create header
    const headerRow = document.createElement('tr');
    columns.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col;
      headerRow.appendChild(th);
    });
    resultsTableHead.appendChild(headerRow);
    
    // Create rows
    rows.forEach(row => {
      const tr = document.createElement('tr');
      columns.forEach(col => {
        const td = document.createElement('td');
        td.textContent = row[col] !== null && row[col] !== undefined ? row[col] : 'NULL';
        tr.appendChild(td);
      });
      resultsTableBody.appendChild(tr);
    });
  }
  
  // Update meta
  rowCount.textContent = `${row_count} rows`;
  execTime.textContent = `${execution_time}s`;
}

function displayResultsError(error) {
  resultsTableHead.innerHTML = '';
  resultsTableBody.innerHTML = '';
  noResults.classList.remove('hidden');
  noResults.innerHTML = `<span class="no-results-icon">❌