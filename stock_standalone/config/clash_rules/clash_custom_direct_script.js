// ==============================================================================
// 量化股票监控与 EA/Steam 游戏极速下载 — Clash Verge Rev 专属扩展脚本 (Script 格式)
// 保存路径: stock_standalone/config/clash_rules/clash_custom_direct_script.js
// ==============================================================================

function main(config, profileName) {
  // 国内金融、股票行情、EA 游戏平台与下载、Steam、通达信核心直连规则（置顶优先匹配）
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

    // 3. EA 平台与 EA 游戏全量直连与下载 CDN (跑满宽带)
    "DOMAIN-SUFFIX,ea.com,DIRECT",
    "DOMAIN-SUFFIX,origin.com,DIRECT",
    "DOMAIN-SUFFIX,electronicarts.com,DIRECT",
    "DOMAIN-SUFFIX,eamobile.com,DIRECT",
    "DOMAIN-SUFFIX,dice.se,DIRECT",
    "DOMAIN-SUFFIX,respawn.com,DIRECT",
    "DOMAIN-SUFFIX,bioware.com,DIRECT",
    "DOMAIN-SUFFIX,frostbite.com,DIRECT",
    "DOMAIN-SUFFIX,eacdn.com,DIRECT",
    "DOMAIN-SUFFIX,akamaized.net,DIRECT",
    "DOMAIN-SUFFIX,akamaihd.net,DIRECT",
    "DOMAIN-SUFFIX,edgekey.net,DIRECT",
    "DOMAIN-SUFFIX,edgesuite.net,DIRECT",
    // EA 游戏进程
    "PROCESS-NAME,EADesktop.exe,DIRECT",
    "PROCESS-NAME,EABackgroundService.exe,DIRECT",
    "PROCESS-NAME,EALauncher.exe,DIRECT",
    "PROCESS-NAME,EACrashReporter.exe,DIRECT",
    "PROCESS-NAME,Origin.exe,DIRECT",
    "PROCESS-NAME,OriginClientService.exe,DIRECT",
    "PROCESS-NAME,OriginWebHelperService.exe,DIRECT",
    "PROCESS-NAME,r5apex.exe,DIRECT",
    "PROCESS-NAME,bf1.exe,DIRECT",
    "PROCESS-NAME,bfv.exe,DIRECT",
    "PROCESS-NAME,bf2042.exe,DIRECT",
    "PROCESS-NAME,FC24.exe,DIRECT",
    "PROCESS-NAME,FC25.exe,DIRECT",
    "PROCESS-NAME,FIFA23.exe,DIRECT",
    "PROCESS-NAME,FIFA22.exe,DIRECT",
    "PROCESS-NAME,NeedForSpeedUnbound.exe,DIRECT",
    "PROCESS-NAME,NFS22.exe,DIRECT",
    "PROCESS-NAME,starwarsjedisurvivor.exe,DIRECT",
    "PROCESS-NAME,deadspace.exe,DIRECT",
    "PROCESS-NAME,EasyAntiCheat.exe,DIRECT",
    "PROCESS-NAME,EasyAntiCheat_EOS.exe,DIRECT",
    "PROCESS-NAME,Link2EA.exe,DIRECT",
    "PROCESS-NAME,ActivationUI.exe,DIRECT",
    // EA 关键词
    "DOMAIN-KEYWORD,ea.com,DIRECT",
    "DOMAIN-KEYWORD,origin,DIRECT",
    "DOMAIN-KEYWORD,electronicarts,DIRECT",

    // 4. Steam 满速下载直连
    "DOMAIN-SUFFIX,steamconnecttest.com,DIRECT",
    "DOMAIN-SUFFIX,steamcontent.com,DIRECT",
    "DOMAIN-SUFFIX,steamserver.net,DIRECT",
    "DOMAIN-SUFFIX,steam-chat.com,DIRECT",
    "DOMAIN-SUFFIX,steambroadcast.akamaized.net,DIRECT",
    "DOMAIN-SUFFIX,steamcdn-a.akamaihd.net,DIRECT",

    // 5. 关键字直连
    "DOMAIN-KEYWORD,stock,DIRECT",
    "DOMAIN-KEYWORD,tongdaxin,DIRECT",
    "DOMAIN-KEYWORD,eastmoney,DIRECT",

    // 6. 通达信与券商行情主站 IP 段 (TCP 7709)
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

    // 7. 国内直连兜底
    "GEOIP,CN,DIRECT"
  ];

  if (!config.rules) {
    config.rules = [];
  }
  config.rules.unshift(...customDirectRules);

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
      "*.bse.cn",
      // EA / Steam 域名
      "*.ea.com",
      "*.origin.com",
      "*.electronicarts.com",
      "*.akamaized.net",
      "*.akamaihd.net",
      "*.edgekey.net",
      "*.edgesuite.net",
      "*.steamconnecttest.com",
      "*.steamcontent.com",
      "*.respawn.com",
      "*.dice.se"
    ];
    filterDomains.forEach(d => {
      if (!config.dns['fake-ip-filter'].includes(d)) {
        config.dns['fake-ip-filter'].push(d);
      }
    });
  }

  return config;
}
