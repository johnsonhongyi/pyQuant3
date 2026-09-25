// ==============================================================================
// 量化股票监控与智能白名单分流 — Clash Verge Rev 专属扩展脚本 (Script 格式)
// 核心逻辑: 白名单模式 (平时系统与软件正常直连，仅特定外网/被墙请求走代理，末尾 MATCH,DIRECT)
// 保存路径: stock_standalone/config/clash_rules/clash_custom_direct_script.js
// ==============================================================================

function main(config, profileName) {
  // ----------------------------------------------------------------------------
  // 1. 策略组默认项调优: 将 Microsoft, Apple, Download 的首选设为 DIRECT
  // ----------------------------------------------------------------------------
  if (config['proxy-groups']) {
    config['proxy-groups'].forEach(g => {
      if (['Microsoft', 'Apple', 'Download', 'Steam'].includes(g.name)) {
        if (g.proxies && g.proxies.includes('DIRECT')) {
          g.proxies = ['DIRECT', ...g.proxies.filter(p => p !== 'DIRECT')];
        }
      }
    });
  }

  // ----------------------------------------------------------------------------
  // 2. 前置强制直连规则 (置顶优先匹配，毫秒级响应，杜绝消耗代理流量)
  // ----------------------------------------------------------------------------
  const customDirectRules = [
    // --------------------------------------------------------------------------
    // A. 股票金融、行情与数据接口 (极速直连)
    // --------------------------------------------------------------------------
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
    "DOMAIN-SUFFIX,sse.com.cn,DIRECT",
    "DOMAIN-SUFFIX,szse.com.cn,DIRECT",
    "DOMAIN-SUFFIX,bse.cn,DIRECT",
    "DOMAIN-SUFFIX,neeq.com.cn,DIRECT",
    "DOMAIN-SUFFIX,csrc.gov.cn,DIRECT",
    "DOMAIN-SUFFIX,chinabond.com.cn,DIRECT",
    "DOMAIN-SUFFIX,chinamoney.com.cn,DIRECT",
    "DOMAIN-KEYWORD,stock,DIRECT",
    "DOMAIN-KEYWORD,tongdaxin,DIRECT",
    "DOMAIN-KEYWORD,eastmoney,DIRECT",

    // 通达信与主流券商行情服务器 IP 段 (TCP 7709 / 7711)
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

    // --------------------------------------------------------------------------
    // B. Windows 系统更新、Visual Studio 安装与开发工具大流量直连 (杜绝偷跑数 GB 流量)
    // --------------------------------------------------------------------------
    "PROCESS-NAME,BackgroundDownload.exe,DIRECT",
    "PROCESS-NAME,vs_installer.exe,DIRECT",
    "PROCESS-NAME,vs_community.exe,DIRECT",
    "PROCESS-NAME,devenv.exe,DIRECT",
    "PROCESS-NAME,MpDefenderCoreService.exe,DIRECT",
    "PROCESS-NAME,SDXHelper.exe,DIRECT",
    "PROCESS-NAME,onedrive.exe,DIRECT",
    "PROCESS-NAME,msedge.exe,DIRECT",
    "PROCESS-NAME,NVDisplay.Container.exe,DIRECT",
    "PROCESS-NAME,LogiOptionsMgr.exe,DIRECT",

    "DOMAIN-SUFFIX,windowsupdate.com,DIRECT",
    "DOMAIN-SUFFIX,update.microsoft.com,DIRECT",
    "DOMAIN-SUFFIX,delivery.mp.microsoft.com,DIRECT",
    "DOMAIN-SUFFIX,windows.com,DIRECT",
    "DOMAIN-SUFFIX,microsoft.com,DIRECT",
    "DOMAIN-SUFFIX,office.com,DIRECT",
    "DOMAIN-SUFFIX,office365.com,DIRECT",
    "DOMAIN-SUFFIX,live.com,DIRECT",
    "DOMAIN-SUFFIX,msftncsi.com,DIRECT",
    "DOMAIN-SUFFIX,msftconnecttest.com,DIRECT",
    "DOMAIN-SUFFIX,azure.com,DIRECT",
    "DOMAIN-SUFFIX,azureedge.net,DIRECT",

    // --------------------------------------------------------------------------
    // C. Apple 服务与系统常用厂商直连
    // --------------------------------------------------------------------------
    "DOMAIN-SUFFIX,apple.com,DIRECT",
    "DOMAIN-SUFFIX,icloud.com,DIRECT",
    "DOMAIN-SUFFIX,mzstatic.com,DIRECT",
    "DOMAIN-SUFFIX,nvidia.com,DIRECT",
    "DOMAIN-SUFFIX,logitech.com,DIRECT",
    "DOMAIN-SUFFIX,digicert.com,DIRECT",

    // --------------------------------------------------------------------------
    // D. EA / Steam 游戏下载满速直连 (跑满千兆带宽)
    // --------------------------------------------------------------------------
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
    "DOMAIN-KEYWORD,ea.com,DIRECT",
    "DOMAIN-KEYWORD,origin,DIRECT",
    "DOMAIN-KEYWORD,electronicarts,DIRECT",

    "DOMAIN-SUFFIX,steamconnecttest.com,DIRECT",
    "DOMAIN-SUFFIX,steamcontent.com,DIRECT",
    "DOMAIN-SUFFIX,steamserver.net,DIRECT",
    "DOMAIN-SUFFIX,steam-chat.com,DIRECT",
    "DOMAIN-SUFFIX,steambroadcast.akamaized.net,DIRECT",
    "DOMAIN-SUFFIX,steamcdn-a.akamaihd.net,DIRECT"
  ];

  if (!config.rules) {
    config.rules = [];
  }
  // 置顶前置直连规则
  config.rules.unshift(...customDirectRules);

  // ----------------------------------------------------------------------------
  // 3. 核心分流重构: 白名单直连模式 (末尾兜底彻底改为 MATCH,DIRECT)
  // ----------------------------------------------------------------------------
  // 过滤掉已有的尾部 MATCH 规则，重新安全构建尾部
  const cleanedRules = [];
  for (let i = 0; i < config.rules.length; i++) {
    const r = config.rules[i].trim();
    if (r.startsWith("MATCH,")) {
      continue; // 稍后统一注入
    }
    cleanedRules.push(config.rules[i]);
  }

  // 尾部安全链构建:
  // 1) GEOSITE,gfw,Default Proxy -> 如果前面的特定规则没命中，但确实属于被墙网站，走代理防丢网
  // 2) GEOIP,CN,DIRECT -> 国内 IP 确认直连
  // 3) GEOIP,PRIVATE,DIRECT -> 局域网直连
  // 4) MATCH,DIRECT -> 关键兜底！未被指定的外网/系统服务/未知流量一律直连，绝不偷跑代理！
  cleanedRules.push("GEOSITE,gfw,Default Proxy");
  cleanedRules.push("GEOIP,CN,DIRECT");
  cleanedRules.push("GEOIP,PRIVATE,DIRECT");
  cleanedRules.push("MATCH,DIRECT");

  config.rules = cleanedRules;

  // ----------------------------------------------------------------------------
  // 4. DNS Fake-IP 白名单优化 (避免核心直连域名被 fake-ip 拦截)
  // ----------------------------------------------------------------------------
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
      "*.windowsupdate.com",
      "*.update.microsoft.com",
      "*.microsoft.com",
      "*.windows.com",
      "*.apple.com",
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
