// ==============================================================================
// 量化股票监控与交易系统 — Clash Verge Rev 专属扩展脚本 (Script 格式)
// 保存路径: stock_standalone/config/clash_rules/clash_custom_direct_script.js
// ==============================================================================

function main(config, profileName) {
  // 国内金融、股票行情、通达信与交易所核心直连规则（置顶优先匹配）
  const customDirectRules = [
    // 1. 行情与金融数据 API
    "DOMAIN-SUFFIX,sinajs.cn,DIRECT",
    "DOMAIN-SUFFIX,sina.com.cn,DIRECT",
    "DOMAIN-SUFFIX,gtimg.cn,DIRECT",
    "DOMAIN-SUFFIX,qq.com,DIRECT",
    "DOMAIN-SUFFIX,eastmoney.com,DIRECT",
    "DOMAIN-SUFFIX,dfcfw.com,DIRECT",
    "DOMAIN-SUFFIX,10jqka.com.cn,DIRECT",
    "DOMAIN-SUFFIX,iwencai.com,DIRECT",
    "DOMAIN-SUFFIX,ths.com.cn,DIRECT",
    "DOMAIN-SUFFIX,upchina.com,DIRECT",
    "DOMAIN-SUFFIX,cninfo.com.cn,DIRECT",
    "DOMAIN-SUFFIX,gw.com.cn,DIRECT",
    "DOMAIN-SUFFIX,tdx.com.cn,DIRECT",
    "DOMAIN-SUFFIX,wind.com.cn,DIRECT",
    // 2. 交易所官方域名
    "DOMAIN-SUFFIX,sse.com.cn,DIRECT",
    "DOMAIN-SUFFIX,szse.com.cn,DIRECT",
    "DOMAIN-SUFFIX,bse.cn,DIRECT",
    "DOMAIN-SUFFIX,neeq.com.cn,DIRECT",
    "DOMAIN-SUFFIX,csrc.gov.cn,DIRECT",
    // 3. 关键字直连
    "DOMAIN-KEYWORD,stock,DIRECT",
    "DOMAIN-KEYWORD,tongdaxin,DIRECT",
    "DOMAIN-KEYWORD,eastmoney,DIRECT",
    // 4. 通达信与券商行情主站 IP 段 (TCP 7709)
    "IP-CIDR,202.108.254.0/24,DIRECT",
    "IP-CIDR,202.108.253.0/24,DIRECT",
    "IP-CIDR,111.15.15.0/24,DIRECT",
    "IP-CIDR,111.13.75.0/24,DIRECT",
    "IP-CIDR,119.147.212.0/24,DIRECT",
    "IP-CIDR,218.75.126.0/24,DIRECT",
    "IP-CIDR,221.231.141.0/24,DIRECT",
    "IP-CIDR,115.238.56.0/24,DIRECT",
    "IP-CIDR,120.199.2.0/24,DIRECT",
    "IP-CIDR,117.149.2.0/24,DIRECT",
    "IP-CIDR,223.112.100.0/24,DIRECT",
    "IP-CIDR,60.12.136.0/24,DIRECT",
    // 5. 国内直连兜底
    "GEOIP,CN,DIRECT"
  ];

  if (!config.rules) {
    config.rules = [];
  }
  // 强行置顶插入
  config.rules.unshift(...customDirectRules);

  // 确保 DNS fake-ip-filter 包含行情域名，防止 TUN 虚拟网卡将其伪装为 198.18.0.x
  if (config.dns) {
    if (!config.dns['fake-ip-filter']) {
      config.dns['fake-ip-filter'] = [];
    }
    const filterDomains = [
      "*.sinajs.cn",
      "*.sina.com.cn",
      "*.gtimg.cn",
      "*.eastmoney.com",
      "*.dfcfw.com",
      "*.10jqka.com.cn",
      "*.iwencai.com",
      "*.ths.com.cn",
      "*.upchina.com",
      "*.tdx.com.cn",
      "*.sse.com.cn",
      "*.szse.com.cn",
      "*.bse.cn"
    ];
    filterDomains.forEach(d => {
      if (!config.dns['fake-ip-filter'].includes(d)) {
        config.dns['fake-ip-filter'].push(d);
      }
    });
  }

  return config;
}
