from pathlib import Path


def patch_frontend(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    repls = [
        (
            """          <button class="menu-btn compact" data-tenant-section-btn="knowledge" onclick="switchTenantSection('knowledge')">
            <span class="menu-btn-icon compact"><span class="material-symbols-outlined text-[16px]">storage</span></span>
            <span class="menu-btn-title">知识资产</span>
          </button>
          <button class="menu-btn compact" data-tenant-section-btn="model" onclick="switchTenantSection('model')">""",
            """          <button class="menu-btn compact" data-tenant-section-btn="knowledge" onclick="switchTenantSection('knowledge')">
            <span class="menu-btn-icon compact"><span class="material-symbols-outlined text-[16px]">storage</span></span>
            <span class="menu-btn-title">知识资产</span>
          </button>
          <button class="menu-btn compact" data-tenant-section-btn="mcp" onclick="switchTenantSection('mcp')">
            <span class="menu-btn-icon compact"><span class="material-symbols-outlined text-[16px]">extension</span></span>
            <span class="menu-btn-title">MCP工具接入</span>
          </button>
          <button class="menu-btn compact" data-tenant-section-btn="model" onclick="switchTenantSection('model')">""",
        ),
        (
            """      knowledge: { title: '知识资产', subtitle: '按知识库、分类、文件与标签组织租户知识内容', badge: '知识资源' },
      model: { title: '模型与工具底座', subtitle: '管理模型、检索后端、Rerank 与 MCP 工具接入', badge: '底座能力' },""",
            """      knowledge: { title: '知识资产', subtitle: '按知识库、分类、文件与标签组织租户知识内容', badge: '知识资源' },
      mcp: { title: 'MCP 工具接入', subtitle: '管理外部系统连接，供智能体与工作流调用', badge: '外部连接' },
      model: { title: '模型与工具底座', subtitle: '管理模型、检索后端与 Rerank 配置', badge: '底座能力' },""",
        ),
        (
            """      knowledge: '/tenant/knowledge',
      model: '/tenant/model',""",
            """      knowledge: '/tenant/knowledge',
      mcp: '/tenant/mcp',
      model: '/tenant/model',""",
        ),
        (
            """      '/tenant/knowledge': 'knowledge',
      '/tenant/model': 'model',""",
            """      '/tenant/knowledge': 'knowledge',
      '/tenant/mcp': 'mcp',
      '/tenant/model': 'model',""",
        ),
        (
            """    function switchTenantSection(section, syncUrl = true) {
      if (syncUrl) {""",
            """    function switchTenantSection(section, syncUrl = true) {
      const paneSection = section === 'mcp' ? 'model' : section;
      if (syncUrl) {""",
        ),
        (
            """      document.querySelectorAll('[data-tenant-section]').forEach((pane) => {
        pane.classList.toggle('active', pane.dataset.tenantSection === section);
      });
      syncTenantHeader(section);
      if (section === 'knowledge') {
        loadTenantKnowledgeFiles();""",
            """      document.querySelectorAll('[data-tenant-section]').forEach((pane) => {
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
        }""",
        ),
        (
            """      const allowed = ['chat', 'branding', 'workflow', 'agents', 'knowledge', 'model', 'users', 'logs'];""",
            """      const allowed = ['chat', 'branding', 'workflow', 'agents', 'knowledge', 'mcp', 'model', 'users', 'logs'];""",
        ),
        (
            """          <details class="config-block">
            <summary class="config-header" style="cursor: pointer; outline: none;">
              <div class="config-step">7</div>""",
            """          <details class="config-block" id="tenant-mcp-config-block">
            <summary class="config-header" style="cursor: pointer; outline: none;">
              <div class="config-step">7</div>""",
        ),
        (
            """            <p class="field-desc">先在模型配置页的 MCP 工具接入里配置服务。</p>""",
            """            <p class="field-desc">先在左侧资源中心的 MCP 工具接入里配置服务。</p>""",
        ),
    ]
    for old, new in repls:
        if old not in text:
            raise RuntimeError(f"missing frontend pattern: {old[:80]!r}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def patch_backend(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = """@app.api_route("/tenant-model-v2", methods=["GET", "HEAD"])
@app.api_route("/tenant/model", methods=["GET", "HEAD"])
async def serve_tenant_model_v2():"""
    new = """@app.api_route("/tenant-model-v2", methods=["GET", "HEAD"])
@app.api_route("/tenant/model", methods=["GET", "HEAD"])
@app.api_route("/tenant/mcp", methods=["GET", "HEAD"])
async def serve_tenant_model_v2():"""
    if old not in text:
        raise RuntimeError("missing backend route pattern")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    patch_frontend(Path("/opt/lok/current/frontend/tenant_v2.html"))
    patch_backend(Path("/opt/lok/current/backend/main.py"))
    print("patched")
