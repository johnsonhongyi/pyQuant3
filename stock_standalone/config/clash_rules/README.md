# 量化系统 Clash / Mihomo 专属直连规则备份与维护指南

## 📁 目录文件清单

1. **`clash_custom_direct_rules.yaml`**：
   * 适用于 Clash Verge Rev 的 **Merge 扩展配置**。
   * 包含新浪、腾讯、东方财富、同花顺、问财、三大交易所、巨潮资讯及通达信全部主站 IP 直连规则。
2. **`clash_custom_direct_script.js`**：
   * 适用于 Clash Verge Rev 的 **Script 扩展脚本**。
   * 采用 JavaScript 自动置顶注入直连规则，并注入 DNS 白名单。
   * 每次生成配置时都会把 ChatGPT/Codex 登录、验证和连接域名置于最前，并统一走 `Research + AI`；Edge 不再有进程级直连覆盖。
3. **`clash_dns_fakeip_filter.yaml`**：
   * DNS Fake-IP 过滤白名单，彻底防止 TUN 虚拟网卡把行情域名伪装为 `198.18.0.x`。
4. **`apply_clash_rules.py`**：
   * 一键将本目录备份规则自动覆盖并部署至系统的 Clash Verge Rev 配置文件中。
   * 同步对运行时配置做幂等补丁，确保上述同出口规则位于 `MATCH` 兜底之前。
5. **`一键恢复Clash直连规则.bat`**：
   * 位于 `stock_standalone` 根目录下，双击即可全自动恢复。

---

## 🚀 快速使用方法

### 方式 1：一键双击恢复（最快）
直接在项目根目录下双击运行 **`一键恢复Clash直连规则.bat`**。

### 方式 2：Python 命令行运行
```bash
python config/clash_rules/apply_clash_rules.py
```

### 方式 3：手动复制到 Clash Verge 客户端
1. 打开 Clash Verge Rev -> 进入左侧 **「订阅」**；
2. 点击中间卡片 **「全局扩展覆写配置」**；
3. 将 `clash_custom_direct_rules.yaml` 的内容复制粘贴进去，按 `Ctrl + S` 保存；
4. 点击左下角 **「设置」** -> **「重启核心 (Restart Core)」** 即可。

---

## 🔄 规则更新与迭代建议
若后续新增了其他券商专属行情服务器、私有 API 域名或数据源：
1. 直接在 `config/clash_rules/clash_custom_direct_rules.yaml` 中添加对应域名或 IP 段；
2. 运行 `apply_clash_rules.py` 或双击 bat 脚本；
3. 重启 Clash 核心即完成一键迭代更新。
