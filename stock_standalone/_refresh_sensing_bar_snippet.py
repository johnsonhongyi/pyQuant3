    def _refresh_sensing_bar(self, code):
        """仅刷新监理看板部分（用于 update_df_all 时的快速更新）"""
        if not hasattr(self, 'kline_plot'):
            return
        
        # 获取当前标题的基础部分（不含监理看板）
        info = self.code_info_map.get(code, {})
        title_parts = [code]
        for k, fmt in [('name', '{}'), ('Rank', 'Rank: {}'), ('percent', '{:+.2f}%'),
                       ('win', 'win: {}'), ('slope', 'slope: {:.1f}%'), ('volume', 'vol: {:.1f}')]:
            v = info.get(k)
            if v is not None:
                title_parts.append(fmt.format(v))
        
        # ⭐ 追加监理看板信息
        sensing_parts = []
        if not self.df_all.empty:
            crow = None
            if code in self.df_all.index:
                crow = self.df_all.loc[code]
            elif 'code' in self.df_all.columns:
                mask = self.df_all['code'] == code
                if mask.any():
                    crow = self.df_all[mask].iloc[0]
            
            if crow is not None:
                mwr = crow.get('market_win_rate', 0)
                ls = crow.get('loss_streak', 0)
                vwap_bias = crow.get('vwap_bias', 0)
                # 显示所有监理数据（即使为0也显示，便于调试）
                sensing_parts.append(f"🛡️监理: 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}")
        
        main_title = " | ".join(title_parts)
        if sensing_parts:
            sensing_html = " ".join(sensing_parts)
            main_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>{sensing_html}</span>"
            
        self.kline_plot.setTitle(main_title)
