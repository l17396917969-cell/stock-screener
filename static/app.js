document.addEventListener('DOMContentLoaded', () => {
    // API UI Elements (Legacy - kept for temporary override logic if needed, but removed from DOM)
    const apiKeyInput = document.getElementById('apikey');
    const capitalInput = document.getElementById('capital');

    // User Menu UI
    const userMenu = document.querySelector('.user-menu');
    const dropdownMenu = document.querySelector('.dropdown-menu');
    const keyStatusChips = document.getElementById('keyStatusChips');

    if (userMenu && dropdownMenu) {
        userMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdownMenu.style.display = dropdownMenu.style.display === 'block' ? 'none' : 'block';
        });
        document.addEventListener('click', () => dropdownMenu.style.display = 'none');
    }

    // Step 1 UI
    const step1Sectors = document.getElementById('step1-sectors');
    const btnFetchSectors = document.getElementById('btnFetchSectors');
    const aiReasoningArea = document.getElementById('aiReasoningArea');
    const aiReasoningText = document.getElementById('aiReasoningText');
    const sectorSelectionArea = document.getElementById('sectorSelectionArea');
    const sectorsCheckboxList = document.getElementById('sectorsCheckboxList');
    const btnFetchStocks = document.getElementById('btnFetchStocks');

    // Sector Watchlist UI
    const sectorWatchlistArea = document.getElementById('sectorWatchlistArea');
    const watchedSectorsChips = document.getElementById('watchedSectorsChips');
    const newWatchedSectorInput = document.getElementById('newWatchedSectorInput');
    const btnAddWatchedSector = document.getElementById('btnAddWatchedSector');
    const btnFetchWatchedStocks = document.getElementById('btnFetchWatchedStocks');

    let watchedSectorsList = [];

    // Step 2 UI
    const step2Stocks = document.getElementById('step2-stocks');
    const btnAnalyzeBatch = document.getElementById('btnAnalyzeBatch');
    const candidateCount = document.getElementById('candidateCount');
    const candidatesTbody = document.getElementById('candidatesTbody');

    // Step 3 UI
    const step3Analysis = document.getElementById('step3-analysis');
    const logTerminal = document.getElementById('logTerminal');
    const logBody = document.getElementById('logBody');
    const stockCardsArea = document.getElementById('stockCardsArea');
    const stockCardTemplate = document.getElementById('stockCardTemplate');

    // Watchlist UI
    const watchlistSection = document.getElementById('watchlist-section');
    const btnToggleWatchlist = document.getElementById('btnToggleWatchlist');
    const watchlistContent = document.getElementById('watchlistContent');
    const watchlistTbody = document.getElementById('watchlistTbody');
    const emptyWatchlistMsg = document.getElementById('emptyWatchlistMsg');
    const watchlistTable = document.getElementById('watchlistTable');

    let pollInterval = null;
    let localStep = 0;
    let renderedLogCount = 0;
    let deepseekState = {}; // Store DeepSeek queries: { '600000': { status: 'loading|done|error', content: '...' } }

    // Navigation UI
    const navScreener = document.getElementById('navScreener');
    const navWatchlist = document.getElementById('navWatchlist');
    const pageScreener = document.getElementById('pageScreener');
    const pageWatchlist = document.getElementById('pageWatchlist');

    // Global Header Reset Button (hijacking startBtn for reset)
    const startBtn = document.getElementById('startBtn');
    startBtn.textContent = '重置系统';
    startBtn.classList.remove('primary-btn');
    startBtn.classList.add('secondary-btn');

    // ---------------------------------------------------------
    // Navigation Logic
    // ---------------------------------------------------------
    if (navScreener && navWatchlist) {
        navScreener.addEventListener('click', () => {
            navScreener.classList.add('active');
            navWatchlist.classList.remove('active');
            pageScreener.classList.remove('hidden');
            pageScreener.classList.add('active');
            pageWatchlist.classList.add('hidden');
            pageWatchlist.classList.remove('active');
        });

        navWatchlist.addEventListener('click', () => {
            navWatchlist.classList.add('active');
            navScreener.classList.remove('active');
            pageWatchlist.classList.remove('hidden');
            pageWatchlist.classList.add('active');
            pageScreener.classList.add('hidden');
            pageScreener.classList.remove('active');
            // Refresh watchlist when switching to this tab
            fetchWatchlist();
        });
    }

    startBtn.addEventListener('click', async () => {
        if (confirm("确定要丢弃当前进度，重新开始分析吗？")) {
            await fetch('/api/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ capital: capitalInput.value })
            });
            window.location.reload();
        }
    });

    // ---------------------------------------------------------
    // Sector Watchlist Logic
    // ---------------------------------------------------------
    async function fetchWatchedSectors() {
        try {
            const res = await fetch('/api/watched_sectors');
            const data = await res.json();
            if (data.success) {
                watchedSectorsList = data.sectors || [];
                renderWatchedSectors();
            }
        } catch (e) { console.error("Failed to fetch watched sectors", e); }
    }

    function renderWatchedSectors() {
        if (!watchedSectorsChips) return;
        watchedSectorsChips.innerHTML = '';
        watchedSectorsList.forEach(sector => {
            const chip = document.createElement('div');
            chip.style.cssText = `
                display:flex; align-items:center; gap:0.5rem; 
                padding:0.25rem 0.75rem; background:rgba(0,240,255,0.1); 
                border:1px solid rgba(0,240,255,0.3); border-radius:15px;
                color:var(--cyan); font-size:0.8rem; font-family:var(--font-data);
            `;
            chip.innerHTML = `
                <span>${sector}</span>
                <span class="remove-sector-btn" data-sector="${sector}" style="cursor:pointer; font-weight:bold; color:var(--text-muted);">&times;</span>
            `;
            watchedSectorsChips.appendChild(chip);
        });

        // Bind remove events
        document.querySelectorAll('.remove-sector-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const s = e.target.dataset.sector;
                await fetch('/api/watched_sectors/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sector_name: s })
                });
                fetchWatchedSectors();
            });
        });
    }

    if (btnAddWatchedSector) {
        btnAddWatchedSector.addEventListener('click', async () => {
            const val = newWatchedSectorInput.value.trim();
            if (!val) return;
            const res = await fetch('/api/watched_sectors/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sector_name: val })
            });
            const data = await res.json();
            if (data.success) {
                newWatchedSectorInput.value = '';
                fetchWatchedSectors();
            }
        });
    }

    if (btnFetchWatchedStocks) {
        btnFetchWatchedStocks.addEventListener('click', async () => {
            if (watchedSectorsList.length === 0) {
                alert("自选板块列表为空，请先添加板块！");
                return;
            }
            btnFetchWatchedStocks.disabled = true;
            btnFetchWatchedStocks.textContent = "拉取中...";
            showLogTerminal();

            try {
                const res = await fetch('/api/step2_fetch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sectors: watchedSectorsList })
                });
                const data = await res.json();
                if (!data.success) {
                    alert(data.message);
                }
            } catch (e) {
                alert("请求失败");
                console.error(e);
            } finally {
                btnFetchWatchedStocks.disabled = false;
                btnFetchWatchedStocks.textContent = "直接拉取关注板块成分股";
            }
        });
    }

    // ---------------------------------------------------------
    // Event Listeners for Steps
    // ---------------------------------------------------------

    // Step 1: Fetch AI Sectors
    btnFetchSectors.addEventListener('click', async () => {
        btnFetchSectors.disabled = true;
        btnFetchSectors.textContent = "分析中...";
        showLogTerminal();

        try {
            const res = await fetch('/api/step1_macro', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}) // API keys loaded from user settings on server
            });
            const data = await res.json();
            if (!data.success) {
                alert(data.message);
                btnFetchSectors.disabled = false;
                btnFetchSectors.textContent = "启动宏观分析";
            }
        } catch (e) {
            alert("请求失败，详情控制台");
            console.error(e);
        }
    });

    // Step 2: Fetch Stocks for selected sectors
    btnFetchStocks.addEventListener('click', async () => {
        // Collect checked boxes
        const checkedBoxes = Array.from(sectorsCheckboxList.querySelectorAll('input:checked'));
        const selectedSectors = checkedBoxes.map(cb => cb.value);

        // Automatically merge watched sectors into the analysis pool
        if (typeof watchedSectorsList !== 'undefined' && watchedSectorsList.length > 0) {
            watchedSectorsList.forEach(ws => {
                if (!selectedSectors.includes(ws)) {
                    selectedSectors.push(ws);
                }
            });
        }

        if (selectedSectors.length === 0) {
            alert("请勾选主线板块或添加自选板块！");
            return;
        }
        btnFetchStocks.disabled = true;
        btnFetchStocks.textContent = "提取中...";
        showLogTerminal();

        try {
            const res = await fetch('/api/step2_fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sectors: selectedSectors })
            });
            const data = await res.json();
            if (!data.success) {
                alert(data.message);
                btnFetchStocks.disabled = false;
                btnFetchStocks.textContent = "提取成分股";
            }
        } catch (e) {
            alert("请求失败");
            console.error(e);
        }
    });

    // Step 3: Start Batch Analysis
    btnAnalyzeBatch.addEventListener('click', async () => {
        btnAnalyzeBatch.disabled = true;
        btnAnalyzeBatch.textContent = "批量审计中...";
        showLogTerminal();

        try {
            const res = await fetch('/api/step3_analyze_batch', { method: 'POST' });
            const data = await res.json();
            if (!data.success) {
                alert(data.message);
                btnAnalyzeBatch.disabled = false;
                btnAnalyzeBatch.textContent = "批量深度审计";
            }
        } catch (e) {
            alert("请求失败");
            console.error(e);
            btnAnalyzeBatch.disabled = false;
            btnAnalyzeBatch.textContent = "批量深度审计";
        }
    });


    // Delegated click for single stock analysis & Expansion
    candidatesTbody.addEventListener('click', async (e) => {
        // Handle Analysis Button
        if (e.target.classList.contains('btn-analyze-single')) {
            e.stopPropagation(); // Don't trigger row expansion
            const code = e.target.dataset.code;
            e.target.disabled = true;
            e.target.textContent = "扫描中...";
            showLogTerminal();

            try {
                await fetch('/api/step3_analyze_single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code })
                });
            } catch (err) {
                console.error(err);
                e.target.disabled = false;
                e.target.textContent = "开始审计";
            }
            return;
        }


    });

    // Delegated click for DeepSeek Analysis (can be in candidates table or final cards) and Row Expansion
    document.addEventListener('click', async (e) => {
        // Handle Row Expansion globally for any .main-row table
        const mainRow = e.target.closest('.main-row');
        // Do not expand/collapse if clicking on buttons, inputs, or selects inside the row
        if (mainRow && !e.target.closest('button') && !e.target.closest('input') && !e.target.closest('select')) {
            mainRow.classList.toggle('expanded');
        }
        // --- Watchlist Controls ---
        if (e.target.classList.contains('btn-toggle-watchlist')) {
            const btn = e.target;
            const code = btn.dataset.code;
            const name = btn.dataset.name || code;
            const sectorsStr = btn.dataset.sectors;
            const sectors = sectorsStr && sectorsStr !== 'undefined' ? JSON.parse(decodeURIComponent(sectorsStr)) : [];

            // Check if it's currently in watchlist by button text
            const isRemoving = btn.textContent.includes('移出') || btn.textContent.includes('已收藏');

            try {
                if (isRemoving) {
                    const res = await fetch('/api/watchlist/remove', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code })
                    });
                    const data = await res.json();
                    if (data.success) {
                        btn.textContent = "+ 添加自选";
                        fetchWatchlist(); // Refresh local list and UI
                    }
                } else {
                    const res = await fetch('/api/watchlist/add', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code, name, sectors })
                    });
                    const data = await res.json();
                    if (data.success) {
                        btn.textContent = "移出";
                        fetchWatchlist(); // Refresh local list and UI
                    }
                }
            } catch (err) { console.error(err); }
            return;
        }

        if (e.target.classList.contains('btn-wl-remove')) {
            const code = e.target.dataset.code;
            if (confirm(`确定将 ${code} 从自选中移除吗？`)) {
                try {
                    await fetch('/api/watchlist/remove', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code })
                    });
                    fetchWatchlist();
                } catch (err) { console.error(err); }
            }
            return;
        }

        if (e.target.classList.contains('btn-wl-audit')) {
            const code = e.target.dataset.code;
            e.target.disabled = true;
            e.target.textContent = "正在量化...";
            showLogTerminal();
            try {
                // Hits the same core logic but forces from Watchlist context
                await fetch('/api/watchlist/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code })
                });
                // The polling interval will pick up the new result in session_state,
                // and for the watchlist UI, it will refresh on the next fetchWatchlist
                fetchWatchlist();
            } catch (err) { console.error(err); }
            e.target.disabled = false;
            e.target.textContent = "重新量化";
            return;
        }

        // --- Watchlist Position Manager ---
        if (e.target.classList.contains('btn-wl-save')) {
            const code = e.target.dataset.code;
            const btn = e.target;

            const status = document.getElementById(`wl-status-${code}`).value;
            const cost_price = document.getElementById(`wl-cost-${code}`).value;
            const shares = document.getElementById(`wl-shares-${code}`).value;

            btn.textContent = "保存中...";
            btn.disabled = true;

            try {
                await fetch('/api/watchlist/update_position', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, status, cost_price, shares })
                });
                // Reload watchlist to reflect changes
                fetchWatchlist();
            } catch (err) { console.error(err); }
            finally {
                btn.textContent = "保存数据";
                btn.disabled = false;
            }
            return;
        }

        // --- Watchlist DeepSeek Diagnosis ---
        if (e.target.classList.contains('btn-wl-diagnose')) {
            const btn = e.target;
            const code = btn.dataset.code;
            const ds_key = document.getElementById('dskey') ? document.getElementById('dskey').value.trim() : '';
            const container = document.getElementById(`wl-ds-${code}`);

            btn.textContent = "AI 分析中...";
            btn.disabled = true;
            container.innerHTML = '<div class="cyber-spinner" style="margin: 0 auto; width: 30px; height: 30px; border: 2px solid var(--border-dim); border-top-color: var(--cyan); border-radius: 50%; animation: spin 0.8s linear infinite;"></div><p style="text-align:center; color:var(--text-secondary); font-size:0.8rem; margin-top:0.5rem;">正在生成综合深度诊断报告...</p>';

            try {
                const res = await fetch('/api/watchlist/ai_diagnose', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, ds_key })
                });
                const data = await res.json();

                if (data.success && data.markdown) {
                    container.innerHTML = marked.parse(data.markdown);
                } else {
                    container.innerHTML = `<span style="color:#ef4444;">${data.message || '分析失败'}</span>`;
                }
            } catch (err) {
                console.error(err);
                container.innerHTML = `<span style="color:#ef4444;">系统异常: ${err.message}</span>`;
            } finally {
                btn.textContent = "AI 深度诊断";
                btn.disabled = false;
                fetchWatchlist(); // refreshing in case we want to persist the cache logic
            }
            return;
        }

        // --- DeepSeek Analysis ---
        if (e.target.classList.contains('btn-ds-analyze')) {
            const btn = e.target;
            const code = btn.dataset.code;
            const ds_key = document.getElementById('dskey') ? document.getElementById('dskey').value.trim() : '';

            if (deepseekState[code] && deepseekState[code].status === 'loading') return;

            // Set state to loading and trigger an immediate UI re-render
            deepseekState[code] = { status: 'loading', content: '<span style="color:#94a3b8; font-style:italic;">深度诊断生成中，请稍候...</span>' };
            pollState();

            try {
                const res = await fetch('/api/deepseek_analysis', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, ds_key })
                });
                const data = await res.json();

                if (data.success && data.markdown) {
                    deepseekState[code] = { status: 'done', content: marked.parse(data.markdown) };
                } else {
                    deepseekState[code] = { status: 'error', content: `<span style="color:#ef4444;">${data.message || '分析失败'}</span>` };
                }
            } catch (err) {
                console.error(err);
                deepseekState[code] = { status: 'error', content: `<span style="color:#ef4444;">系统异常: ${err.message}</span>` };
            }
            pollState(); // Re-render when done
        }
    });


    // ---------------------------------------------------------
    // Polling & State Management
    // ---------------------------------------------------------

    async function pollState() {
        try {
            // Add timestamp to prevent aggressive browser caching
            const res = await fetch('/api/state?t=' + Date.now(), { cache: 'no-store' });
            const state = await res.json();
            syncUIWithState(state);
        } catch (e) {
            console.error("Polling error", e);
        }
    }

    function syncUIWithState(state) {
        // 1. Logs Binding
        if (state.logs && state.logs.length > renderedLogCount) {
            const newLogs = state.logs.slice(renderedLogCount);
            newLogs.forEach(entry => {
                const div = document.createElement('div');
                div.className = `log-entry ${entry.status || 'info'}`;
                div.innerHTML = `<span class="log-time">${entry.time}</span><span class="log-msg">${entry.msg}</span>`;
                logBody.appendChild(div);
            });
            renderedLogCount += newLogs.length;
            logBody.scrollTop = logBody.scrollHeight;
        }

        // 1.5 Render Key Status Chips
        if (keyStatusChips) {
            const fetchUserMe = async () => {
                if (keyStatusChips.dataset.loaded) return;
                const res = await fetch('/api/me');
                const me = await res.json();
                keyStatusChips.innerHTML = `
                    <div class="status-chip ${me.has_ds_key ? 'active' : ''}" title="${me.has_ds_key ? '已连接' : '未连接'}">DeepSeek</div>
                    <div class="status-chip ${me.has_gemini_key ? 'active' : ''}" title="${me.has_gemini_key ? '已连接' : '未连接'}">Gemini</div>
                `;
                keyStatusChips.dataset.loaded = "true";
            };
            fetchUserMe();
        }

        // 2. Global analyzing state
        btnFetchSectors.disabled = state.is_analyzing || state.step > 0;
        btnFetchStocks.disabled = state.is_analyzing || state.step > 1;
        btnAnalyzeBatch.disabled = state.is_analyzing || state.step < 2;

        if (state.is_analyzing) {
            if (state.step === 0) {
                btnFetchSectors.textContent = "正在思考中...";
                aiReasoningArea.classList.remove('hidden');
                if (!aiReasoningText.innerHTML.includes('cyber-spinner')) {
                    aiReasoningText.innerHTML = `
                        <div class="loading-state" style="text-align:center; padding: 2.5rem 1rem;">
                            <div class="cyber-spinner" style="margin: 0 auto 1.5rem; width: 45px; height: 45px; border: 3px solid var(--border-dim); border-top-color: var(--cyan); border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                            <p style="color: var(--cyan); font-weight: 500; font-family: var(--font-body); margin: 0;">
                                <span style="animation: pulse 2s infinite;">建立大模型连接中...</span><br>
                                <span style="font-size:0.9rem; color:var(--text-secondary); margin-top:0.75rem; display:block;">正在挂载大模型，扫描全市场及主力资金流向<br>此过程需建立通信并进行深度逻辑推演，约需 15~30 秒，请耐心等待。</span>
                            </p>
                            <style>
                                @keyframes spin { to { transform: rotate(360deg); } }
                                @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
                            </style>
                        </div>
                    `;
                }
            }
            if (state.step === 1) btnFetchStocks.textContent = "提取成分股中...";
            if (state.step === 2) btnAnalyzeBatch.textContent = `批量深度审计 (${state.batch_progress.current}/${state.batch_progress.total})`;
        } else {
            if (state.step >= 1) btnFetchSectors.textContent = "已锁定宏观板块";
            if (state.step >= 2) btnFetchStocks.textContent = "成分股提取完毕";
            if (state.step >= 2) btnAnalyzeBatch.textContent = "批量深度审计 (耗时较长)";
            if (state.step === 3) btnAnalyzeBatch.textContent = "批量审计完成";
        }

        // 3. Render Step UI based on State Progression
        if (state.step >= 1 && localStep < 1) {
            // Unlocked AI Reasoning & Sector Checkboxes
            localStep = 1;
            aiReasoningArea.classList.remove('hidden');
            aiReasoningText.innerHTML = (state.ai_reasoning || "无").replace(/\n/g, '<br>');

            sectorSelectionArea.classList.remove('hidden');
            sectorsCheckboxList.innerHTML = '';

            state.ai_sectors.forEach(sector => {
                const label = document.createElement('label');
                label.className = 'checkbox-label';
                // Note: user can't uncheck if it jumps past step 1
                const checkedAttr = state.step > 1 ? (state.selected_sectors.includes(sector) ? 'checked disabled' : 'disabled') : 'checked';
                label.innerHTML = `<input type="checkbox" value="${sector}" ${checkedAttr}><span>${sector}</span>`;
                sectorsCheckboxList.appendChild(label);
            });
        }

        if (state.step >= 2 && localStep < 2) {
            localStep = 2;
            step2Stocks.classList.remove('hidden');
            step3Analysis.classList.remove('hidden');
        }

        // Always refresh Table if step >= 2
        if (state.step >= 2) {
            candidateCount.textContent = state.candidate_stocks.length;
            renderCandidatesTable(state);
        }

        // Refresh Stock Cards
        if (state.analysis_results && Object.keys(state.analysis_results).length > 0) {
            renderStockCards(state);
        }
    }

    // DOM Diffing State
    const rowHtmlHashes = {};

    function renderSingleRowHTML(code, info, rs, state, isExpanded) {
        let statusHtml = '<span class="status-badge status-pending">待分析</span>';
        let actionHtml = `<button class="small-btn btn-analyze-single" data-code="${code}" ${state.is_analyzing ? 'disabled' : ''}>开始审计</button>`;
        let rowClass = '';

        if (rs) {
            if (rs.passed) {
                statusHtml = '<span class="status-badge status-passed">评估通过</span>';
                rowClass = 'passed';
            } else {
                const shortReason = (rs.reason || '').substring(0, 28);
                statusHtml = `<span class="status-badge status-failed" title="${rs.reason}">未通过: ${shortReason}</span>`;
                rowClass = 'failed';
            }
            actionHtml = `<button class="small-btn outline" disabled>已审计</button>`;
        }

        // Check if stock is in watchlist
        const isInWatchlist = state.watchlist && state.watchlist.some(s => s.code === code);
        const strSectors = encodeURIComponent(JSON.stringify(info.sectors || []));
        const wlBtnHtml = `<button class="small-btn btn-toggle-watchlist" 
                            data-code="${code}" 
                            data-name="${info.name}" 
                            data-sectors="${strSectors}">
                            ${isInWatchlist ? '移出自选' : '+ 添加自选'}
                           </button>`;

        return `
            <td class="stock-code-cell"><span class="expand-icon">▶</span>${code}</td>
            <td class="stock-name-cell">${info.name}</td>
            <td class="sector-cell">${(info.sectors || []).join(', ')}</td>
            <td>${statusHtml}</td>
            <td class="text-right flex items-center justify-end gap-2">
                ${wlBtnHtml}
                ${actionHtml}
            </td>
        `;
    }

    function renderSingleDetailsHTML(code, info, rs, state) {
        let detailsHtml = '';
        if (rs && rs.score_report) {
            const report = rs.score_report;
            const failureBanner = !rs.passed ? `
                <div class="failure-indicator-banner">
                    [WARN] 已触碰排雷红线：${rs.reason}。该股目前不符合选股标准，但量化打分过程已全部跑完以供参考。
                </div>
            ` : '';

            detailsHtml = `
                <div class="inner-report-container ${!rs.passed ? 'failed-report' : ''}">
                    ${failureBanner}
                    <div class="inner-report-header">
                        <h4 style="font-family: var(--font-heading); color: var(--cyan);">量化审计报告 :: ${info.name}</h4>
                        <div class="inner-report-score">
                            <span class="val">${report.total_score}</span>
                            <span class="total">/100</span>
                        </div>
                    </div>
                    <table class="audit-table">
                        <thead>
                            <tr>
                                <th>维度</th><th>指标</th><th>结果</th><th>证据</th><th class="text-right">加分</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${report.report.map(row => {
                let resClass = '';
                if (row.res.includes('[PASS]')) resClass = 'res-pass';
                else if (row.res.includes('[FAIL]')) resClass = 'res-fail';
                else if (row.res.includes('[WARN]')) resClass = 'res-warn';
                return `
                                    <tr>
                                        <td class="font-medium text-gray-500" style="font-size:0.7rem;">${row.dim}</td>
                                        <td class="font-semibold" style="color:#a0b0cc;">${row.name}</td>
                                        <td class="font-bold ${resClass}">${row.res}</td>
                                        <td class="text-xs" style="color:#526077;">${row.evidence}</td>
                                        <td class="text-right font-bold" style="color:#94a3b8;">${row.score !== '-' ? '+' + row.score : '-'}</td>
                                    </tr>
                                `;
            }).join('')}
                        </tbody>
                    </table>
                    ${report.trade_plan ? `
                        <div class="card-footer mt-4" style="background:var(--bg-card); border-radius:4px;">
                            <div class="trade-plan-box" style="padding: 1rem; border: 1px dashed var(--border-dim);">
                                <h4 style="color:var(--cyan); font-family: var(--font-body); font-size:0.85rem;">综合投资建议</h4>
                                <p style="font-size:0.9rem; color:var(--text-primary); font-family: var(--font-body); margin-top:0.5rem;">💡 ${report.trade_plan}</p>
                            </div>
                        </div>
                    ` : ''}
                    
                    <!-- DeepSeek Analysis Trigger -->
                    <div class="card-footer mt-4" style="background:rgba(255,255,255,0.03); border-radius:8px; border:none;">
                        ${getDsAnalysisHtml(code)}
                    </div>
                </div>
            `;
        } else if (rs) {
            detailsHtml = `<div class="inner-report-empty">已触碰排雷红线：${rs.reason}。数据获取受限，暂无评分。</div>`;
        } else {
            detailsHtml = `<div class="inner-report-empty">等待分析中，点击右侧「开始审计」生成深度报告。</div>`;
        }
        return detailsHtml;
    }

    function renderCandidatesTable(state) {
        state.candidate_stocks.forEach(code => {
            const info = state.stock_infos[code] || { name: code, sectors: [] };
            const rs = state.analysis_results[code];

            // 1. Get existing DOM nodes
            let mainRowNode = candidatesTbody.querySelector(`.main-row[data-code="${code}"]`);
            let detailsRowNode = candidatesTbody.querySelector(`.details-row[data-code="${code}"]`);
            const isExpanded = mainRowNode && mainRowNode.classList.contains('expanded');

            // 2. Compute Target HTML
            const mainHtml = renderSingleRowHTML(code, info, rs, state, isExpanded);
            const detailsHtmlStr = renderSingleDetailsHTML(code, info, rs, state);
            const detailsHtml = `
                <td colspan="5">
                    <div class="details-content">${detailsHtmlStr}</div>
                </td>
            `;

            // Row Class logic
            let rowClass = '';
            if (rs) {
                rowClass = rs.passed ? 'passed' : 'failed';
            }
            if (isExpanded) {
                rowClass += ' expanded';
            }

            // 3. Hash computation (simple string length combining state props usually suffices for this specific UI, but full string comparison is safer)
            const rowHash = mainHtml + detailsHtml + rowClass;

            if (rowHtmlHashes[code] === rowHash) {
                // No changes, skip DOM update
                return;
            }

            // Update hash memory
            rowHtmlHashes[code] = rowHash;

            // 4. Surgical DOM updates
            if (!mainRowNode) {
                // Append new elements if they don't exist
                mainRowNode = document.createElement('tr');
                mainRowNode.className = `main-row ${rowClass}`;
                mainRowNode.setAttribute('data-code', code);
                mainRowNode.innerHTML = mainHtml;
                candidatesTbody.appendChild(mainRowNode);

                detailsRowNode = document.createElement('tr');
                detailsRowNode.className = 'details-row';
                detailsRowNode.setAttribute('data-code', code);
                detailsRowNode.innerHTML = detailsHtml;
                candidatesTbody.appendChild(detailsRowNode);
            } else {
                // Update existing elements surgically
                mainRowNode.className = `main-row ${rowClass}`;
                mainRowNode.innerHTML = mainHtml;
                // Only update details body if the content actually changes to preserve text selection if possible
                if (detailsRowNode.innerHTML !== detailsHtml) {
                    detailsRowNode.innerHTML = detailsHtml;
                }
            }
        });
    }

    // Memory for Stock Cards
    const cardHtmlHashes = {};

    function renderStockCards(state) {
        // Extract array of PASSED score reports
        const passedReports = Object.values(state.analysis_results)
            .filter(r => r.passed && r.score_report)
            .map(r => r.score_report);

        // Sort by total score
        passedReports.sort((a, b) => b.total_score - a.total_score);

        // Keep track of which cards were rendered this cycle
        const renderedCodes = new Set();

        passedReports.forEach(report => {
            renderedCodes.add(report.symbol);

            let tbodyHtml = '';
            report.report.forEach(row => {
                let resClass = '';
                if (row.res.includes('[PASS]')) resClass = 'res-pass';
                else if (row.res.includes('[FAIL]')) resClass = 'res-fail';
                else if (row.res.includes('[WARN]')) resClass = 'res-warn';

                tbodyHtml += `
                    <tr>
                        <td class="font-medium text-gray-400" style="font-size:0.75rem;">${row.dim || ''}</td>
                        <td class="font-semibold text-gray-200" style="font-size:0.85rem;">${row.name}</td>
                        <td class="font-bold ${resClass}" style="font-size:0.85rem;">${row.res}</td>
                        <td class="text-xs text-gray-500" style="font-size:0.75rem;">${row.evidence}</td>
                        <td class="text-right font-bold text-gray-300">
                            ${row.score !== '-' ? '+' + row.score : '-'}
                        </td>
                    </tr>
                `;
            });

            const tradePlanHtml = report.trade_plan ? `
                <div class="trade-plan-box" style="padding: 1rem; border: 1px dashed var(--border-bright); margin-top: 1rem; background: rgba(0,0,0,0.3);">
                    <h4 style="color:var(--cyan); font-family: var(--font-data); font-size:0.75rem; text-transform:uppercase;">综合投资建议</h4>
                    <p class="trade-plan-text" style="font-size:0.85rem; color:var(--text-primary); font-family: var(--font-data); margin-top:0.5rem;">> ${report.trade_plan}</p>
                </div>
            ` : '';

            // Get DeepSeek status
            const dsHtml = getDsAnalysisHtml(report.symbol);

            // Get Chinese Name and Sectors from global state info
            const info = state.stock_infos[report.symbol] || { name: report.name, sectors: [report.sectors] };

            // Check if stock is in watchlist
            const isInWatchlist = state.watchlist && state.watchlist.some(s => s.code === report.symbol);
            const strSectors = encodeURIComponent(JSON.stringify(info.sectors || []));
            const wlBtnHtml = `<button class="secondary-btn btn-toggle-watchlist" style="padding: 0.2rem 0.75rem; font-size: 0.75rem;"
                                data-code="${report.symbol}" 
                                data-name="${info.name}" 
                                data-sectors="${strSectors}">
                                ${isInWatchlist ? '移出自选' : '+ 加入自选'}
                               </button>`;

            const cardInnerHtml = `
                <header class="card-header" style="justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h3 class="stock-name" style="font-family: 'Space Grotesk'; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 0.75rem;">
                            ${info.name} 
                            <span class="stock-code" style="color: var(--cyan); font-family: var(--font-data); font-size: 0.9rem;">(${report.symbol})</span>
                            ${wlBtnHtml}
                        </h3>
                        <p class="info-text" style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.5rem;">板块：<span class="sectors-text" style="color: #fff;">${info.sectors.join(', ')}</span></p>
                    </div>
                    <div class="score-badge">
                        <span class="score-value">${report.total_score}</span><span style="font-size: 0.8rem;">/100</span>
                    </div>
                </header>

                <div class="data-grid hidden"></div>

                <div class="inner-report-container" style="margin-top: 1rem; overflow-x: auto;">
                    <table class="audit-table" style="width: 100%; min-width: 480px; border-collapse: collapse; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-dim); font-size: 0.75rem; color: var(--text-secondary);">
                                <th style="padding: 0.5rem;">维度</th>
                                <th style="padding: 0.5rem;">指标名称</th>
                                <th style="padding: 0.5rem;">审计结果</th>
                                <th style="padding: 0.5rem;">依据/原始数据</th>
                                <th class="text-right" style="padding: 0.5rem;">评分</th>
                            </tr>
                        </thead>
                        <tbody class="audit-body">
                            ${tbodyHtml}
                        </tbody>
                    </table>
                    
                    ${tradePlanHtml}
                    
                    <div style="margin-top: 1.5rem;">
                        ${dsHtml}
                    </div>
                </div>
            `;

            if (cardHtmlHashes[report.symbol] === cardInnerHtml) {
                return; // No change for this card
            }
            cardHtmlHashes[report.symbol] = cardInnerHtml;

            let existingCard = stockCardsArea.querySelector(`.stock-card[data-code="${report.symbol}"]`);
            if (!existingCard) {
                existingCard = document.createElement('article');
                existingCard.className = 'stock-card';
                existingCard.setAttribute('data-code', report.symbol);
                existingCard.innerHTML = cardInnerHtml;
                stockCardsArea.appendChild(existingCard);
            } else {
                existingCard.innerHTML = cardInnerHtml;
            }
        });

        // Remove cards that are no longer in the passedReports (if any)
        Array.from(stockCardsArea.children).forEach(child => {
            const code = child.getAttribute('data-code');
            if (code && !renderedCodes.has(code)) {
                stockCardsArea.removeChild(child);
                delete cardHtmlHashes[code];
            }
        });
    }

    function getDsAnalysisHtml(code) {
        let dsState = deepseekState[code] || { status: 'idle', content: '' };
        let dsBtnText = "INITIATE DEEPSEEK SCAN";
        let dsBtnDisabled = "";
        let dsContainerClass = "hidden";

        if (dsState.status === 'loading') {
            dsBtnText = "AI 连接中...";
            dsBtnDisabled = "disabled";
            dsContainerClass = "";
        } else if (dsState.status === 'done') {
            dsBtnText = "分析完成 / 重新生成";
            dsContainerClass = "";
        } else if (dsState.status === 'error') {
            dsBtnText = "系统错误 / 重试";
            dsContainerClass = "";
        }

        return `
            <div class="ds-action-box" style="text-align: center;">
                <button class="primary-btn btn-ds-analyze" data-code="${code}" style="font-size: 0.85rem; padding: 0.5rem 1rem;" ${dsBtnDisabled}>${dsBtnText}</button>
            </div>
            <div class="ds-result-container ${dsContainerClass}" style="margin-top: 1rem; padding: 1.5rem; background: rgba(15, 23, 42, 0.4); border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.1);">
                <div class="ds-markdown-content text-left" style="font-size: 0.85rem; line-height: 1.6;">${dsState.content}</div>
            </div>
        `;
    }

    function showLogTerminal() {
        logTerminal.classList.remove('hidden');
        step3Analysis.classList.remove('hidden');
    }

    // --- Watchlist Functions ---
    if (btnToggleWatchlist) {
        btnToggleWatchlist.addEventListener('click', () => {
            watchlistContent.classList.toggle('hidden');
        });
    }

    async function manualAddWatchlistStock() {
        const input = document.getElementById('manualStockCodeInput');
        const code = input.value.trim();
        if (!code) {
            alert('请输入股票代码');
            return;
        }

        const btn = document.getElementById('btnManualAddStock');
        const originalText = btn.innerHTML;
        btn.innerHTML = '添加中...';
        btn.disabled = true;

        try {
            const res = await fetch('/api/watchlist/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, name: code, sectors: ['手动添加'] })
            });
            const data = await res.json();
            if (data.success) {
                input.value = '';
                fetchWatchlist(); // Refresh list
            } else {
                alert(data.message || '添加失败');
            }
        } catch (e) {
            console.error('Manual Add Error:', e);
            alert('请求错误');
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }

    // Bind event for manual adding
    const btnManualAdd = document.getElementById('btnManualAddStock');
    if (btnManualAdd) {
        btnManualAdd.addEventListener('click', manualAddWatchlistStock);
    }
    const inputManualAdd = document.getElementById('manualStockCodeInput');
    if (inputManualAdd) {
        inputManualAdd.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') manualAddWatchlistStock();
        });
    }

    // Bind event for price refresh
    const btnRefreshPrices = document.getElementById('btnRefreshPrices');
    if (btnRefreshPrices) {
        btnRefreshPrices.addEventListener('click', fetchWatchlist);
    }

    async function fetchWatchlist() {
        const btnRefresh = document.getElementById('btnRefreshPrices');
        const origBtnText = btnRefresh ? btnRefresh.innerHTML : '';
        if (btnRefresh) {
            btnRefresh.innerHTML = '<svg class="cyber-spinner" viewBox="0 0 50 50" style="width:16px;height:16px;vertical-align:middle;margin-right:8px;"><circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5"></circle></svg> 刷新中...';
            btnRefresh.disabled = true;
        }

        try {
            const res = await fetch('/api/watchlist?t=' + Date.now(), { cache: 'no-store' });
            const data = await res.json();
            if (data.success) {
                renderWatchlist(data.watchlist);
            }
        } catch (e) {
            console.error('Watchlist fetch error', e);
        } finally {
            if (btnRefresh) {
                btnRefresh.innerHTML = origBtnText;
                btnRefresh.disabled = false;
            }
        }
    }

    // Memory for Watchlist to prevent re-renders wiping out state
    const wlRowHtmlHashes = {};

    function renderWatchlist(watchlist) {
        const codes = Object.keys(watchlist);
        if (codes.length === 0) {
            emptyWatchlistMsg.classList.remove('hidden');
            watchlistTable.classList.add('hidden');
            return;
        }
        emptyWatchlistMsg.classList.add('hidden');
        watchlistTable.classList.remove('hidden');

        // Track rendered codes to clean up deleted ones
        const renderedWlCodes = new Set();

        codes.forEach(code => {
            renderedWlCodes.add(code);
            const info = watchlist[code];
            const sectors = info.sectors ? (Array.isArray(info.sectors) ? info.sectors.join(', ') : info.sectors) : '未知';

            // Status badge (if holding)
            const holdingBadge = info.status === 'holding'
                ? `<span style="background: var(--accent-blue); color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-left: 0.5rem; box-shadow: var(--shadow-sm);">已持仓</span>`
                : `<span style="background: var(--bg-surface); color: var(--text-secondary); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--border-dim); font-size: 0.7rem; margin-left: 0.5rem;">观察中</span>`;

            // 1. Entry Price
            let entryPriceHtml = `<span style="color:var(--text-secondary); font-weight: 500;">${info.entry_price ? info.entry_price.toFixed(2) : '--'}</span>`;

            // 2. Current Price
            let currentPriceHtml = `<span style="color:var(--text-primary); font-weight: 600; font-family: var(--font-data);">${info.current_price ? info.current_price.toFixed(2) : '--'}</span>`;

            // 3. Trend since added
            let trendHtml = `<span style="color:var(--text-muted);">--</span>`;
            if (info.entry_price && info.current_price) {
                let diff = info.current_price - info.entry_price;
                let pct = (diff / info.entry_price) * 100;
                let colorClass = pct > 0 ? 'text-red' : (pct < 0 ? 'text-green' : '');
                let sign = pct > 0 ? '+' : '';
                trendHtml = `<span class="${colorClass}" style="font-weight:700; font-family:var(--font-data);">${sign}${pct.toFixed(2)}%</span>`;
            }

            // If holding, overwrite the trend column with actual profit/loss based on cost_price
            if (info.status === 'holding' && info.cost_price && info.shares && info.current_price) {
                let diff = info.current_price - info.cost_price;
                let pct = (diff / info.cost_price) * 100;
                let totalProfit = diff * info.shares;
                let colorClass = pct > 0 ? 'text-red' : (pct < 0 ? 'text-green' : '');
                let sign = pct > 0 ? '+' : '';
                trendHtml = `
                    <div style="display:flex; flex-direction:column; line-height: 1.2;">
                        <span class="${colorClass}" style="font-weight:700; font-family:var(--font-data); font-size: 0.95rem;">${sign}${pct.toFixed(2)}%</span>
                        <span class="${colorClass}" style="font-size:0.75rem; opacity: 0.8;">¥${sign}${totalProfit.toFixed(1)}</span>
                    </div>
                `;
            }

            const mainHtml = `
                <td><span class="expand-icon">▶</span> <strong style="color:var(--accent-blue);">${code}</strong></td>
                <td style="font-weight: 600; display: flex; align-items: center;">${info.name} ${holdingBadge}</td>
                <td><span class="sector-tag" style="background: var(--bg-surface); border: 1px solid var(--border-dim); color: var(--text-secondary); font-size: 0.75rem;">${sectors}</span></td>
                <td>${entryPriceHtml}</td>
                <td>${currentPriceHtml}</td>
                <td>${trendHtml}</td>
                <td class="text-right">
                    <button class="secondary-btn btn-wl-audit" data-code="${code}" style="padding: 4px 10px; font-size: 0.8rem; border-radius: 6px;">重新量化</button>
                    <button class="secondary-btn btn-wl-remove" data-code="${code}" style="padding: 4px 10px; font-size: 0.8rem; border-color: #ff3b30; color: #ff3b30; border-radius: 6px;">移除</button>
                </td>
            `;

            const detailsHtmlStr = `
                <td colspan="6">
                    <div class="details-content" style="display:flex; flex-direction:column; gap: 1.5rem;">
                        
                        <!-- Row 1: Position Manager & AI Tactical Diagnosis -->
                        <div style="display:flex; gap: 1.5rem; flex-wrap: wrap;">
                            <!-- Left: Position Mananger -->
                            <div style="flex:1; min-width:320px; background: var(--bg-card); padding: 1.5rem; border: 1px solid var(--border-dim); border-radius: 8px; box-shadow: var(--shadow-sm);">
                                <h4 style="color:var(--accent-blue); margin-bottom: 1.5rem; font-family:var(--font-heading); font-size:1.05rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
                                    持仓管理信息
                                </h4>
                                
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 0.5rem; align-items:end;">
                                    <div style="grid-column: span 2;">
                                        <label style="display:block; font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.5rem; font-weight: 500;">持仓状态</label>
                                        <select id="wl-status-${code}" class="cyan-input" style="width:100%; padding: 0.65rem 1rem; background: var(--bg-surface); border: 1px solid var(--border-dim); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; outline: none; cursor: pointer; transition: all 0.2s;">
                                            <option value="watched" ${info.status !== 'holding' ? 'selected' : ''}>👀 持续观察</option>
                                            <option value="holding" ${info.status === 'holding' ? 'selected' : ''}>💼 建立底仓</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style="display:block; font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.5rem; font-weight: 500;">持仓成本价</label>
                                        <input type="number" id="wl-cost-${code}" value="${info.cost_price || ''}" placeholder="0.00" class="cyan-input" style="width:100%; padding: 0.65rem 1rem; background: var(--bg-surface); border: 1px solid var(--border-dim); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; outline: none; transition: all 0.2s;">
                                    </div>
                                    <div>
                                        <label style="display:block; font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.5rem; font-weight: 500;">持股数量 (股)</label>
                                        <input type="number" id="wl-shares-${code}" value="${info.shares || ''}" placeholder="0" class="cyan-input" style="width:100%; padding: 0.65rem 1rem; background: var(--bg-surface); border: 1px solid var(--border-dim); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; outline: none; transition: all 0.2s;">
                                    </div>
                                    <div style="grid-column: span 2; margin-top: 0.5rem;">
                                        <button class="primary-btn btn-wl-save" data-code="${code}" style="width:100%; padding: 0.8rem 1rem; font-size:0.9rem; font-weight: 600; border-radius: 6px; box-shadow: var(--shadow-sm); justify-content: center;">📝 保存数据</button>
                                    </div>
                                </div>
                            </div>

                            <!-- Right: AI Tactical Diagnosis -->
                            <div style="flex:1.8; min-width:400px; background: var(--bg-card); padding: 1.5rem; border: 1px solid var(--border-dim); border-radius: 8px; box-shadow: var(--shadow-sm);">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
                                    <h4 style="color:var(--text-primary); font-family:var(--font-heading); font-size:1.05rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                                        短线/中线深度研判建议
                                    </h4>
                                    <button class="primary-btn warning-bg btn-wl-diagnose" data-code="${code}" style="padding: 0.5rem 1rem; font-size:0.85rem; border-radius: 6px; box-shadow: var(--shadow-sm); display: flex; align-items: center; gap: 0.4rem;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                                        AI 深度诊断
                                    </button>
                                </div>
                                <div id="wl-ds-${code}" class="ds-markdown-content" style="font-size:0.9rem; line-height:1.7; background: var(--bg-base); padding: 1.25rem; border-radius: 6px; border: 1px solid var(--border-dim); color: var(--text-primary);">
                                    ${info.last_ai_analysis ? marked.parse(info.last_ai_analysis) : '<div style="color:var(--text-muted); font-style:italic; display:flex; align-items:center; justify-content:center; padding: 2rem 0; gap:0.5rem;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg> 等待生成研判报告...</div>'}
                                </div>
                            </div>
                        </div>

                        <!-- Row 2 (Full Width): Last Quantitative Audit Report -->
                        <div style="background: var(--bg-card); padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border-dim); box-shadow: var(--shadow-sm);">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.25rem;">
                                <h4 style="color:var(--text-secondary); font-family:var(--font-heading); font-size:1.05rem; font-weight:600; display:flex; align-items:center; gap:0.5rem; margin:0;">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                                    最新量化扫描快照
                                </h4>
                                ${info.last_audit_report && typeof info.last_audit_report.total_score !== 'undefined' ? `
                                    <div style="display:flex; align-items:center; gap: 1rem;">
                                        <span style="font-size: 1.25rem; font-weight: 700; color: ${info.last_audit_report.total_score >= 80 ? 'var(--accent-blue)' : (info.last_audit_report.total_score >= 60 ? 'var(--text-primary)' : 'var(--text-muted)')}">${info.last_audit_report.total_score}分 <span style="font-size:0.75rem; color:var(--text-secondary); font-weight:normal;">/ 综合得分</span></span>
                                        <span style="font-size:0.85rem; padding: 3px 10px; border-radius:12px; border: 1px solid var(--border-dim); color:var(--text-secondary);">${info.last_audit_report.report ? info.last_audit_report.report.filter(r => r.score > 0).length : 0}/${info.last_audit_report.report ? info.last_audit_report.report.length : 19} 项得分</span>
                                    </div>
                                ` : ''}
                            </div>
                            
                            ${info.last_audit_report && typeof info.last_audit_report.total_score !== 'undefined' ? `
                                ${info.last_audit_report.report ? `
                                <div style="overflow-x: auto;">
                                    <table class="audit-table" style="width: 100%; border-collapse: collapse; text-align: left;">
                                        <thead>
                                            <tr style="border-bottom: 1px solid var(--border-dim); font-size: 0.8rem; color: var(--text-secondary);">
                                                <th style="padding: 0.6rem 0.5rem;">维度</th>
                                                <th style="padding: 0.6rem 0.5rem;">指标名称</th>
                                                <th style="padding: 0.6rem 0.5rem;">审计结果</th>
                                                <th style="padding: 0.6rem 0.5rem;">依据/原始数据</th>
                                                <th class="text-right" style="padding: 0.6rem 0.5rem;">评分</th>
                                            </tr>
                                        </thead>
                                        <tbody class="audit-body">
                                            ${info.last_audit_report.report.map(row => {
                let resClass = '';
                if (row.res.includes('[PASS]')) resClass = 'res-pass';
                else if (row.res.includes('[FAIL]')) resClass = 'res-fail';
                else if (row.res.includes('[WARN]')) resClass = 'res-warn';

                return `
                                                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                                                        <td class="font-medium text-gray-400" style="font-size:0.75rem; padding: 0.5rem;">${row.dim || ''}</td>
                                                        <td class="font-semibold text-gray-200" style="font-size:0.85rem; padding: 0.5rem;">${row.name}</td>
                                                        <td class="font-bold ${resClass}" style="font-size:0.85rem; padding: 0.5rem;">${row.res}</td>
                                                        <td class="text-xs text-gray-500" style="font-size:0.75rem; padding: 0.5rem;">${row.evidence}</td>
                                                        <td class="text-right font-bold text-gray-300" style="font-size:0.85rem; padding: 0.5rem;">
                                                            ${row.score !== '-' ? '+' + row.score : '-'}
                                                        </td>
                                                    </tr>
                                                `;
            }).join('')}
                                        </tbody>
                                    </table>
                                </div>
                                ` : ''}
                            ` : '<span style="color:var(--text-muted); font-size:0.85rem;">暂无量化数据，请点击上方重新量化</span>'}
                        </div>
                    </div>
                </td>
            `;

            // Hash diffing to avoid destroying DOM/expanded states
            const wlHash = mainHtml + detailsHtmlStr;
            if (wlRowHtmlHashes[code] === wlHash) {
                return; // skip exactly identical DOM update
            }
            wlRowHtmlHashes[code] = wlHash;

            let mainRowNode = watchlistTbody.querySelector(`.main-row[data-code="${code}"]`);
            let detailsRowNode = watchlistTbody.querySelector(`.details-row[data-code="${code}"]`);
            const isExpanded = mainRowNode && mainRowNode.classList.contains('expanded');

            if (!mainRowNode) {
                mainRowNode = document.createElement('tr');
                mainRowNode.className = 'main-row';
                mainRowNode.dataset.code = code;
                mainRowNode.innerHTML = mainHtml;
                watchlistTbody.appendChild(mainRowNode);

                detailsRowNode = document.createElement('tr');
                detailsRowNode.className = 'details-row';
                detailsRowNode.dataset.code = code;
                detailsRowNode.innerHTML = detailsHtmlStr;
                watchlistTbody.appendChild(detailsRowNode);
            } else {
                mainRowNode.innerHTML = mainHtml;
                if (isExpanded) {
                    mainRowNode.classList.add('expanded');
                }

                // Diff update details to preserve typing state if user was typing in inputs
                // A complete outerHTML replacement destroys focused inputs
                const currentStatus = document.getElementById(`wl-status-${code}`);
                const hasFocus = currentStatus && (document.activeElement === currentStatus ||
                    document.activeElement === document.getElementById(`wl-cost-${code}`) ||
                    document.activeElement === document.getElementById(`wl-shares-${code}`));

                if (!hasFocus) {
                    detailsRowNode.innerHTML = detailsHtmlStr;
                }
            }
        });

        // Clean up deleted ones
        Array.from(watchlistTbody.children).forEach(child => {
            const code = child.getAttribute('data-code');
            if (code && !renderedWlCodes.has(code)) {
                watchlistTbody.removeChild(child);
                delete wlRowHtmlHashes[code];
            }
        });
    }

    // Start Polling immediately to catch up with any existing state on server
    fetchWatchedSectors();
    fetchWatchlist();
    pollInterval = setInterval(pollState, 1500);
    pollState();
});
