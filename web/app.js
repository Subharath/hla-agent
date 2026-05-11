/**
 * HLA Agent — Frontend Application
 * Handles API calls, WebSocket pipeline, Chart.js radar, and Mermaid rendering.
 */

// ─── State ────────────────────────────────────
let currentRequirements = null;
let currentResults = null;
let radarChartInstance = null;
let ws = null;
let currentRunId = null;
let diagramWorkflow = null;

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
        'deepseek-v4-flash': 'DeepSeek V4 Flash',
        'deepseek-v4-pro': 'DeepSeek V4 Pro',
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

        if (data.type === 'phase1_complete') {
            updateProgress(100, '⚖️ Phase 1 complete. Pending human selection.');
            currentResults = data;
            displayTradeoffPhase(data);
            updateStatus('Pending Selection', '#FACC15');
            resetRunButton();
            showSection('results');
            loadHistory();
        }

        if (data.type === 'complete') {
            updateProgress(100, '✅ Elaboration complete!');
            currentResults = data;
            displayFinalWinner(data);
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

// ─── Display Tradeoff Phase (Phase 1) ────────
function displayTradeoffPhase(data) {
    const resultsSection = document.getElementById('results-section');
    resultsSection.classList.remove('hidden');
    document.getElementById('diagrams-section').classList.add('hidden');

    const selectedIndex = (data.selectedCandidateIndex ?? currentResults?.selectedCandidateIndex);

    document.getElementById('resultsRunId').textContent = `Run ID: ${data.run_id} — Pending ATAM Tradeoff Selection`;
    document.getElementById('diagrams-section').classList.add('hidden');
    document.getElementById('mermaidDiagram').innerHTML = '';
    document.getElementById('mermaidCode').textContent = '';
    document.getElementById('mermaidCode').classList.add('hidden');

    document.getElementById('plantumlPanel').classList.add('hidden');
    document.getElementById('plantumlEditor').value = '';
    document.getElementById('plantumlDiff').textContent = '';
    document.getElementById('plantumlStatus').textContent = '';
    document.getElementById('plantumlMetrics').innerHTML = '';
    diagramWorkflow = null;
    currentRunId = null;
    
    // Hide winner card, show tradeoff card
    document.getElementById('winnerCard').classList.add('hidden');
    document.getElementById('componentsCard').classList.add('hidden');
    const tradeoffCard = document.getElementById('tradeoffCard');
    tradeoffCard.classList.remove('hidden');
    
    // Trivial Decision Logic
    const isDominant = data.dominant_winner === true;
    let headerHtml = `
        <div class="card-header-row">
            <h3 class="card-title">⚖️ ATAM Tradeoff Analysis</h3>
            <div class="badge" style="background: rgba(234, 179, 8, 0.2); color: #facc15;">Action Required</div>
        </div>
        <p style="color: var(--text-muted); margin-bottom: 20px;">Review the generated candidates below. Analyze their architectural characteristics and select the best fit for your organizational context to proceed with diagram elaboration.</p>
    `;

    if (isDominant) {
        headerHtml = `
            <div class="card-header-row" style="background: rgba(16, 185, 129, 0.1); padding: 15px; border-radius: var(--radius-sm); border: 1px solid var(--success);">
                <h3 class="card-title" style="color: var(--success); margin: 0;">🏆 ATAM Trivial Decision: Dominant Architecture Detected</h3>
            </div>
            <p style="color: var(--text-muted); margin: 15px 0 20px;">The top-ranked architecture clearly dominates the Utility Tree without significant tradeoff conflicts. It is mathematically recommended to proceed with this candidate.</p>
        `;
    }
    
    // Update Tradeoff Card Header
    const tradeoffGrid = document.getElementById('tradeoffGrid');
    tradeoffCard.innerHTML = headerHtml + '<div class="tradeoff-grid" id="tradeoffGrid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px;"></div>';


    // Phase 1 intentionally does not show radar chart.
    document.getElementById('radarImage').style.display = 'none';
    document.getElementById('radarChart').style.display = 'none';

    const grid = document.getElementById('tradeoffGrid');
    
    data.candidates.forEach((c, index) => {
        const s = c.scores || {};
        const isFailed = c.rank === -1;
        const isTop = index === 0 && isDominant;
        const isSelected = selectedIndex === index;
        
        // CSS classes for Dominant UI
        const cardClass = isSelected ? 'card glass-card dominant-card' : (isTop ? 'card glass-card dominant-card' : (isDominant ? 'card glass-card alternative-card' : 'card glass-card'));
        const glowStyle = isSelected ? 'box-shadow: 0 0 20px rgba(16, 185, 129, 0.45); border-color: var(--success);' : (isTop ? 'box-shadow: 0 0 20px rgba(16, 185, 129, 0.4); border-color: var(--success);' : '');
        const rankBadge = isFailed ? '<div class="badge" style="background: rgba(239, 68, 68, 0.2); color: var(--danger); position: absolute; top: 10px; right: 10px;">Failed</div>' 
                                   : isSelected ? '<div class="badge" style="background: rgba(16, 185, 129, 0.2); color: var(--success); position: absolute; top: 10px; right: 10px;">Selected</div>'
                                   : `<div class="badge" style="position: absolute; top: 10px; right: 10px;">Rank ${c.rank}</div>`;
        
        let contentHtml = '';
        if (isFailed) {
            contentHtml = `
                <div style="color: var(--danger); font-weight: bold; margin: 10px 0;">Error:</div>
                <div style="font-size: 0.85em; color: var(--text-secondary); background: rgba(0,0,0,0.3); padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                    ${c.error || "Generation Failed"}
                </div>
            `;
        } else {
            const prosCons = c.architecture.pros_and_cons || "No contextual analysis provided.";
                // Build deterministic NAS rubric breakdown
                let nfrBlock = '';
                try {
                    const nasDetails = s.details?.nas?.alignment_map || {};
                    const unaligned = s.details?.nas?.unaligned || [];
                    const alignedCount = s.details?.nas?.aligned_count ?? Object.values(nasDetails).filter(v => v.aligned || v.coverage === 1).length;
                    const nfrEntries = Object.entries(nasDetails);
                    if (nfrEntries.length) {
                        nfrBlock += `<div class="nfr-coverage"><strong>NAS Evidence Rubric</strong> <span class="nfr-summary">(${alignedCount}/${nfrEntries.length} aligned)</span>`;
                        nfrEntries.forEach(([nid, info], idx) => {
                            const bd = info.breakdown || {};
                            const coverage = Number(info.coverage ?? (info.aligned ? 1 : 0));
                            const status = (unaligned.includes(nid) || coverage < 1) ? 'Unaligned' : 'Aligned';
                            const target = info.target ? `<span class="nfr-target">${info.target}</span>` : '';
                            const finalScore = (bd.final_score ?? info.score ?? 0).toFixed(4);
                            const details = bd.details || {};
                            const statusColor = status === 'Aligned' ? 'var(--success)' : 'var(--danger)';
                            
                            nfrBlock += `<div class="nfr-item" style="border-left: 4px solid ${statusColor}; padding-left: 12px; margin: 8px 0;">`;
                            nfrBlock += `<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">`;
                            nfrBlock += `<strong>${nid}</strong> <span style="color: ${statusColor}; font-weight: bold;">${finalScore}</span>`;
                            nfrBlock += `</div>`;
                            nfrBlock += `<div style="font-size: 0.8em; color: var(--text-muted); margin-bottom: 6px;">${info.type} • ${target}</div>`;
                            nfrBlock += `<details style="cursor: pointer; user-select: none;">`;
                            nfrBlock += `<summary style="color: var(--accent-secondary); font-size: 0.85em; padding: 4px 0; outline: none;">Show calculation</summary>`;
                            nfrBlock += `<div style="background: rgba(0,0,0,0.15); padding: 8px; border-radius: 3px; margin-top: 6px; font-size: 0.8em; font-family: monospace;">`;
                            nfrBlock += `<div>Formula: score = evidence + interaction + style_bonus - penalty</div>`;
                            nfrBlock += `<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 4px;">`;
                            nfrBlock += `<div>Evidence Score: <strong>${(bd.evidence_score ?? 0).toFixed(4)}</strong></div>`;
                            nfrBlock += `<div>Interaction Bonus: <strong>+${(bd.interaction_bonus ?? 0).toFixed(4)}</strong></div>`;
                            nfrBlock += `<div>Style Bonus: <strong>+${(bd.style_bonus ?? 0).toFixed(4)}</strong></div>`;
                            nfrBlock += `<div>Style Penalty: <strong>-${(bd.style_penalty ?? 0).toFixed(4)}</strong></div>`;
                            nfrBlock += `</div>`;
                            nfrBlock += `<div style="margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px;">`;
                            nfrBlock += `<strong>Final Score: ${finalScore}</strong> (${status})`;
                            nfrBlock += `</div>`;
                            nfrBlock += `<div style="margin-top: 4px; font-size: 0.75em; color: var(--text-secondary);">`;
                            nfrBlock += `High matches: ${details.high_hits || 0} | Medium: ${details.medium_hits || 0} | Implicit: ${details.implicit_hits || 0} | Style: ${details.style || 'N/A'}`;
                            nfrBlock += `</div>`;
                            nfrBlock += `</div></details></div>`;
                        });
                        nfrBlock += `</div>`;
                    }
                } catch (e) { console.error("NFR rendering error:", e); nfrBlock = ''; }

                contentHtml = `
                <div style="font-size: 1.5em; font-weight: 700; color: var(--primary); margin: 10px 0;">Phase 1 CAS: ${(s.PHASE1_CAS || 0).toFixed(4)}</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px; font-size: 0.85em; margin-bottom: 15px; border-bottom: 1px solid var(--glass-border); padding-bottom: 10px;">
                    <div><strong>RCR</strong> (Func): ${s.RCR.toFixed(2)}</div>
                    <div><strong>NAS</strong> (NFR): ${s.NAS.toFixed(2)}</div>
                </div>
                <div style="font-size: 0.85em; color: var(--text-secondary); margin-bottom: 15px; font-style: italic; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 4px; border-left: 3px solid var(--accent-primary);">
                    <strong>LLM Analysis:</strong><br>${prosCons}
                </div>
                    ${nfrBlock}
                <button class="run-btn" style="width: 100%; justify-content: center; ${isSelected ? 'background: var(--success);' : (isTop ? 'background: var(--success);' : '')}" onclick="selectCandidate('${data.run_id}', ${index})">
                    ${isSelected ? 'Selected for Phase 2' : (isTop ? 'Accept Dominant Architecture' : 'Select this Architecture')}
                </button>
            `;
        }

        grid.innerHTML += `
            <div class="${cardClass}" style="position: relative; ${glowStyle}">
                ${rankBadge}
                <h4 style="margin-top: 0; color: ${isFailed ? 'var(--danger)' : 'inherit'};">${c.model}</h4>
                <p style="font-size: 0.9em; color: var(--text-muted);">${c.architecture.architecture_style || "Unknown Style"}</p>
                ${contentHtml}
            </div>
        `;
    });

    // Populate Ranking Table + full LLM logs
    populateRankingTable(data.candidates);
    renderLlmLogs(data.candidates);
}

// ─── Select Candidate (Phase 2 trigger) ──────
async function selectCandidate(run_id, candidate_idx) {
    updateStatus('Elaborating...', '#3B82F6');
    document.getElementById('tradeoffCard').classList.add('hidden');
    document.getElementById('progressSection').classList.remove('hidden');
    updateProgress(50, `Elaborating selected candidate...`);

    try {
        const candidate = currentResults.candidates[candidate_idx];
        if (!candidate) {
            throw new Error('Candidate not found in results');
        }
        
        const res = await fetch(`/api/runs/${run_id}/select`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: candidate.model,
                architecture: candidate.architecture,
                scores: candidate.scores
            })
        });
        
        if (!res.ok) throw new Error('Failed to elaborate architecture');
        const result = await res.json();

        currentResults.selectedCandidateIndex = candidate_idx;
        currentResults.phase2Result = result;
        
        updateProgress(100, '✅ Elaboration complete!');
        updateStatus('Complete', '#10B981');
        
        // Hide tradeoff, show winner
        displayFinalWinner(result);
        
    } catch (err) {
        updateProgress(0, `❌ Error: ${err.message}`);
        updateStatus('Error', '#EF4444');
    }
}

// ─── Display Final Winner (Phase 2) ────────
function displayFinalWinner(data) {
    document.getElementById('tradeoffCard').classList.add('hidden');
    document.getElementById('winnerCard').classList.remove('hidden');
    document.getElementById('componentsCard').classList.remove('hidden');
    document.getElementById('diagrams-section').classList.remove('hidden');
    document.getElementById('resultsRunId').textContent = `Run ID: ${data.run_id} — Phase 2 Complete`;

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
        
        const displayName = metric;
        
        metricsDiv.innerHTML += `
            <div class="metric-card fade-in">
                <div class="metric-name" title="${metric}">${displayName}</div>
                <div class="metric-value ${colorClass}">${val.toFixed(2)}</div>
                <div class="metric-bar"><div class="metric-bar-fill" style="width:${val*100}%;background:${barColor}"></div></div>
            </div>`;
    });

    renderComponents(winner.architecture.components);

    if (currentResults?.candidates) {
        populateRankingTable(currentResults.candidates);
    }

    // Phase 2 radar visualization based on final 5 metrics.
    document.getElementById('radarChart').style.display = 'block';
    document.getElementById('radarImage').style.display = 'none';
    renderRadarChart([{
        model: winner.model,
        candidate_num: 1,
        scores: winner.scores,
    }]);
    
    // Auto-switch to diagrams
    if (data.outputs) {
        currentRunId = data.run_id;
        loadDiagrams(data);
    }
}

function appendCliLog(line) {
    const box = document.getElementById('cliLog');
    if (!box) return;
    box.textContent = (box.textContent || '') + line + '\n';
    box.scrollTop = box.scrollHeight;
}

function populateRankingTable(candidates) {
    const tbody = document.getElementById('resultsBody');
    tbody.innerHTML = '';
    const selectedIndex = currentResults?.selectedCandidateIndex;
    candidates.forEach(c => {
        const s = c.scores;
        const rankClass = c.rank <= 3 ? `rank-${c.rank}` : '';
        const phase1Verdict = selectedIndex === undefined || selectedIndex === null
            ? (s.phase1_verdict || s.verdict)
            : (candidates[selectedIndex] === c ? 'Accepted' : 'Alternative');
        const verdictClass = phase1Verdict === 'Accepted' ? 'verdict-accepted' : (phase1Verdict === 'Marginal' || phase1Verdict === 'Alternative') ? 'verdict-marginal' : 'verdict-poor';
        const verdictIcon = phase1Verdict === 'Accepted' ? '✅' : (phase1Verdict === 'Marginal' || phase1Verdict === 'Alternative') ? '⚠️' : '❌';

        tbody.innerHTML += `<tr>
            <td><span class="rank-badge ${rankClass}">${c.rank === -1 ? 'F' : c.rank}</span></td>
            <td><strong>${c.model}</strong><br><small>Cand #${c.candidate_num}</small></td>
            <td>${c.architecture.architecture_style || "Unknown"}</td>
            <td>${s.RCR.toFixed(2)}</td>
            <td>${s.NAS.toFixed(2)}</td>
            <td><strong>${(s.PHASE1_CAS || 0).toFixed(4)}</strong></td>
            <td><span class="verdict-badge ${verdictClass}">${verdictIcon} ${phase1Verdict}</span></td>
        </tr>`;
    });
}

function renderLlmLogs(candidates) {
    const container = document.getElementById('llmLogsContainer');
    if (!container) return;

    container.innerHTML = '';
    candidates.forEach((candidate) => {
        const llm = candidate.llm || {};
        const attempts = llm.attempts || [];
        const attemptsHtml = attempts.length
            ? attempts.map(a => {
                const status = a.status || 'unknown';
                const dur = a.duration_ms ? `${a.duration_ms} ms` : '-';
                const chars = a.chars || 0;
                const err = a.error ? `<div class="llm-error">error: ${a.error}</div>` : '';
                return `<li>attempt ${a.attempt}: ${status}, duration=${dur}, chars=${chars}${err}</li>`;
            }).join('')
            : '<li>No attempt-level logs available.</li>';

        const raw = (llm.raw_text || candidate.raw_text || '').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
        const duration = llm.duration_ms ? `${Math.round(llm.duration_ms)} ms` : '-';

        container.innerHTML += `
            <details class="llm-log-item">
                <summary>
                    ${candidate.model} #${candidate.candidate_num} | provider=${llm.provider || 'unknown'} | duration=${duration}
                </summary>
                <div class="llm-log-meta">
                    <strong>attempts:</strong>
                    <ul>${attemptsHtml}</ul>
                </div>
                <div class="llm-log-meta"><strong>raw output:</strong></div>
                <pre class="llm-raw">${raw}</pre>
            </details>
        `;
    });
}

function renderComponents(components) {
    // Components grid
    const grid = document.getElementById('componentsGrid');
    grid.innerHTML = '';
    components.forEach(comp => {
        grid.innerHTML += `
            <div class="comp-card fade-in">
                <div class="comp-name">${comp.name}</div>
                <div class="comp-layer">${comp.layer}</div>
                <div class="comp-resp">${comp.responsibility}</div>
            </div>`;
    });
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
        'deepseek-v4-flash': { bg: 'rgba(0,122,255,0.2)', border: '#007AFF' },
        'deepseek-v4-pro': { bg: 'rgba(0,122,255,0.2)', border: '#007AFF' },
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
    await loadDiagramWorkflow(data.run_id);
}

function colorizeDiff(diffText) {
    return diffText
        .split('\n')
        .map(line => {
            const escaped = line.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
            if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) return `<span class="diff-context">${escaped}</span>`;
            if (line.startsWith('+') && !line.startsWith('+++')) return `<span class="diff-added">${escaped}</span>`;
            if (line.startsWith('-') && !line.startsWith('---')) return `<span class="diff-removed">${escaped}</span>`;
            return `<span class="diff-context">${escaped}</span>`;
        })
        .join('\n');
}

function renderDiagramWorkflow(wf) {
    diagramWorkflow = wf;

    const mermaidDiagram = document.getElementById('mermaidDiagram');
    const mermaidCode = document.getElementById('mermaidCode');
    const plantumlPanel = document.getElementById('plantumlPanel');

    // PlantUML panel
    plantumlPanel.classList.remove('hidden');
    const pu = (wf && wf.plantuml) ? wf.plantuml : {};
    const puCur = (pu && pu.current) ? pu.current : {};

    const approved = !!pu.approved;
    const used = Number(pu.llm_iterations_used || 0);
    const max = Number(pu.max_llm_iterations || 2);

    document.getElementById('plantumlStatus').textContent = `provider=${wf.provider || 'N/A'} • model=${wf.model || 'N/A'} • approved=${approved} • llm_iterations=${used}/${max}`;

    // Research-grade metrics display
    const metricsResearch = document.getElementById('plantumlMetricsResearch');
    const metricsDetail = puCur.metrics_detail || {};
    const scores = puCur.breakdown || {};
    
    if (metricsDetail && Object.keys(metricsDetail).length > 0) {
        metricsResearch.innerHTML = '';
        
        // Display all 5 metrics
        ['RCR', 'NAS', 'SMI', 'LSCS', 'SCI'].forEach(metric => {
            const score = scores[metric] || 0;
            const detail = metricsDetail[metric] || {};
            const scoreClass = score >= 0.8 ? 'high' : score >= 0.6 ? 'medium' : 'low';
            
            let detailsHtml = '';
            if (metric === 'RCR') {
                const covered = detail.covered || 0;
                const total = detail.total || 0;
                const uncovered = detail.uncovered || [];
                detailsHtml = `
                    <details class="metric-details">
                        <summary>Coverage Details</summary>
                        <div class="metric-breakdown">
                            <div class="breakdown-item"><span class="breakdown-label">Covered:</span><span class="breakdown-value">${covered}/${total}</span></div>
                            ${uncovered.length > 0 ? `<div class="breakdown-item"><span class="breakdown-label">Uncovered:</span><span class="breakdown-value">${uncovered.join(', ')}</span></div>` : ''}
                        </div>
                    </details>
                `;
            } else if (metric === 'NAS') {
                const aligned = detail.aligned_count || 0;
                const unaligned = detail.unaligned || [];
                detailsHtml = `
                    <details class="metric-details">
                        <summary>Alignment Details</summary>
                        <div class="metric-breakdown">
                            <div class="breakdown-item"><span class="breakdown-label">Aligned NFRs:</span><span class="breakdown-value">${aligned}</span></div>
                            ${unaligned.length > 0 ? `<div class="breakdown-item"><span class="breakdown-label">Unaligned:</span><span class="breakdown-value">${unaligned.join(', ')}</span></div>` : ''}
                        </div>
                    </details>
                `;
            } else if (metric === 'SMI') {
                const instability = detail.average_instability || 0;
                detailsHtml = `
                    <details class="metric-details">
                        <summary>Modularity Details</summary>
                        <div class="metric-breakdown">
                            <div class="breakdown-item"><span class="breakdown-label">Avg Instability:</span><span class="breakdown-value">${instability.toFixed(4)}</span></div>
                        </div>
                    </details>
                `;
            } else if (metric === 'LSCS') {
                const violations = detail.violations || 0;
                detailsHtml = `
                    <details class="metric-details">
                        <summary>Consistency Details</summary>
                        <div class="metric-breakdown">
                            <div class="breakdown-item"><span class="breakdown-label">Violations:</span><span class="breakdown-value">${violations}</span></div>
                        </div>
                    </details>
                `;
            } else if (metric === 'SCI') {
                const valid = detail.valid || 0;
                const total = detail.total || 0;
                detailsHtml = `
                    <details class="metric-details">
                        <summary>Clarity Details</summary>
                        <div class="metric-breakdown">
                            <div class="breakdown-item"><span class="breakdown-label">Valid Components:</span><span class="breakdown-value">${valid}/${total}</span></div>
                        </div>
                    </details>
                `;
            }
            
            metricsResearch.innerHTML += `
                <div class="metric-research">
                    <div class="label">${metric}</div>
                    <div class="value ${scoreClass}">${score.toFixed(4)}</div>
                    ${detailsHtml}
                </div>
            `;
        });
        
        metricsResearch.classList.remove('hidden');
    } else {
        metricsResearch.classList.add('hidden');
    }

    // Legacy metrics display
    const metrics = document.getElementById('plantumlMetrics');
    const cas = Number(puCur.diagram_cas || 0);
    const b = puCur.breakdown || {};
    metrics.innerHTML = `
        <div class="diagram-metric"><div class="k">Diagram_CAS</div><div class="v">${cas.toFixed(4)}</div></div>
    `;

    const editor = document.getElementById('plantumlEditor');
    editor.value = puCur.diagram || '';
    editor.disabled = approved;

    // Side-by-side diff display
    const diffHtmlContainer = document.getElementById('plantumlDiffHtml');
    const diffBox = document.getElementById('plantumlDiff');
    
    const diffHtml = puCur.diff_html || pu.last_diff_html || '';
    const diff = puCur.diff || pu.last_diff || '';
    
    if (diffHtml) {
        diffHtmlContainer.innerHTML = diffHtml;
        diffHtmlContainer.classList.remove('hidden');
    } else if (diff.trim()) {
        // Fallback to colorized unified diff
        diffHtmlContainer.innerHTML = '<p style="color: var(--text-muted); padding: 20px; text-align: center;">Side-by-side diff not available. See unified diff below.</p>';
        diffBox.innerHTML = colorizeDiff(diff);
    } else {
        diffHtmlContainer.innerHTML = '<p style="color: var(--text-muted); padding: 20px; text-align: center;">No diff available yet. Make an edit or request iteration 2.</p>';
        diffBox.textContent = 'No diff available yet.';
    }

    // Buttons
    const rescoreBtn = document.getElementById('plantumlRescoreBtn');
    const improveBtn = document.getElementById('plantumlImproveBtn');
    const approveBtn = document.getElementById('plantumlApproveBtn');

    rescoreBtn.disabled = approved;
    improveBtn.disabled = approved || used >= max;
    approveBtn.disabled = approved;
    approveBtn.textContent = approved ? 'Approved' : 'Approve PlantUML';

    // Mermaid panel
    if (!wf.mermaid || !wf.mermaid.generated) {
        mermaidDiagram.innerHTML = '<div style="color: var(--text-muted); font-size: 14px; text-align:center;">Mermaid is generated only after you approve the PlantUML.</div>';
        mermaidCode.textContent = '';
        mermaidCode.classList.add('hidden');
        return;
    }

    // Fetch Mermaid source and render + show copyable code
    fetch(`/api/results/${wf.run_id}/diagram/mermaid`)
        .then(res => res.ok ? res.json() : null)
        .then(d => {
            if (!d || !d.content) return;
            const mmd = d.content;
            mermaidCode.textContent = mmd;
            mermaidCode.classList.remove('hidden');
            mermaid.render('mermaidSvgApproved', mmd)
                .then(({ svg }) => { mermaidDiagram.innerHTML = svg; })
                .catch(() => { mermaidDiagram.innerHTML = `<pre style="color:#94a3b8">${mmd}</pre>`; });
        });
}

async function loadDiagramWorkflow(run_id) {
    try {
        const res = await fetch(`/api/results/${run_id}/diagram_workflow`);
        if (!res.ok) {
            // Workflow should exist after Phase 2, but keep UI resilient.
            document.getElementById('plantumlPanel').classList.add('hidden');
            document.getElementById('mermaidDiagram').innerHTML = '<div style="color: var(--text-muted); font-size: 14px; text-align:center;">No diagram workflow found for this run yet.</div>';
            return;
        }
        const wf = await res.json();
        renderDiagramWorkflow(wf);
    } catch (e) {
        console.error('Failed to load diagram workflow', e);
    }
}

async function rescorePlantUml() {
    if (!currentRunId) return;
    const diagram = document.getElementById('plantumlEditor').value;
    const res = await fetch(`/api/runs/${currentRunId}/diagram/plantuml/score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ diagram })
    });
    if (res.ok) {
        const wf = await res.json();
        renderDiagramWorkflow(wf);
    }
}

async function improvePlantUml() {
    if (!currentRunId) return;
    const res = await fetch(`/api/runs/${currentRunId}/diagram/plantuml/improve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });
    if (res.ok) {
        const wf = await res.json();
        renderDiagramWorkflow(wf);
    }
}

async function approvePlantUml() {
    if (!currentRunId) return;
    const res = await fetch(`/api/runs/${currentRunId}/diagram/plantuml/approve`, { method: 'POST' });
    if (res.ok) {
        const wf = await res.json();
        renderDiagramWorkflow(wf);
        showDiagramTab('mermaid');
    }
}

function showDiagramTab(tab) {
    const buttons = Array.from(document.querySelectorAll('.tab-btn'));
    buttons.forEach(b => b.classList.remove('active'));
    const idx = tab === 'plantuml' ? 1 : 0;
    const targetBtn = buttons[idx];
    if (targetBtn) targetBtn.classList.add('active');

    document.getElementById('mermaidDiagram').classList.toggle('hidden', tab !== 'mermaid');
    const mermaidCode = document.getElementById('mermaidCode');
    const shouldShowMermaidCode = tab === 'mermaid' && (mermaidCode.textContent || '').trim().length > 0;
    mermaidCode.classList.toggle('hidden', !shouldShowMermaidCode);

    document.getElementById('plantumlPanel').classList.toggle('hidden', tab !== 'plantuml');
    document.getElementById('plantumlDiagram').classList.add('hidden');
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
