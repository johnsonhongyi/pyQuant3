
// ==UserScript==

// @name         网页股票联动伴侣

// @namespace    http://tampermonkey.net/

// @version      8.1

// @description  高效精准地高亮显示A股股票代码和名称 ，联动通达信、同花顺、东方财富、大智慧、指南针软件，它是一款能一键打通网页与本地股票软件的超级工具。

// @author       John

// @match        *://*/*

// @grant        GM_xmlhttpRequest

// @grant        GM_addStyle

// @grant        GM_getValue

// @grant        GM_setValue

// @grant        GM_setClipboard

// @connect      localhost



// ==/UserScript==

(function( ) {
    'use strict';
    // 监听选择事件
    document.addEventListener('mouseup', function(e) {
        // 获取选中的文本
        const selectedText = window.getSelection().toString().trim();
        // 如果有选中的文本，则复制到剪贴板
        if (selectedText) {
            const stockCode = (stockCodeRegex.test(selectedText));
            if (stockCode) {
                // 检查将要被替换的内容是否已在高亮标签内，防止重复高亮


                GM_setClipboard(stockCode, 'text');
                console.log('已复制: ' + stockCode);

            } else {
                console.log('NoCode: ' + selectedText);
            }
            // 使用油猴API复制到剪贴板
            // 可选：在控制台显示已复制的内容（调试用）
        }
    });

    // 阻止网站的复制限制
    document.addEventListener('copy', function(e) {
        const selectedText = window.getSelection().toString().trim();
        if (selectedText) {
            e.stopPropagation();
        }
    }, true);

    // 阻止网站的选择限制
    document.addEventListener('selectstart', function(e) {
        e.stopPropagation();
    }, true);

    // 禁用可能阻止复制的CSS
    const style = document.createElement('style');
    style.textContent = `
        * {
            -webkit-user-select: text !important;
            -moz-user-select: text !important;
            -ms-user-select: text !important;
            user-select: text !important;
        }
    `;
    document.head.appendChild(style);
    // --- 1. 样式定义 ---
    GM_addStyle(`
        .stock-highlight {
            color: red !important;
            font-weight: bold !important;
            cursor: pointer !important;
            background-color: #fff3cd !important;
            padding: 1px 2px !important;
            border-radius: 3px !important;
            display: inline !important;
            font-style: normal !important;
        }
        .stock-highlight:hover {
            text-decoration: underline !important;
            background-color: #ffe082 !important;
        }
    `);
    // document.head.appendChild(style);
    // --- 2. 股票数据 ---
    // 股票名称到代码的映射 (为了性能，键应该是唯一的)

    // --- 3. 核心高亮逻辑 (带详细注释) ---

    // 正则表达式定义
    // const stockCodeRegex = /\b(00[0-9]{4}|30[0-9]{4}|60[0-9]{4}|68[0-9]{4})\b/;
    const stockCodeRegex = /\b(00[0-9]{4}|30[0-9]{4}|60[0-9]{4}|68[0-9]{4}|43[0-9]{4}|83[0-9]{4}|87[0-9]{4}|92[0-9]{4})\b/;
    // const stockCodeRegex = /\b(00[0-9]{4}|30[0-9]{4}|60[0-9]{4}|68[0-9]{4})\b/g;
    // const stockCodeRegex = /\b(000[\d]{3}|002[\d]{3}|300[\d]{3}|600[\d]{3}|60[\d]{4})\b/g;
    //const stockNames = Object.keys(stockNameToCode);
    //const escapedStockNames = stockNames.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    //const stockNameRegex = new RegExp(`(${escapedStockNames.join('|')})`, 'g');
    const combinedRegex = new RegExp(`${stockCodeRegex.source}`, 'g');

    // 性能优化：存储已处理节点
    const processedNodes = new WeakSet();

    // ContextualWalker 类的定义 (保持不变)
    class ContextualWalker {
        constructor(rootNode, regex, highlightFn) {
            this.root = rootNode;
            this.regex = regex;
            this.highlightFn = highlightFn;
            this.textNodes = [];
            this.scan();
            this.process();
        }
        scan() {
            const walker = document.createTreeWalker(this.root, NodeFilter.SHOW_TEXT, {
                acceptNode: (node) => {
                    const parent = node.parentElement;
                    if (!parent || processedNodes.has(node) || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA'].includes(parent.tagName) || parent.closest('.stock-highlight')) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (node.nodeValue.trim() === '') {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            });
            while (walker.nextNode()) {
                this.textNodes.push(walker.currentNode);
            }
        }
        process() {
            for (let i = 0; i < this.textNodes.length; i++) {
                const startNode = this.textNodes[i];
                if (processedNodes.has(startNode)) continue;
                let context = { text: '', nodes: [], maxLookAhead: 10 };
                for (let j = i; j < this.textNodes.length && context.nodes.length < context.maxLookAhead; j++) {
                    const currentNode = this.textNodes[j];
                    if (processedNodes.has(currentNode)) {
                        if (context.nodes.length > 0) break;
                        else continue;
                    }
                    if (context.nodes.length > 0 && !this.areNodesAdjacent(context.nodes[context.nodes.length - 1], currentNode)) {
                        break;
                    }
                    context.text += currentNode.nodeValue;
                    context.nodes.push(currentNode);
                }
                if (context.text) {
                    this.highlightFn(context, this.regex);
                }
            }
        }
        areNodesAdjacent(node1, node2) {
            let sibling = node1.nextSibling;
            while (sibling) {
                if (sibling === node2) return true;
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.textContent.trim() === '' && getComputedStyle(sibling).display.includes('inline')) {
                    sibling = sibling.nextSibling;
                    continue;
                }
                return false;
            }
            let parent = node1.parentNode;
            while (parent && parent !== this.root) {
                sibling = parent.nextSibling;
                while (sibling) {
                    if (sibling.contains(node2)) return true;
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.textContent.trim() === '' && getComputedStyle(sibling).display.includes('inline')) {
                        sibling = sibling.nextSibling;
                        continue;
                    }
                    return false;
                }
                parent = parent.parentNode;
            }
            return false;
        }
    }

    // applyHighlight 函数的定义 (保持不变)
    function applyHighlight(context, regex) {
        let match;
        regex.lastIndex = 0;
        while ((match = regex.exec(context.text)) !== null) {
            // console.log('match:' + match[0].replace(/[\d\+]/g,""))
            const matchText = match[0].trim()
            const startIndex = match.index;
            const endIndex = startIndex + matchText.length;
            let charCounter = 0;
            let startNode = null, endNode = null;
            let startOffset = -1, endOffset = -1;
            for (const node of context.nodes) {
                const nodeLen = node.nodeValue.length;
                if (charCounter + nodeLen > startIndex && startOffset === -1) {
                    startNode = node;
                    startOffset = startIndex - charCounter;
                }
                if (charCounter + nodeLen >= endIndex && endOffset === -1) {
                    endNode = node;
                    endOffset = endIndex - charCounter;
                }
                charCounter += nodeLen;
                if (endNode) break;
            }
            if (startNode && endNode) {
                const range = document.createRange();
                range.setStart(startNode, startOffset);
                range.setEnd(endNode, endOffset);
                // console.log('检查matchText1: ' + matchText);
                // console.log('检查matchText600475: ' + (stockCodeRegex.test('600475') ? '600475' : null) );
                // console.log('检查matchText600979: ' + (stockCodeRegex.test('600979') ? '600475' : null) );
                const stockCode = (stockCodeRegex.test(matchText) ? matchText : null)
                // console.log('检查stockCode1: ' + stockCode);
                if (stockCode) {
                    // 检查将要被替换的内容是否已在高亮标签内，防止重复高亮
                    if (range.cloneContents().querySelector('.stock-highlight')) {
                        // console.log('已高亮: ' + stockCode);
                        continue;
                    }
                    const highlightSpan = document.createElement('span');
                    highlightSpan.className = 'stock-highlight';
                    highlightSpan.textContent = matchText;
                    highlightSpan.dataset.stockCode = stockCode;
                    range.deleteContents();
                    range.insertNode(highlightSpan);
                }
            }
        }
        context.nodes.forEach(node => processedNodes.add(node));
    }

    // --- 4. 联动与事件处理 ---

    // 联动函数
    function sendToLocalBridge(stockCode) {
        // console.log(`发送代码 ${stockCode} 到本地服务进行广播...`);
        // 如果有选中的文本，则复制到剪贴板
        if (stockCode) {
            // 使用油猴API复制到剪贴板
            GM_setClipboard(stockCode, 'text');

            // 可选：在控制台显示已复制的内容（调试用）
            console.log('已发送: ' + stockCode);
        }
    }

    // 点击事件委托
    document.body.addEventListener('click', (event) => {
        const target = event.target.closest('.stock-highlight');
        if (target && target.dataset.stockCode) {
            event.preventDefault();
            event.stopPropagation();
            sendToLocalBridge(target.dataset.stockCode);
        }
    }, true);

    // --- 5. 动态内容处理与周期性扫描 (修复后) ---

    // 防抖函数，用于防止在短时间内过于频繁地执行扫描
    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    // 统一的高亮扫描入口函数
    const triggerHighlight = debounce(() => {
        // console.log("Debounced scan triggered"); // 调试时可开启
        new ContextualWalker(document.body, combinedRegex, applyHighlight);
    }, 500); // 500毫秒的防抖延迟，可以根据需要调整

    // 方案A: 响应式高亮 - MutationObserver
    // 它的任务很简单：只要DOM有任何变化，就去调用统一的入口函数
    const observer = new MutationObserver(() => {
        triggerHighlight();
    });

    // 配置观察器以监听最广泛的变化
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });

    // 方案B: 周期性高亮 - setInterval
    // 它的任务也很简单：每隔一段时间，就去调用统一的入口函数，作为保险
    setInterval(() => {
        triggerHighlight();
    }, 2000); // 每2秒触发一次

    // --- 6. 初始执行 ---
    // 页面加载完成后，也调用统一的入口函数来执行首次扫描
    window.addEventListener('load', () => {
        setTimeout(triggerHighlight, 1000);
    });

})();