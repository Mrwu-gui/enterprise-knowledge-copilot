from pathlib import Path


FRONTEND = Path("/opt/lok/current/frontend/tenant_v2.html")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = FRONTEND.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """          <details class="config-block" id="tenant-mcp-config-block">
            <summary class="config-header" style="cursor: pointer; outline: none;">
              <div class="config-step">7</div>
              <div class="config-title-area">
                <h3 class="config-title">外部系统连接</h3>
                <p class="config-desc">把 HIS、EMR、CRM 等外部系统接进来后，智能体和工作流才能调用这些系统能力。</p>
              </div>
            </summary>
            <div class="form-grid">
              <div class="field-group">
                <label class="field-label" for="tenant-mcp-enabled">启用外部系统能力</label>
                <div class="custom-dropdown" data-value="false">
                  <input type="hidden" id="tenant-mcp-enabled" value="false">
                  <div class="dropdown-trigger" onclick="toggleTenantDropdown(this)">
                    <span class="val-label">否</span>
                    <span class="material-symbols-outlined transition-all transform duration-300">expand_more</span>
                  </div>
                  <div class="dropdown-menu">
                    <div class="dropdown-item" data-val="true" onclick="selectTenantDropdownItem(this)">是</div>
                    <div class="dropdown-item selected" data-val="false" onclick="selectTenantDropdownItem(this)">否 <span class="material-symbols-outlined text-[16px]">check_circle</span></div>
                  </div>
                </div>
              </div>
              <div class="field-group">
                <label class="field-label" for="tenant-mcp-timeout">接口超时（秒）</label>
                <input id="tenant-mcp-timeout" type="number" min="3" placeholder="30">
              </div>
            </div>
            <div class="field-group" style="margin-top:20px;">
              <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                <label class="field-label" style="margin:0;">连接列表</label>
                <button class="btn-secondary" type="button" onclick="addTenantMcpServerRow()" style="padding:6px 12px;font-size:12px;">新增连接</button>
              </div>
              <div class="field-desc">按表格填写连接 ID、显示名称、调用地址和 Token。缺少调用地址的连接会标记为待完善，不会生效。</div>
              <div id="tenant-mcp-servers-table-wrap" style="margin-top:12px;border:1px solid var(--line);border-radius:12px;overflow:hidden;"></div>
              <div id="tenant-mcp-server-preview" style="margin-top:14px; display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px;"></div>
            </div>
          </details>

          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-secondary" onclick="loadTenantModelConfig()">重新读取</button>
            <button class="btn-primary" onclick="saveTenantModelConfig()" style="padding: 12px 32px;">保存全局模型配置</button>
          </div>
        </div>
""",
        """          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-secondary" onclick="loadTenantModelConfig()">重新读取</button>
            <button class="btn-primary" onclick="saveTenantModelConfig()" style="padding: 12px 32px;">保存全局模型配置</button>
          </div>
        </div>

        <div class="card pane" data-tenant-section="mcp">
          <details class="config-block" id="tenant-mcp-config-block" open>
            <summary class="config-header" style="cursor: pointer; outline: none;">
              <div class="config-step">1</div>
              <div class="config-title-area">
                <h3 class="config-title">外部系统连接</h3>
                <p class="config-desc">把 HIS、EMR、CRM 等外部系统接进来后，智能体和工作流才能调用这些系统能力。</p>
              </div>
            </summary>
            <div class="form-grid">
              <div class="field-group">
                <label class="field-label" for="tenant-mcp-enabled">启用外部系统能力</label>
                <div class="custom-dropdown" data-value="false">
                  <input type="hidden" id="tenant-mcp-enabled" value="false">
                  <div class="dropdown-trigger" onclick="toggleTenantDropdown(this)">
                    <span class="val-label">否</span>
                    <span class="material-symbols-outlined transition-all transform duration-300">expand_more</span>
                  </div>
                  <div class="dropdown-menu">
                    <div class="dropdown-item" data-val="true" onclick="selectTenantDropdownItem(this)">是</div>
                    <div class="dropdown-item selected" data-val="false" onclick="selectTenantDropdownItem(this)">否 <span class="material-symbols-outlined text-[16px]">check_circle</span></div>
                  </div>
                </div>
              </div>
              <div class="field-group">
                <label class="field-label" for="tenant-mcp-timeout">接口超时（秒）</label>
                <input id="tenant-mcp-timeout" type="number" min="3" placeholder="30">
              </div>
            </div>
            <div class="field-group" style="margin-top:20px;">
              <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                <label class="field-label" style="margin:0;">连接列表</label>
                <button class="btn-secondary" type="button" onclick="addTenantMcpServerRow()" style="padding:6px 12px;font-size:12px;">新增连接</button>
              </div>
              <div class="field-desc">按表格填写连接 ID、显示名称、调用地址和 Token。缺少调用地址的连接会标记为待完善，不会生效。</div>
              <div id="tenant-mcp-servers-table-wrap" style="margin-top:12px;border:1px solid var(--line);border-radius:12px;overflow:hidden;"></div>
              <div id="tenant-mcp-server-preview" style="margin-top:14px; display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px;"></div>
            </div>
          </details>

          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-secondary" onclick="loadTenantMcpConfig()">重新读取</button>
            <button class="btn-primary" onclick="saveTenantMcpConfig()" style="padding: 12px 32px;">保存 MCP 配置</button>
          </div>
        </div>
""",
        "mcp pane split",
    )

    text = replace_once(
        text,
        """    function switchTenantSection(section, syncUrl = true) {
      const paneSection = section === 'mcp' ? 'model' : section;
      if (syncUrl) {
        const nextPath = tenantSectionPathMap[section] || '/tenant';
        const nextUrl = `${nextPath}${location.search || ''}`;
        if (`${location.pathname}${location.search || ''}` !== nextUrl) {
          history.replaceState(null, '', nextUrl);
        }
      }
      document.querySelectorAll('[data-tenant-section-btn]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.tenantSectionBtn === section);
      });
      document.querySelectorAll('[data-tenant-section]').forEach((pane) => {
        pane.classList.toggle('active', pane.dataset.tenantSection === paneSection);
      });
      syncTenantHeader(section);
      if (section === 'knowledge') {
        loadTenantKnowledgeFiles();
      } else if (section === 'mcp') {
        loadTenantModelConfig();
        const mcpBlock = document.getElementById('tenant-mcp-config-block');
        if (mcpBlock) {
          mcpBlock.open = true;
          requestAnimationFrame(() => {
            mcpBlock.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
        }
      } else if (section === 'workflow') {""",
        """    function switchTenantSection(section, syncUrl = true) {
      if (syncUrl) {
        const nextPath = tenantSectionPathMap[section] || '/tenant';
        const nextUrl = `${nextPath}${location.search || ''}`;
        if (`${location.pathname}${location.search || ''}` !== nextUrl) {
          history.replaceState(null, '', nextUrl);
        }
      }
      document.querySelectorAll('[data-tenant-section-btn]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.tenantSectionBtn === section);
      });
      document.querySelectorAll('[data-tenant-section]').forEach((pane) => {
        pane.classList.toggle('active', pane.dataset.tenantSection === section);
      });
      syncTenantHeader(section);
      if (section === 'knowledge') {
        loadTenantKnowledgeFiles();
      } else if (section === 'mcp') {
        loadTenantMcpConfig();
      } else if (section === 'workflow') {""",
        "switchTenantSection",
    )

    text = replace_once(
        text,
        """          loadTenantKnowledgeFiles(),
          loadTenantModelConfig(),
          loadTenantWorkflows(),""",
        """          loadTenantKnowledgeFiles(),
          loadTenantModelConfig(),
          loadTenantMcpConfig(),
          loadTenantWorkflows(),""",
        "bootstrapTenant",
    )

    old_block_start = "    async function loadTenantModelConfig() {"
    old_block_end = "\n\n    // ========== Workflow Module =========="
    start = text.find(old_block_start)
    end = text.find(old_block_end)
    if start == -1 or end == -1:
        raise RuntimeError("missing load/save block boundaries")
    new_block = """    async function loadTenantModelConfig() {
      const [modelRes, retrievalRes] = await Promise.all([
        tenantFetch('/api/tenant/model-config', { headers: tenantHeaders() }),
        tenantFetch('/api/tenant/retrieval-config', { headers: tenantHeaders() })
      ]);
      const modelData = await modelRes.json();
      const retrievalData = await retrievalRes.json();
      if (modelData.ok) {
        const providers = Array.isArray(modelData.config?.providers) && modelData.config.providers.length
          ? modelData.config.providers
          : [{
              id: 'provider_1',
              label: '供应商 1',
              base_url: modelData.config?.base_url || '',
              model_primary: modelData.config?.model_primary || '',
              supports_image: modelData.config?.supports_image === true,
              api_keys_text: modelData.api_keys_text || ''
            }];
        tenantRenderModelProviders(providers);
        renderTenantAgentModelOptions(document.getElementById('tenant-agent-model')?.value || '');
      }
      if (retrievalData.ok) {
        const cfg = retrievalData.config || {};
        const qdrant = cfg.qdrant || {};
        const embedding = cfg.embedding || {};
        const rerank = cfg.rerank || {};
        const sparse = cfg.sparse || {};
        const orchestration = cfg.orchestration || {};
        const rewrite = orchestration.rewrite || {};
        const judge = orchestration.judge || {};
        const retry = orchestration.retry || {};
        setTenantDropdownValue('tenant-retrieval-backend', cfg.backend || 'hybrid');
        setTenantDropdownValue('tenant-qdrant-enabled', String(Boolean(qdrant.enabled)));
        setTenantDropdownValue('tenant-qdrant-mode', qdrant.mode || 'local');
        document.getElementById('tenant-qdrant-url').value = qdrant.url || '';
        document.getElementById('tenant-qdrant-api-key').value = qdrant.api_key || '';
        document.getElementById('tenant-qdrant-path').value = qdrant.path || '';
        document.getElementById('tenant-qdrant-collection').value = qdrant.collection || '';
        document.getElementById('tenant-qdrant-vector-size').value = qdrant.vector_size || 1024;
        setTenantDropdownValue('tenant-qdrant-distance', qdrant.distance || 'Cosine');
        setTenantDropdownValue('tenant-sparse-enabled', String(Boolean(sparse.enabled)));
        document.getElementById('tenant-sparse-k1').value = sparse.k1 ?? 1.5;
        document.getElementById('tenant-sparse-b').value = sparse.b ?? 0.75;
        document.getElementById('tenant-dense-weight').value = sparse.dense_weight ?? 0.6;
        document.getElementById('tenant-sparse-weight').value = sparse.sparse_weight ?? 0.4;
        setTenantDropdownValue('tenant-embedding-provider', embedding.provider || 'siliconcloud');
        document.getElementById('tenant-embedding-model').value = embedding.model || '';
        document.getElementById('tenant-embedding-base-url').value = embedding.base_url || '';
        document.getElementById('tenant-embedding-api-key').value = embedding.api_key || '';
        setTenantDropdownValue('tenant-rerank-enabled', String(Boolean(rerank.enabled)));
        setTenantDropdownValue('tenant-rerank-provider', rerank.provider || 'siliconcloud');
        document.getElementById('tenant-rerank-model').value = rerank.model || '';
        document.getElementById('tenant-rerank-base-url').value = rerank.base_url || '';
        document.getElementById('tenant-rerank-api-key').value = rerank.api_key || '';
        document.getElementById('tenant-rerank-candidate-limit').value = rerank.candidate_limit || 20;
        document.getElementById('tenant-rerank-top-n').value = rerank.top_n || 5;
        setTenantDropdownValue('tenant-rewrite-enabled', String(rewrite.enabled !== false));
        setTenantDropdownValue('tenant-rewrite-expand', String(rewrite.expand_synonyms !== false));
        document.getElementById('tenant-judge-min-results').value = judge.min_results || 2;
        document.getElementById('tenant-judge-min-top-score').value = judge.min_top_score ?? 0.2;
        document.getElementById('tenant-judge-min-avg-score').value = judge.min_avg_score ?? 0.12;
        setTenantDropdownValue('tenant-retry-enabled', String(retry.enabled !== false));
        document.getElementById('tenant-retry-max-attempts').value = retry.max_attempts || 2;
        document.getElementById('tenant-retry-fallback-topk').value = retry.fallback_top_k || 8;
        syncAllTenantDropdownDisplays(document.querySelector('[data-tenant-section="model"]'));
        updateTenantQdrantVisibility();
      }
    }

    async function saveTenantModelConfig() {
      const providers = tenantCollectModelProviders();
      if (!providers.length) {
        tenantShowToast('⚠️ 请至少配置一个模型供应商', 'info');
        return;
      }
      const modelPromise = tenantFetch('/api/tenant/model-config', {
        method: 'PUT',
        headers: tenantHeaders(),
        body: JSON.stringify({
          providers,
          base_url: providers[0]?.base_url || '',
          model_primary: providers[0]?.model_primary || '',
          model_fallback: '',
          api_keys_text: providers.map(item => item.api_keys_text).filter(Boolean).join('\\n')
        })
      });
      const retrievalPromise = tenantFetch('/api/tenant/retrieval-config', {
        method: 'PUT',
        headers: tenantHeaders(),
        body: JSON.stringify({
          config: {
            backend: document.getElementById('tenant-retrieval-backend').value,
            qdrant: {
              enabled: document.getElementById('tenant-qdrant-enabled').value === 'true',
              mode: document.getElementById('tenant-qdrant-mode').value,
              url: document.getElementById('tenant-qdrant-url').value.trim(),
              api_key: document.getElementById('tenant-qdrant-api-key').value.trim(),
              path: document.getElementById('tenant-qdrant-path').value.trim(),
              collection: document.getElementById('tenant-qdrant-collection').value.trim(),
              vector_size: Number(document.getElementById('tenant-qdrant-vector-size').value || 1024),
              distance: document.getElementById('tenant-qdrant-distance').value || 'Cosine'
            },
            sparse: {
              enabled: document.getElementById('tenant-sparse-enabled').value === 'true',
              provider: 'bm25',
              k1: Number(document.getElementById('tenant-sparse-k1').value || 1.5),
              b: Number(document.getElementById('tenant-sparse-b').value || 0.75),
              dense_weight: Number(document.getElementById('tenant-dense-weight').value || 0.6),
              sparse_weight: Number(document.getElementById('tenant-sparse-weight').value || 0.4)
            },
            embedding: {
              provider: document.getElementById('tenant-embedding-provider').value,
              model: document.getElementById('tenant-embedding-model').value.trim(),
              base_url: document.getElementById('tenant-embedding-base-url').value.trim(),
              api_key: document.getElementById('tenant-embedding-api-key').value.trim()
            },
            rerank: {
              enabled: document.getElementById('tenant-rerank-enabled').value === 'true',
              provider: document.getElementById('tenant-rerank-provider').value,
              model: document.getElementById('tenant-rerank-model').value.trim(),
              base_url: document.getElementById('tenant-rerank-base-url').value.trim(),
              api_key: document.getElementById('tenant-rerank-api-key').value.trim(),
              candidate_limit: Number(document.getElementById('tenant-rerank-candidate-limit').value || 20),
              top_n: Number(document.getElementById('tenant-rerank-top-n').value || 5)
            },
            orchestration: {
              rewrite: {
                enabled: document.getElementById('tenant-rewrite-enabled').value === 'true',
                expand_synonyms: document.getElementById('tenant-rewrite-expand').value === 'true'
              },
              judge: {
                min_results: Number(document.getElementById('tenant-judge-min-results').value || 2),
                min_top_score: Number(document.getElementById('tenant-judge-min-top-score').value || 0.2),
                min_avg_score: Number(document.getElementById('tenant-judge-min-avg-score').value || 0.12)
              },
              retry: {
                enabled: document.getElementById('tenant-retry-enabled').value === 'true',
                max_attempts: Number(document.getElementById('tenant-retry-max-attempts').value || 2),
                fallback_top_k: Number(document.getElementById('tenant-retry-fallback-topk').value || 8)
              }
            }
          }
        })
      });
      const [modelRes, retrievalRes] = await Promise.all([modelPromise, retrievalPromise]);
      const modelData = await modelRes.json();
      const retrievalData = await retrievalRes.json();
      if (modelData.ok && retrievalData.ok) {
        tenantShowToast('✅ 模型与检索核心配置已刷新并保存', 'success');
        loadTenantModelConfig();
      } else {
        tenantShowToast(`❌ 配置保存失败: ${modelData.msg || retrievalData.msg}`, 'error');
      }
    }

    async function loadTenantMcpConfig() {
      const toolRes = await tenantFetch('/api/tenant/tool-config', { headers: tenantHeaders() });
      const toolData = await toolRes.json();
      if (!toolData.ok) return;
      const mcp = toolData.config?.mcp || {};
      setTenantDropdownValue('tenant-mcp-enabled', String(Boolean(mcp.enabled)));
      document.getElementById('tenant-mcp-timeout').value = mcp.request_timeout_seconds || 30;
      tenantMcpServerDrafts = normalizeTenantMcpServers(mcp.servers || []);
      renderTenantMcpServersTable();
      renderTenantMcpServerPreview(tenantMcpServerDrafts);
      tenantAvailableMcpServers = Array.isArray(mcp.servers)
        ? mcp.servers
            .filter((item) => item && item.enabled !== false && (item.server_id || item.id))
            .map((item) => ({
              server_id: String(item.server_id || item.id || '').trim(),
              label: String(item.label || item.server_id || item.id || '').trim(),
              transport: String(item.transport || ((item.bridge_url || item.url) ? 'http' : 'stdio')).trim().toLowerCase() || 'http',
              bridge_url: String(item.bridge_url || item.url || '').trim(),
              command: String(item.command || '').trim(),
            }))
        : [];
      syncAllTenantDropdownDisplays(document.querySelector('[data-tenant-section="mcp"]'));
    }

    async function saveTenantMcpConfig() {
      const toolRes = await tenantFetch('/api/tenant/tool-config', {
        method: 'PUT',
        headers: tenantHeaders(),
        body: JSON.stringify({
          config: {
            mcp: {
              enabled: document.getElementById('tenant-mcp-enabled').value === 'true',
              request_timeout_seconds: Number(document.getElementById('tenant-mcp-timeout').value || 30),
              servers: getTenantMcpServersFromTable()
            }
          }
        })
      });
      const toolData = await toolRes.json();
      if (toolData.ok) {
        tenantShowToast('✅ MCP 配置已保存', 'success');
        loadTenantMcpConfig();
      } else {
        tenantShowToast(`❌ MCP 配置保存失败: ${toolData.msg || '请稍后重试'}`, 'error');
      }
    }"""
    text = text[:start] + new_block + text[end:]

    FRONTEND.write_text(text, encoding="utf-8")
    print("patched")


if __name__ == "__main__":
    main()
