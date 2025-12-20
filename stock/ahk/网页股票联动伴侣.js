// ==UserScript==
// @name         网页股票联动伴侣
// @namespace    http://tampermonkey.net/
// @version      8.2
// @description  高效精准高亮 A 股股票代码，并支持复制联动
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

    /* ================= 股票正则（严格分工） ================= */

    // 仅用于全文扫描（exec）
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

    /* ================= 高亮实现（核心修复点） ================= */

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

            range.deleteContents();
            range.insertNode(span);
        }

        ctx.nodes.forEach(n => processedNodes.add(n));
    }

    /* ================= 点击复制 ================= */

    document.body.addEventListener('click', e => {
        const el = e.target.closest('.stock-highlight');
        if (!el) return;
        e.stopPropagation();
        GM_setClipboard(el.dataset.code, 'text');
        console.log('[Stock Copied]', el.dataset.code);
    }, true);

    /* ================= 扫描调度 ================= */

    let timer;
    function trigger() {
        clearTimeout(timer);
        timer = setTimeout(() => {
            new ContextualWalker(document.body, STOCK_SCAN_REGEX, applyHighlight);
        }, 400);
    }

    const mo = new MutationObserver(trigger);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });

    window.addEventListener('load', () => setTimeout(trigger, 800));
})();
