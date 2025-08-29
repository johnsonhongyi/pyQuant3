// ==UserScript==
// @name         自动复制选中文本
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  自动复制用户选中的文本内容到剪贴板，绕过网站的复制限制
// @author       Steper Lin
// @match        *://*/*
// @grant        GM_setClipboard
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';
    // 正则表达式定义
    const stockCodeRegex = /\b(00[0-9]{4}|30[0-9]{4}|60[0-9]{4}|68[0-9]{4})\b/g;
    //const stockNames = Object.keys(stockNameToCode);
    //const escapedStockNames = stockNames.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    //const stockNameRegex = new RegExp(`(${escapedStockNames.join('|')})`, 'g');
    const combinedRegex = new RegExp(`${stockCodeRegex.source}`, 'g');


    // 监听选择事件
    document.addEventListener('mouseup', function(e) {
        // 获取选中的文本
        const selectedText = window.getSelection().toString().trim();
        const stockCode = (stockCodeRegex.test(selectedText));
        // 如果有选中的文本，则复制到剪贴板
        if (stockCode) {
            // 使用油猴API复制到剪贴板
            GM_setClipboard(stockCode, 'text');

            // 可选：在控制台显示已复制的内容（调试用）
            console.log('已复制: ' + selectedText);
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
})();



