// ==UserScript==
// @name         网页股票联动伴侣
// @namespace    http://tampermonkey.net/
// @version      8.3-debug
// @description  股票高亮 + Debug 可视化
// @author       John
// @match        *://*/*
// @grant        GM_addStyle
// @grant        GM_setClipboard
// ==/UserScript==

(function () {
    'use strict';

    if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
        return;
    }

    // ========================
    // Debug 开关控制（键盘 + 鼠标兜底）
    // ========================

    let DEBUG = false;

    /* ---------- 键盘：Ctrl + Alt + E ---------- */
    window.addEventListener('keydown', e => {
        if (
            e.ctrlKey &&
            e.altKey &&
            (
                e.key === 'e' ||
                e.key === 'E' ||
                e.code === 'KeyE'
            )
        ) {
            DEBUG = !DEBUG;
            console.warn(`[Stock Debug] ${DEBUG ? 'ON' : 'OFF'} (keyboard)`);
        }
    }, true); // 使用 capture，避免被页面拦截


    /* ---------- 鼠标：左键三击（500ms 内） ---------- */
    let clickCount = 0;
    let clickTimer = null;

    document.addEventListener('click', e => {
        // 只响应左键
        if (e.button !== 0) return;

        clickCount++;

        if (clickTimer) {
            clearTimeout(clickTimer);
        }

        clickTimer = setTimeout(() => {
            clickCount = 0;
        }, 500);

        if (clickCount === 3) {
            DEBUG = !DEBUG;
            console.warn(`[Stock Debug] ${DEBUG ? 'ON' : 'OFF'} (triple click)`);
            clickCount = 0;
            clearTimeout(clickTimer);
        }
    }, true); // capture，确保不被页面阻断

    /* ================= 正则 ================= */

    const STOCK_SCAN_REGEX =
        /\b(00\d{4}|30\d{4}|60\d{4}|68\d{4}|43\d{4}|83\d{4}|87\d{4}|92\d{4})\b/g;

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
        .stock-debug-tip {
            position: absolute;
            z-index: 999999;
            background: #111;
            color: #0f0;
            font-size: 12px;
            padding: 6px 8px;
            border-radius: 4px;
            pointer-events: none;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(0,0,0,.4);
        }
    `);

    const processedNodes = new WeakSet();

    /* ================= Walker（不变） ================= */

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
                    ctx.text += n.nodeValue;
                    ctx.nodes.push(n);
                }

                if (ctx.text) {
                    this.handler(ctx, this.regex);
                }
            }
        }
    }

    /* ================= 高亮 + Debug 数据 ================= */

    function applyHighlight(ctx, regex) {
        let match;
        regex.lastIndex = 0;

        while ((match = regex.exec(ctx.text)) !== null) {
            const code = match[1];
            const start = match.index;
            const end = start + code.length;

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
            span.textContent = code;
            span.dataset.code = code;

            if (DEBUG) {
                span.dataset.debug =
                    `code=${code}\nstart=${start}\nend=${end}\nnodes=${ctx.nodes.length}`;
            }

            range.deleteContents();
            range.insertNode(span);
        }

        ctx.nodes.forEach(n => processedNodes.add(n));
    }

    /* ================= Debug Tooltip ================= */

    let tip;
    document.body.addEventListener('mousemove', e => {
        if (!DEBUG) return;

        const el = e.target.closest('.stock-highlight');
        if (!el || !el.dataset.debug) {
            if (tip) tip.remove(), (tip = null);
            return;
        }

        if (!tip) {
            tip = document.createElement('div');
            tip.className = 'stock-debug-tip';
            document.body.appendChild(tip);
        }

        tip.textContent = el.dataset.debug;
        tip.style.left = e.pageX + 12 + 'px';
        tip.style.top = e.pageY + 12 + 'px';
    });

    /* ================= 点击复制 ================= */

    document.body.addEventListener('click', e => {
        const el = e.target.closest('.stock-highlight');
        if (!el) return;
        e.stopPropagation();
        GM_setClipboard(el.dataset.code, 'text');
    }, true);

    /* ================= 扫描调度 ================= */

    let timer;
    function trigger() {
        clearTimeout(timer);
        timer = setTimeout(() => {
            new ContextualWalker(document.body, STOCK_SCAN_REGEX, applyHighlight);
        }, 400);
    }

    new MutationObserver(trigger)
        .observe(document.body, { childList: true, subtree: true, characterData: true });

    window.addEventListener('load', () => setTimeout(trigger, 800));
})();
