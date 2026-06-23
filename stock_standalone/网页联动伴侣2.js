// ==UserScript==
// @name         网页股票联动伴侣2
// @namespace    http://tampermonkey.net/
// @version      8.4
// @description  高效精准高亮 A 股股票代码与中文股票名称，并支持复制联动
// @author       John
// @match        *://*/*
// @grant        GM_addStyle
// @grant        GM_setClipboard
// @grant        GM_xmlhttpRequest
// @connect      file
// @connect      127.0.0.1
// ==/UserScript==

(function () {
    'use strict';

    if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
        return;
    }

    /* ================= 股票正则与中文映射 ================= */

    // 仅用于全文扫描（exec）
    const STOCK_SCAN_REGEX =
        /\b(00\d{4}|30\d{4}|60\d{4}|68\d{4}|43\d{4}|83\d{4}|87\d{4}|92\d{4})\b/g;

    let codeToNameMap = {};
    let nameToCodeMap = {};
    let STOCK_NAME_REGEX = null;

    // 将全角字母/数字转换为半角
    function toHalfWidth(str) {
        return str.replace(/[\uff01-\uff5e]/g, function (ch) {
            return String.fromCharCode(ch.charCodeAt(0) - 0xfee0);
        }).replace(/\u3000/g, ' ');
    }

    // 规范化股票名字（去除空格、全角转半角、转大写），用于无视格式进行匹配 and 映射查找
    function normalizeNameForLookup(name) {
        return toHalfWidth(name).replace(/\s+/g, '').toUpperCase();
    }

    // 获取单个字符的正则模式（支持全/半角英数字，忽略大小写）
    function getCharacterPattern(char) {
        const hw = toHalfWidth(char);
        if (/[a-zA-Z]/.test(hw)) {
            const lowerHw = hw.toLowerCase();
            const upperHw = hw.toUpperCase();
            const lowerFw = String.fromCharCode(lowerHw.charCodeAt(0) + 0xfee0);
            const upperFw = String.fromCharCode(upperHw.charCodeAt(0) + 0xfee0);
            return `[${lowerHw}${upperHw}${lowerFw}${upperFw}]`;
        }
        if (/[0-9]/.test(hw)) {
            const fw = String.fromCharCode(hw.charCodeAt(0) + 0xfee0);
            return `[${hw}${fw}]`;
        }
        return hw.replace(/[.*+?^${}()|[\\\]]/g, '\\$&');
    }

    // 构建能模糊匹配空格及全/半角的正则模式
    function buildRegexPattern(name) {
        const cleanName = name.replace(/\s+/g, '');
        const chars = Array.from(cleanName);
        const patternParts = chars.map((char, index) => {
            const charPat = getCharacterPattern(char);
            // 允许字符之间有可选的空格
            return charPat + (index < chars.length - 1 ? '\\s*' : '');
        });
        return patternParts.join('');
    }

    // 加载本地股票名称缓存
    function loadStockNames() {
        if (typeof GM_xmlhttpRequest === 'undefined') {
            console.warn('[网页股票联动伴侣] 未检测到 GM_xmlhttpRequest，无法读取本地股票名称缓存。');
            return;
        }

        const localUrl = "http://127.0.0.1:26672/stock_names";
        const fileUrl = "file:///D:/JohnsonProgram/instockMonitorTK/datacsv/stock_name_cache.json";

        function parseData(responseText, sourceName) {
            try {
                const data = JSON.parse(responseText);
                let loadedCount = 0;
                codeToNameMap = {};
                nameToCodeMap = {};
                for (const [code, name] of Object.entries(data)) {
                    if (code && name && typeof name === 'string') {
                        const trimmedName = name.trim();
                        if (trimmedName && trimmedName !== '-' && !trimmedName.startsWith("个股_")) {
                            codeToNameMap[code] = trimmedName;
                            // 键名存入规范化后的股票名字，用于在 applyHighlight 中极速查找
                            const normName = normalizeNameForLookup(trimmedName);
                            nameToCodeMap[normName] = code;
                            loadedCount++;
                        }
                    }
                }

                // 按照长度从长到短排序，防止子串匹配冲突（例如“深南电A”优先于“深南电”）
                const names = Object.keys(nameToCodeMap);
                if (names.length > 0) {
                    names.sort((a, b) => b.length - a.length);

                    // 构建支持空格、全/半角模糊匹配的大正则表达式
                    const patterns = names.map(buildRegexPattern);
                    STOCK_NAME_REGEX = new RegExp(patterns.join('|'), 'g');
                    console.log(`[网页股票联动伴侣] 成功通过 ${sourceName} 加载 ${loadedCount} 个股票名称，已启用中文联动高亮！`);

                    // 暴露到全局，便于 F12 调试
                    const debugObj = { codeToNameMap, nameToCodeMap, STOCK_NAME_REGEX };
                    if (typeof unsafeWindow !== 'undefined') unsafeWindow.__stock_helper = debugObj;
                    window.__stock_helper = debugObj;

                    // 加载成功后立即触发一次高亮
                    trigger();
                    return true;
                }
            } catch (e) {
                console.error(`[网页股票联动伴侣] 解析 ${sourceName} 数据失败:`, e);
            }
            return false;
        }

        // 优先通道：本地 HTTP API
        try {
            console.log("[网页股票联动伴侣] 尝试连接本地 HTTP 端口服务...");
            GM_xmlhttpRequest({
                method: "GET",
                url: localUrl,
                timeout: 2000,
                onload: function (response) {
                    if (response.status === 200 && parseData(response.responseText, "本地 HTTP 服务")) {
                        return;
                    }
                    fallbackToFile();
                },
                onerror: function (err) {
                    console.log("[网页股票联动伴侣] 本地 HTTP 端口不可用，尝试读取本地文件...");
                    fallbackToFile();
                },
                ontimeout: function () {
                    console.log("[网页股票联动伴侣] 本地 HTTP 端口超时，尝试读取本地文件...");
                    fallbackToFile();
                }
            });
        } catch (e) {
            console.warn("[网页股票联动伴侣] 本地 HTTP 接口异常:", e);
            fallbackToFile();
        }

        // 次优先通道：本地文件协议
        function fallbackToFile() {
            try {
                console.log("[网页股票联动伴侣] 尝试通过 file:// 协议读取本地文件...");
                GM_xmlhttpRequest({
                    method: "GET",
                    url: fileUrl,
                    onload: function (response) {
                        parseData(response.responseText, "本地文件缓存");
                    },
                    onerror: function (err) {
                        console.warn(
                            "[网页股票联动伴侣] 加载本地股票缓存失败。如果您不需要中文股票名联动，可忽略此警告。\n" +
                            "如需启用中文名称联动，请确保：\n" +
                            "1. 本地监控软件已启动（本地 HTTP 服务正在运行）\n" +
                            "2. 或本地文件存在且在 Tampermonkey 设置中开启了「允许访问文件网址」"
                        );
                    }
                });
            } catch (fileErr) {
                console.error("[网页股票联动伴侣] 读取 file:// 本地文件协议异常:", fileErr);
            }
        }
    }

    // 启动时异步加载
    loadStockNames();

    /* ================= 样式 ================= */

    GM_addStyle(`
        .stock-highlight {
            color: #ff3b30 !important;
            font-weight: bold !important;
            cursor: pointer !important;
            background: #fff3cd !important;
            padding: 1px 3px !important;
            border-radius: 3px !important;
        }
        .stock-highlight:hover {
            background: #ffe082 !important;
        }
    `);

    /* ================= 已处理节点缓存 ================= */

    const processedNodes = new WeakSet();

    /* ================= Walker ================= */

    class ContextualWalker {
        constructor(root, regex, handler) {
            this.root = root;
            this.regex = regex;
            this.handler = handler;
            this.textNodes = [];
            this.scan();
            this.process();
        }

        scan() {
            const walker = document.createTreeWalker(
                this.root,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: node => {
                        const p = node.parentElement;
                        if (!p) return NodeFilter.FILTER_REJECT;
                        if (processedNodes.has(node)) return NodeFilter.FILTER_REJECT;
                        if (['SCRIPT', 'STYLE', 'TEXTAREA', 'NOSCRIPT'].includes(p.tagName))
                            return NodeFilter.FILTER_REJECT;
                        if (p.closest('.stock-highlight')) return NodeFilter.FILTER_REJECT;
                        if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );

            while (walker.nextNode()) {
                this.textNodes.push(walker.currentNode);
            }
        }

        process() {
            for (let i = 0; i < this.textNodes.length; i++) {
                const base = this.textNodes[i];
                if (processedNodes.has(base)) continue;

                let ctx = { text: '', nodes: [] };

                for (let j = i; j < this.textNodes.length; j++) {
                    const n = this.textNodes[j];
                    if (processedNodes.has(n)) break;
                    if (ctx.nodes.length &&
                        !this.isAdjacent(ctx.nodes[ctx.nodes.length - 1], n)
                    ) break;

                    ctx.text += n.nodeValue;
                    ctx.nodes.push(n);
                }

                if (ctx.text) {
                    this.handler(ctx, this.regex);
                }
            }
        }

        isAdjacent(a, b) {
            let n = a.nextSibling;
            while (n) {
                if (n === b) return true;
                if (n.nodeType === 3 && !n.nodeValue.trim()) {
                    n = n.nextSibling;
                    continue;
                }
                return false;
            }
            return false;
        }
    }

    /* ================= 高亮实现 ================= */

    function applyHighlight(ctx, regex, isName = false) {
        let match;
        regex.lastIndex = 0;
        let matchedAny = false;

        while ((match = regex.exec(ctx.text)) !== null) {
            const matchedText = match[0];
            if (!matchedText) continue;

            const code = isName ? nameToCodeMap[normalizeNameForLookup(matchedText)] : matchedText;
            if (!code) continue;

            const start = match.index;
            const end = start + matchedText.length;

            let count = 0;
            let sNode, eNode, sOff, eOff;

            for (const n of ctx.nodes) {
                const len = n.nodeValue.length;
                if (!sNode && count + len > start) {
                    sNode = n;
                    sOff = start - count;
                }
                if (count + len >= end) {
                    eNode = n;
                    eOff = end - count;
                    break;
                }
                count += len;
            }

            if (!sNode || !eNode) continue;

            const range = document.createRange();
            range.setStart(sNode, sOff);
            range.setEnd(eNode, eOff);

            if (range.cloneContents().querySelector('.stock-highlight')) continue;

            const span = document.createElement('span');
            span.className = 'stock-highlight';
            span.textContent = matchedText;
            span.dataset.code = code;

            if (isName) {
                span.title = `点击联动股票代码: ${code}`;
            }

            range.deleteContents();
            range.insertNode(span);
            matchedAny = true;
        }

        // 只有确实产生了高亮替换，才将这些节点标为已处理
        // 未高亮的节点必须放行，以便数字高亮能继续扫描处理它们
        if (matchedAny) {
            ctx.nodes.forEach(n => processedNodes.add(n));
        }
    }

    /* ================= 点击复制 ================= */

    document.body.addEventListener('click', e => {
        const el = e.target.closest('.stock-highlight');
        if (!el) return;
        e.stopPropagation();
        
        const code = el.dataset.code;
        
        // 尝试通过 HTTP 联动接口调用本地系统联动能力
        GM_xmlhttpRequest({
            method: 'GET',
            url: `http://127.0.0.1:26672/link?code=${code}`,
            timeout: 800,
            onload: function(response) {
                let success = false;
                try {
                    if (response.status === 200) {
                        const resJson = JSON.parse(response.responseText);
                        if (resJson.status === 'ok') {
                            success = true;
                            console.log('[Stock Linked via HTTP]', code);
                        }
                    }
                } catch(err) {}
                
                if (!success) {
                    fallbackCopy(code);
                }
            },
            onerror: function() {
                fallbackCopy(code);
            },
            ontimeout: function() {
                fallbackCopy(code);
            }
        });
    }, true);

    function fallbackCopy(code) {
        GM_setClipboard(code, 'text');
        console.log('[Stock Copied (Fallback)]', code);
    }

    /* ================= 扫描调度 ================= */

    let timer;
    function trigger() {
        clearTimeout(timer);
        timer = setTimeout(() => {
            // 1. 如果启用了中文股票名正则，优先高亮中文股票名
            if (STOCK_NAME_REGEX) {
                new ContextualWalker(document.body, STOCK_NAME_REGEX, (ctx, regex) => {
                    applyHighlight(ctx, regex, true);
                });
            }
            // 2. 高亮数字股票代码
            new ContextualWalker(document.body, STOCK_SCAN_REGEX, (ctx, regex) => {
                applyHighlight(ctx, regex, false);
            });
        }, 400);
    }

    const mo = new MutationObserver(trigger);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });

    window.addEventListener('load', () => setTimeout(trigger, 800));
})();