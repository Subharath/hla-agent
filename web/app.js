/**
 * HLA Agent — Frontend Application
 * Handles API calls, WebSocket pipeline, Chart.js radar, and Mermaid rendering.
 */

// ─── State ────────────────────────────────────
let currentRequirements = null;
let currentResults = null;
let radarChartInstance = null;
let ws = null;

// ─── Init ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadSamples();
    loadHistory();
    mermaid.initialize({ theme: 'dark', startOnLoad: false });
});

// ─── Navigation ───────────────────────────────
function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const section = link.dataset.section;
            showSection(section);
        });
    });
}

function showSection(name) {
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`[data-section="${name}"]`)?.classList.add('active');

    const sectionMap = {
        input: 'input-section',
        results: 'results-section',
        diagrams: 'diagrams-section',
        history: 'history-section',
    };

    Object.values(sectionMap).forEach(id => {
        document.getElementById(id)?.classList.add('hidden');
    });

    const targetId = sectionMap[name];
    if (targetId) {
        document.getElementById(targetId)?.classList.remove('hidden');
    }
}

// ─── Samples ──────────────────────────────────
async function loadSamples() {
    try {
        const res = await fetch('/api/samples');
        if (!res.ok) return;
        const samples = await res.json();

        // Check health / model availability and populate model checkboxes dynamically
        try {
            const hRes = await fetch('/api/health');
            if (hRes.ok) {
                const health = await hRes.json();
                const models = health.models || {};
                const configuredModels = health.configured_models || Object.keys(models);
                const available = Object.values(models).filter(v => v).length;

                // Build model checkboxes dynamically
                const container = document.getElementById('modelCheckboxes');
                container.innerHTML = '';
                configuredModels.forEach(model => {
                    const isAvailable = models[model] || false;
                    const cssClass = getModelCssClass(model);
                    const displayName = getModelDisplayName(model);
                    container.innerHTML += `
                        <label class="model-check">
                            <input type="checkbox" value="${model}" ${isAvailable ? 'checked' : 'disabled'}>
                            <span class="model-tag ${cssClass}">${displayName}${isAvailable ? '' : ' ⛔'}</span>
                        </label>`;
                });

                // Update footer with actual model names and provider
                const footer = document.getElementById('footerModels');
                if (footer) {
                    const providerName = health.provider || 'Unknown';
                    footer.textContent = 'Powered by ' + configuredModels.map(getModelDisplayName).join(' • ') + ' via ' + providerName.charAt(0).toUpperCase() + providerName.slice(1);
                }

                if (available > 0) {
                    updateStatus('Ready', '#10B981');
                    document.getElementById('statModels').textContent = String(available);
                } else {
                    updateStatus('No Models', '#F59E0B');
                }
            }
        } catch (he) {
            // Fallback: populate with defaults if API fails
            updateStatus('Ready', '#10B981');
        }
    } catch (e) {
        console.log('Server not available yet');
    }
}

// Map model names to CSS classes for styling
function getModelCssClass(model) {
    if (model.startsWith('llama')) return 'llama';
    if (model.startsWith('mistral') || model.startsWith('mixtral')) return 'mistral';
    if (model.startsWith('qwen')) return 'qwen';
    if (model.startsWith('deepseek')) return 'deepseek';
    if (model.startsWith('gemini')) return 'gemini';
    return 'default';
}

// Map model names to human-readable display names
function getModelDisplayName(model) {
    const names = {
        // Ollama models
        'llama3.1': 'LLaMA 3.1',
        'mistral': 'Mistral',
        'qwen3': 'Qwen 3',
        // Groq models
        'llama-3.3-70b-versatile': 'LLaMA 3.3 70B',
        'mixtral-8x7b-32768': 'Mixtral 8x7B',
        // DeepSeek models
        'deepseek-chat': 'DeepSeek V3',
        'deepseek-reasoner': 'DeepSeek R1',
        // Gemini models
        'gemini-2.0-flash': 'Gemini 2.0 Flash',
        'gemini-2.0-flash-lite': 'Gemini 2.0 Flash Lite',
    };
    return names[model] || model;
}

async function loadSample(filename) {
    try {
        const res = await fetch(`/api/samples/${filename}`);
        if (!res.ok) return;
        const data = await res.json();
        currentRequirements = data;

        const editor = document.getElementById('jsonEditor');
        editor.value = JSON.stringify(data, null, 2);

        document.querySelectorAll('.sample-btn').forEach(b => b.classList.remove('active'));
        document.querySelector(`[data-file="${filename}"]`)?.classList.add('active');

        const info = document.getElementById('editorInfo');
        info.textContent = `${data.project} — ${data.functional_requirements.length} FRs, ${data.non_functional_requirements.length} NFRs`;
    } catch (e) {
        console.error('Failed to load sample:', e);
    }
}

// Attach sample button click handlers
document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', () => loadSample(btn.dataset.file));
});

// ─── Pipeline Execution ──────────────────────
function startPipeline() {
    const editor = document.getElementById('jsonEditor');
    let requirements;

    try {
        requirements = JSON.parse(editor.value);
    } catch (e) {
        alert('Invalid JSON! Please check your input.');
        return;
    }

    // Get selected models
    const models = [];
    document.querySelectorAll('#modelCheckboxes input:checked').forEach(cb => {
        models.push(cb.value);
    });

    if (models.length === 0) {
        alert('Please select at least one model.');
        return;
    }

    // Disable run button
    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="run-icon">⏳</span><span>Running...</span>';

    // Show progress
    const progressSection = document.getElementById('progressSection');
    progressSection.classList.remove('hidden');
    updateProgress(10, 'Connecting to server...');

    // WebSocket connection
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws/pipeline`);

    ws.onopen = () => {
        updateProgress(20, 'Sending requirements to pipeline...');
        ws.send(JSON.stringify({ requirements, models }));
        updateStatus('Running', '#F59E0B');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'status') {
            const stepProgress = {
                start: 25, load: 30, models: 35, init: 40,
                prompt: 45, generate: 55, evaluate: 70, rank: 80, output: 90, done: 100,
            };
            updateProgress(stepProgress[data.step] || 50, data.message);
        }

        if (data.type === 'complete') {
            updateProgress(100, '✅ Pipeline complete!');
            currentResults = data;
            displayResults(data);
            updateStatus('Complete', '#10B981');
            resetRunButton();
            showSection('results');
            loadHistory();
        }

        if (data.type === 'error') {
            updateProgress(0, `❌ Error: ${data.message}`);
            updateStatus('Error', '#EF4444');
            resetRunButton();
        }
    };

    ws.onerror = () => {
        updateProgress(0, '❌ WebSocket connection failed. Is the server running?');
        updateStatus('Error', '#EF4444');
        resetRunButton();
    };

    ws.onclose = () => {
        if (btn.disabled) resetRunButton();
    };
}

function resetRunButton() {
    const btn = document.getElementById('runBtn');
    btn.disabled = false;
    btn.innerHTML = '<span class="run-icon">▶</span><span>Run Pipeline</span>';
}

function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = percent + '%';
    const log = document.getElementById('progressLog');
    const time = new Date().toLocaleTimeString();
    log.innerHTML += `<div>[${time}] ${message}</div>`;
    log.scrollTop = log.scrollHeight;
}

function updateStatus(text, color) {
    const status = document.getElementById('navStatus');
    status.querySelector('.status-text').textContent = text;
    status.querySelector('.status-dot').style.background = color;
}

// ─── Display Results ─────────────────────────
function displayResults(data) {
    const resultsSection = document.getElementById('results-section');
    resultsSection.classList.remove('hidden');

    document.getElementById('resultsRunId').textContent = `Run ID: ${data.run_id}`;

    // Winner card
    const winner = data.winner;
    const ws = winner.scores;
    document.getElementById('winnerTitle').textContent = `${winner.model} — ${winner.architecture.architecture_style}`;
    document.getElementById('winnerSub').textContent = `${winner.architecture.components.length} components, ${winner.architecture.interactions.length} interactions`;
    document.getElementById('winnerCAS').textContent = ws.CAS.toFixed(4);

    // Winner metrics
    const metricsDiv = document.getElementById('winnerMetrics');
    metricsDiv.innerHTML = '';
    ['RCR', 'NAS', 'SMI', 'LSCS', 'SCI'].forEach(metric => {
        const val = ws[metric] || 0;
        const colorClass = val >= 0.8 ? 'score-high' : val >= 0.6 ? 'score-mid' : 'score-low';
        const barColor = val >= 0.8 ? '#10B981' : val >= 0.6 ? '#F59E0B' : '#EF4444';
        metricsDiv.innerHTML += `
            <div class="metric-card fade-in">
                <div class="metric-name">${metric}</div>
                <div class="metric-value ${colorClass}">${val.toFixed(2)}</div>
                <div class="metric-bar"><div class="metric-bar-fill" style="width:${val*100}%;background:${barColor}"></div></div>
            </div>`;
    });

    // Ranking table
    const tbody = document.getElementById('resultsBody');
    tbody.innerHTML = '';
    data.candidates.forEach(c => {
        const s = c.scores;
        const rankClass = c.rank <= 3 ? `rank-${c.rank}` : '';
        const verdictClass = s.verdict === 'Accepted' ? 'verdict-accepted' : s.verdict === 'Marginal' ? 'verdict-marginal' : 'verdict-poor';
        const verdictIcon = s.verdict === 'Accepted' ? '✅' : s.verdict === 'Marginal' ? '⚠️' : '❌';

        tbody.innerHTML += `<tr>
            <td><span class="rank-badge ${rankClass}">${c.rank}</span></td>
            <td>${c.model}</td>
            <td>${c.architecture.architecture_style}</td>
            <td class="${scoreColor(s.RCR)}">${s.RCR.toFixed(2)}</td>
            <td class="${scoreColor(s.NAS)}">${s.NAS.toFixed(2)}</td>
            <td class="${scoreColor(s.SMI)}">${s.SMI.toFixed(2)}</td>
            <td class="${scoreColor(s.LSCS)}">${s.LSCS.toFixed(2)}</td>
            <td class="${scoreColor(s.SCI)}">${s.SCI.toFixed(2)}</td>
            <td><strong>${s.CAS.toFixed(4)}</strong></td>
            <td><span class="verdict-badge ${verdictClass}">${verdictIcon} ${s.verdict}</span></td>
        </tr>`;
    });

    // Radar chart
    renderRadarChart(data.candidates);

    // Components grid
    const grid = document.getElementById('componentsGrid');
    grid.innerHTML = '';
    winner.architecture.components.forEach(comp => {
        grid.innerHTML += `
            <div class="comp-card fade-in">
                <div class="comp-name">${comp.name}</div>
                <div class="comp-layer">${comp.layer}</div>
                <div class="comp-resp">${comp.responsibility}</div>
            </div>`;
    });

    // Load diagrams
    loadDiagrams(data);
}

function scoreColor(val) {
    return val >= 0.8 ? 'score-high' : val >= 0.6 ? 'score-mid' : 'score-low';
}

// ─── Radar Chart ─────────────────────────────
function renderRadarChart(candidates) {
    const ctx = document.getElementById('radarChart').getContext('2d');

    if (radarChartInstance) radarChartInstance.destroy();

    const modelColors = {
        // Ollama models
        'llama3.1': { bg: 'rgba(0,201,167,0.2)', border: '#00C9A7' },
        'mistral': { bg: 'rgba(132,94,194,0.2)', border: '#845EC2' },
        'qwen3': { bg: 'rgba(255,111,0,0.2)', border: '#FF6F00' },
        // Groq models
        'llama-3.3-70b-versatile': { bg: 'rgba(0,201,167,0.2)', border: '#00C9A7' },
        'mixtral-8x7b-32768': { bg: 'rgba(132,94,194,0.2)', border: '#845EC2' },
        // DeepSeek models
        'deepseek-chat': { bg: 'rgba(0,122,255,0.2)', border: '#007AFF' },
        // Gemini models
        'gemini-2.0-flash': { bg: 'rgba(66,133,244,0.2)', border: '#4285F4' },
    };

    const fallbackColors = [
        { bg: 'rgba(59,130,246,0.2)', border: '#3B82F6' },
        { bg: 'rgba(236,72,153,0.2)', border: '#EC4899' },
        { bg: 'rgba(253,203,110,0.2)', border: '#FDCB6E' },
    ];

    const datasets = candidates.map((c, i) => {
        const colors = modelColors[c.model] || fallbackColors[i % fallbackColors.length];
        return {
            label: `${c.model} #${c.candidate_num} (CAS=${c.scores.CAS.toFixed(3)})`,
            data: [c.scores.RCR, c.scores.NAS, c.scores.SMI, c.scores.LSCS, c.scores.SCI],
            backgroundColor: colors.bg,
            borderColor: colors.border,
            borderWidth: 2,
            pointBackgroundColor: colors.border,
            pointRadius: 5,
        };
    });

    radarChartInstance = new Chart(ctx, {
        type: 'radar',
        data: { labels: ['RCR', 'NAS', 'SMI', 'LSCS', 'SCI'], datasets },
        options: {
            responsive: true,
            scales: {
                r: {
                    min: 0, max: 1,
                    ticks: { stepSize: 0.2, color: '#64748b', backdropColor: 'transparent' },
                    grid: { color: 'rgba(255,255,255,0.08)' },
                    angleLines: { color: 'rgba(255,255,255,0.08)' },
                    pointLabels: { color: '#f1f5f9', font: { size: 14, weight: 'bold' } },
                }
            },
            plugins: {
                legend: { labels: { color: '#f1f5f9', font: { size: 12 }, padding: 16 } }
            }
        }
    });
}

// ─── Diagrams ────────────────────────────────
async function loadDiagrams(data) {
    const diagramSection = document.getElementById('diagrams-section');
    diagramSection.classList.remove('hidden');

    // Render Mermaid from winner architecture
    const arch = data.winner.architecture;
    let mmdCode = 'flowchart TD\n';
    const layerComps = {};
    arch.components.forEach(c => {
        if (!layerComps[c.layer]) layerComps[c.layer] = [];
        layerComps[c.layer].push(c);
    });

    arch.layers.forEach(l => {
        const safe = l.name.replace(/\s+/g, '_');
        const comps = layerComps[l.name] || [];
        mmdCode += `    subgraph ${safe}["${l.name}"]\n`;
        comps.forEach(c => {
            const cid = c.name.replace(/\s+/g, '_');
            mmdCode += `        ${cid}["${c.name}"]\n`;
        });
        mmdCode += '    end\n';
    });

    arch.interactions.forEach(inter => {
        const from = inter.from.replace(/\s+/g, '_');
        const to = inter.to.replace(/\s+/g, '_');
        mmdCode += `    ${from} -->|"${inter.type}"| ${to}\n`;
    });

    try {
        const { svg } = await mermaid.render('mermaidSvg', mmdCode);
        document.getElementById('mermaidDiagram').innerHTML = svg;
    } catch (e) {
        document.getElementById('mermaidDiagram').innerHTML = `<pre style="color:#94a3b8">${mmdCode}</pre>`;
    }

    // Load PlantUML source
    try {
        const res = await fetch(`/api/results/${data.run_id}/diagram/plantuml`);
        if (res.ok) {
            const d = await res.json();
            document.getElementById('plantumlDiagram').textContent = d.content;
        }
    } catch (e) { /* ignore */ }
}

function showDiagramTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    document.getElementById('mermaidDiagram').classList.toggle('hidden', tab !== 'mermaid');
    document.getElementById('plantumlDiagram').classList.toggle('hidden', tab !== 'plantuml');
}

// ─── History ─────────────────────────────────
async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        if (!res.ok) return;
        const runs = await res.json();

        const tbody = document.getElementById('historyBody');
        tbody.innerHTML = '';

        runs.forEach(run => {
            const statusClass = run.status === 'completed' ? 'score-high' : run.status === 'failed' ? 'score-low' : 'score-mid';
            tbody.innerHTML += `<tr>
                <td><strong>${run.run_id}</strong></td>
                <td>${run.project}</td>
                <td>${new Date(run.timestamp).toLocaleString()}</td>
                <td>${run.total_candidates || '-'}</td>
                <td>${run.winner_model || '-'}</td>
                <td class="${statusClass}">${run.winner_cas ? run.winner_cas.toFixed(4) : '-'}</td>
                <td class="${statusClass}">${run.status}</td>
            </tr>`;
        });
    } catch (e) { /* Server not available */ }
}
