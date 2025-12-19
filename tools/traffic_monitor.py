#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流量监控分析工具 - 最终版本
"""

import streamlit as st
import pandas as pd
import io
from datetime import date, datetime, timedelta
import logging

class TrafficMonitor:
    """流量监控分析工具"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def determine_network_type(row):
        """
        判断小区制式（4G/5G）
        
        规则：
        1. performance_data.pinduan 中，4.9GHz、2.6GHz、700M 为 5G 小区
        2. cell_mapping.zhishi 为 '5G' 为 5G 小区
        3. 其中一个表判断为 5G 则为 5G，其他则为 4G
        
        Args:
            row: DataFrame 行数据，需包含 'pinduan' 和 'zhishi' 字段
            
        Returns:
            str: '5g' 或 '4g'
        """
        # 5G 频段列表（仅包含真正的5G频段）
        freq_5g = ['4.9GHz', '2.6GHz', '700M']
        
        # 获取频段和制式
        pinduan = row.get('pinduan', '')
        zhishi = row.get('zhishi', '')
        
        # 判断逻辑：任一条件满足即为 5G
        if pinduan in freq_5g or zhishi == '5G':
            return '5g'
        else:
            return '4g'

    def render(self):
        """渲染容智策略分析引擎界面"""
        st.title("📈 容智策略分析引擎")
        st.caption("网络容量策略分析与性能优化平台")

        # 功能导航
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 零低流量分析", 
            "📈 流量骤降分析", 
            "⚡ 高负荷小区查询",
            "🔍 小区查询",
            "🎯 流量突降分析"
        ])

        with tab1:
            self._render_zero_low_traffic_analysis()

        with tab2:
            self._render_traffic_drop_analysis()

        with tab3:
            self._render_high_load_analysis()

        with tab4:
            self._render_cell_query()

        with tab5:
            self._render_traffic_spike_analysis()

    def _render_zero_low_traffic_analysis(self):
        """渲染零低流量分析页面"""
        st.subheader("📊 零低流量分析")
        st.caption("分析零流量和低流量小区，支持4G/5G不同阈值")
        
        # 获取有数据的日期列表
        available_dates = self._get_available_dates()
        
        # 日期范围选择
        st.markdown("#### 📅 时间范围")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=7),
                key="zero_low_start_date"
            )
        with col_d2:
            end_date = st.date_input(
                "结束日期",
                value=date.today(),
                key="zero_low_end_date"
            )
        
        # 显示有数据的日期提示
        if available_dates:
            self._display_date_availability(available_dates, start_date, end_date)
        
        # 阈值设置
        st.markdown("#### 阈值设置")
        col1, col2 = st.columns(2)
        with col1:
            threshold_4g = st.number_input(
                "4G低流量阈值 (GB)",
                min_value=0.0,
                max_value=100.0,
                value=1.0,
                step=0.1,
                key="threshold_4g",
                help="4G小区流量低于此阈值将被识别为低流量小区"
            )
        with col2:
            threshold_5g = st.number_input(
                "5G低流量阈值 (GB)",
                min_value=0.0,
                max_value=100.0,
                value=1.0,
                step=0.1,
                key="threshold_5g",
                help="5G小区流量低于此阈值将被识别为低流量小区"
            )
        
        if st.button("开始分析", key="analyze_zero_low_traffic"):
            # 创建进度条和日志容器
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_container = st.expander("📋 分析日志", expanded=True)
            
            try:
                with log_container:
                    st.write("---")
                    st.write(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    st.write(f"📅 分析时间范围: {start_date} 至 {end_date}")
                    st.write(f"📊 分析天数: {(end_date - start_date).days + 1} 天")
                    st.write(f"🎯 4G阈值: {threshold_4g} GB")
                    st.write(f"🎯 5G阈值: {threshold_5g} GB")
                    st.write("---")
                
                # 步骤1: 生成零流量分析
                status_text.text("🔍 正在执行零流量分析...")
                progress_bar.progress(20)
                with log_container:
                    st.write("🔍 步骤 1/4: 开始零流量分析...")
                
                zero_df = self._generate_zero_traffic_analysis(start_date, end_date)
                
                with log_container:
                    st.write(f"✅ 零流量分析完成，共发现 {len(zero_df)} 个零流量小区")
                    if not zero_df.empty and '制式' in zero_df.columns:
                        zero_4g = len(zero_df[zero_df['制式'] == '4g'])
                        zero_5g = len(zero_df[zero_df['制式'] == '5g'])
                        st.write(f"   - 4G小区: {zero_4g} 个")
                        st.write(f"   - 5G小区: {zero_5g} 个")
                
                progress_bar.progress(50)
                
                # 步骤2: 生成低流量分析
                status_text.text("🔍 正在执行低流量分析...")
                with log_container:
                    st.write("🔍 步骤 2/4: 开始低流量分析...")
                
                low_df = self._generate_low_traffic_analysis(
                    start_date, end_date, threshold_4g, threshold_5g
                )
                
                with log_container:
                    st.write(f"✅ 低流量分析完成，共发现 {len(low_df)} 个低流量小区")
                    if not low_df.empty and '制式' in low_df.columns:
                        low_4g = len(low_df[low_df['制式'] == '4g'])
                        low_5g = len(low_df[low_df['制式'] == '5g'])
                        st.write(f"   - 4G小区: {low_4g} 个")
                        st.write(f"   - 5G小区: {low_5g} 个")
                
                progress_bar.progress(80)
                
                # 步骤3: 保存数据
                status_text.text("💾 正在保存分析结果...")
                with log_container:
                    st.write("💾 步骤 3/4: 保存分析结果...")
                
                st.session_state['zero_traffic_df'] = zero_df
                st.session_state['low_traffic_df'] = low_df
                st.session_state['zero_low_start_date_saved'] = start_date
                st.session_state['zero_low_end_date_saved'] = end_date
                st.session_state['zero_low_threshold_4g'] = threshold_4g
                st.session_state['zero_low_threshold_5g'] = threshold_5g
                
                progress_bar.progress(100)
                
                with log_container:
                    st.write("✅ 数据保存完成")
                    st.write("---")
                    st.write(f"⏰ 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    total_cells = len(zero_df) + len(low_df)
                    st.write(f"📊 分析结果汇总: 共发现 {total_cells} 个问题小区")
                
                # 完成
                status_text.empty()
                progress_bar.empty()
                st.success("✅ 零低流量分析完成！")
                
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                with log_container:
                    st.write("---")
                    st.write(f"❌ 分析失败: {str(e)}")
                    st.write(f"⏰ 失败时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                st.error(f"分析失败: {e}")
                self.logger.error(f"零低流量分析失败: {e}")
        
        # 显示分析结果
        if 'zero_traffic_df' in st.session_state and not st.session_state['zero_traffic_df'].empty:
            zero_df = st.session_state['zero_traffic_df']
            low_df = st.session_state['low_traffic_df']
            
            # 显示统计信息
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("零流量小区", len(zero_df))
            with col2:
                st.metric("低流量小区", len(low_df))
            with col3:
                zero_4g = len(zero_df[zero_df['制式'] == '4g']) if '制式' in zero_df.columns and not zero_df.empty else 0
                low_4g = len(low_df[low_df['制式'] == '4g']) if '制式' in low_df.columns and not low_df.empty else 0
                st.metric("4G小区", zero_4g + low_4g)
            with col4:
                zero_5g = len(zero_df[zero_df['制式'] == '5g']) if '制式' in zero_df.columns and not zero_df.empty else 0
                low_5g = len(low_df[low_df['制式'] == '5g']) if '制式' in low_df.columns and not low_df.empty else 0
                st.metric("5G小区", zero_5g + low_5g)
            
            # 导出Excel文件
            if st.button("导出Excel文件", key="export_zero_low_traffic"):
                self._export_zero_low_traffic_excel(
                    zero_df, low_df,
                    st.session_state['zero_low_start_date_saved'],
                    st.session_state['zero_low_end_date_saved'],
                    st.session_state.get('zero_low_threshold_4g', 1.0),
                    st.session_state.get('zero_low_threshold_5g', 1.0)
                )

    def _render_traffic_drop_analysis(self):
        """渲染流量骤降分析页面"""
        st.subheader("📈 流量骤降分析")
        st.caption("对比两个时间段的流量变化，识别骤降小区")
        
        # 获取有数据的日期列表
        available_dates = self._get_available_dates()
        
        # 历史时间段（用于对比的基准）
        st.markdown("#### 📅 历史时间段（对比基准）")
        st.caption("💡 这是历史时间段，用于作为流量对比的基准")
        col1, col2 = st.columns(2)
        with col1:
            before_start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=10),
                key="before_start_date"
            )
        with col2:
            before_end_date = st.date_input(
                "结束日期",
                value=date.today() - timedelta(days=7),
                key="before_end_date"
            )
        
        # 显示历史时间段的数据可用性
        if available_dates:
            self._display_date_availability(available_dates, before_start_date, before_end_date)
        
        # 当前时间段（需要对比的时间段）
        st.markdown("#### 📅 当前时间段（需要对比的时段）")
        st.caption("💡 这是需要对比的时间段，如果流量较历史时段下降明显，将被识别为骤降")
        col1, col2 = st.columns(2)
        with col1:
            after_start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=3),
                key="after_start_date"
            )
        with col2:
            after_end_date = st.date_input(
                "结束日期",
                value=date.today(),
                key="after_end_date"
            )
        
        # 显示当前时间段的数据可用性
        if available_dates:
            self._display_date_availability(available_dates, after_start_date, after_end_date)
        
        # 骤降阈值设置
        st.markdown("#### ⚙️ 阈值设置")
        drop_threshold = st.slider(
            "骤降阈值 (%)",
            min_value=10,
            max_value=90,
            value=50,
            step=10,
            key="traffic_drop_threshold",
            help="平均流量下降超过此百分比将被识别为骤降"
        )
        
        if st.button("开始分析", key="analyze_traffic_drop"):
            # 创建进度条和日志容器
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_container = st.expander("📋 分析日志", expanded=True)
            
            try:
                with log_container:
                    st.write("---")
                    st.write(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    st.write(f"📅 历史时间段（基准）: {before_start_date} 至 {before_end_date}")
                    st.write(f"📅 当前时间段（对比）: {after_start_date} 至 {after_end_date}")
                    st.write(f"🎯 骤降阈值: {drop_threshold}%")
                    st.write("---")
                
                # 步骤1: 执行流量骤降分析
                status_text.text("🔍 正在执行流量骤降分析...")
                progress_bar.progress(30)
                with log_container:
                    st.write("🔍 步骤 1/3: 开始流量骤降分析...")
                
                df = self._generate_traffic_drop_analysis(
                    before_start_date, before_end_date,
                    after_start_date, after_end_date,
                    drop_threshold
                )
                
                with log_container:
                    st.write(f"✅ 流量骤降分析完成，共发现 {len(df)} 个骤降小区")
                    if not df.empty:
                        # 显示前5个结果
                        st.write("📊 前5个骤降小区:")
                        display_cols = ['CGI', '小区名称', '对比前平均流量(GB)', '对比后平均流量(GB)', '流量降幅(%)']
                        available_cols = [col for col in display_cols if col in df.columns]
                        st.dataframe(df[available_cols].head(5))
                        
                        # 检查特定小区
                        target_cgi = '460-00-442681-65'
                        target_cell = df[df['CGI'] == target_cgi]
                        if not target_cell.empty:
                            st.write(f"✅ 找到目标小区 {target_cgi}:")
                            st.write(target_cell[available_cols].to_string())
                        else:
                            st.write(f"❌ 未找到目标小区 {target_cgi}")
                
                progress_bar.progress(80)
                
                # 步骤2: 保存数据
                status_text.text("💾 正在保存分析结果...")
                with log_container:
                    st.write("💾 步骤 2/3: 保存分析结果...")
                
                st.session_state['traffic_drop_df'] = df
                st.session_state['traffic_drop_before_start'] = before_start_date
                st.session_state['traffic_drop_before_end'] = before_end_date
                st.session_state['traffic_drop_after_start'] = after_start_date
                st.session_state['traffic_drop_after_end'] = after_end_date
                
                progress_bar.progress(100)
                
                with log_container:
                    st.write("✅ 数据保存完成")
                    st.write("---")
                    st.write(f"⏰ 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 完成
                status_text.empty()
                progress_bar.empty()
                st.success(f"✅ 流量骤降分析完成，共发现 {len(df)} 个骤降小区")
                
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                with log_container:
                    st.write("---")
                    st.write(f"❌ 分析失败: {str(e)}")
                    st.write(f"⏰ 失败时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                st.error(f"分析失败: {e}")
                self.logger.error(f"流量骤降分析失败: {e}")
        
        # 显示分析结果
        if 'traffic_drop_df' in st.session_state and not st.session_state['traffic_drop_df'].empty:
            df = st.session_state['traffic_drop_df']
            
            # 显示统计信息
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总骤降小区数", len(df))
            with col2:
                avg_drop = df['流量降幅(%)'].mean() if '流量降幅(%)' in df.columns else 0
                st.metric("平均降幅", f"{avg_drop:.1f}%")
            with col3:
                max_drop = df['流量降幅(%)'].max() if '流量降幅(%)' in df.columns else 0
                st.metric("最大降幅", f"{max_drop:.1f}%")
            with col4:
                drop_4g = len(df[df['制式'] == '4g']) if '制式' in df.columns else 0
                drop_5g = len(df[df['制式'] == '5g']) if '制式' in df.columns else 0
                st.metric("4G/5G小区", f"{drop_4g}/{drop_5g}")
            
            # 显示数据表格
            st.dataframe(df, use_container_width=True)
            
            # 导出Excel文件
            if st.button("导出Excel文件", key="export_traffic_drop"):
                self._export_traffic_drop_excel(
                    df,
                    st.session_state['traffic_drop_before_start'],
                    st.session_state['traffic_drop_before_end'],
                    st.session_state['traffic_drop_after_start'],
                    st.session_state['traffic_drop_after_end']
                )

    def _render_high_load_analysis(self):
        """渲染高负荷小区查询页面"""
        st.subheader("⚡ 高负荷小区查询")
        st.caption("查询指定时间内的高负荷小区")
        
        # 时间范围设置
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=7),
                key="high_load_start_date"
            )
        with col2:
            end_date = st.date_input(
                "结束日期",
                value=date.today(),
                key="high_load_end_date"
            )
        
        # 说明信息
        st.info("💡 高负荷小区查询：查询指定时间内 if_overcel='t' 的小区清单")
        
        if st.button("开始查询", key="query_high_load"):
            try:
                summary_df, detail_df = self._generate_high_load_analysis(start_date, end_date)
                
                # 保存到session state（即使为空也保存，以便显示提示信息）
                st.session_state['high_load_summary'] = summary_df
                st.session_state['high_load_detail'] = detail_df
                # 注意：不需要手动设置 high_load_start_date 和 high_load_end_date
                # 因为 date_input widget 已经自动管理这些 session state 值
                
                if summary_df.empty:
                    st.warning("⚠️ 查询完成，但在指定时间范围内未找到高负荷小区数据")
                else:
                    st.success(f"✅ 高负荷小区查询完成，共找到 {len(summary_df)} 个高负荷小区")
                
            except Exception as e:
                st.error(f"查询失败: {e}")
                self.logger.error(f"高负荷小区查询失败: {e}")
                # 清除之前的结果
                if 'high_load_summary' in st.session_state:
                    del st.session_state['high_load_summary']
                if 'high_load_detail' in st.session_state:
                    del st.session_state['high_load_detail']
        
        # 显示查询结果
        if 'high_load_summary' in st.session_state:
            summary_df = st.session_state['high_load_summary']
            detail_df = st.session_state.get('high_load_detail', pd.DataFrame())
            
            if summary_df.empty:
                st.info("📊 当前没有高负荷小区数据，请调整查询时间范围或检查数据")
            else:
                # 显示汇总信息
                st.markdown("#### 小区汇总清单")
                st.dataframe(summary_df, use_container_width=True)
                
                # 显示统计信息
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("高负荷小区数", len(summary_df))
                with col2:
                    st.metric("平均高负荷次数", round(summary_df['高负荷次数'].mean(), 1) if '高负荷次数' in summary_df.columns else 0)
                with col3:
                    st.metric("最大高负荷次数", summary_df['高负荷次数'].max() if '高负荷次数' in summary_df.columns else 0)
                
                # 显示详细清单
                st.markdown("#### 小区负荷详细清单")
                if not detail_df.empty:
                    st.dataframe(detail_df, use_container_width=True)
                else:
                    st.info("暂无详细数据")
                
                # 导出Excel文件
                if st.button("导出Excel文件", key="export_high_load"):
                    self._export_high_load_excel(summary_df, detail_df, st.session_state.get('high_load_start_date', start_date), st.session_state.get('high_load_end_date', end_date))

    def _render_cell_query(self):
        """渲染小区查询页面"""
        st.subheader("🔍 小区查询")
        st.caption("查询性能表中的小区数据（不关联映射表）")
        
        # 查询条件
        col1, col2 = st.columns(2)
        with col1:
            query_type = st.selectbox(
                "查询类型",
                ["按小区名称", "按CGI"],
                key="cell_query_type"
            )
        with col2:
            query_value = st.text_input(
                "查询值",
                placeholder="请输入查询条件",
                key="cell_query_value"
            )
        
        # 日期范围
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=7),
                key="cell_query_start_date"
            )
        with col2:
            end_date = st.date_input(
                "结束日期",
                value=date.today(),
                key="cell_query_end_date"
            )
        
        if st.button("开始查询", key="query_cells"):
            try:
                df = self._generate_cell_query(query_type, query_value, start_date, end_date)
                
                # 保存到session state（使用不同的key名称避免冲突）
                st.session_state['cell_query_df'] = df
                st.session_state['cell_query_type_saved'] = query_type
                st.session_state['cell_query_value_saved'] = query_value
                
                if not df.empty:
                    st.success(f"✅ 查询完成，共找到 {len(df)} 个小区")
                else:
                    st.warning("未找到匹配的小区")
                    
            except Exception as e:
                st.error(f"查询失败: {e}")
                self.logger.error(f"小区查询失败: {e}")
        
        # 显示查询结果
        if 'cell_query_df' in st.session_state and not st.session_state['cell_query_df'].empty:
            df = st.session_state['cell_query_df']
            
            st.dataframe(df, use_container_width=True)
            
            # 导出Excel文件
            if st.button("导出Excel文件", key="export_cell_query"):
                self._export_cell_query_excel(
                    df, 
                    st.session_state.get('cell_query_type_saved', '未知'), 
                    st.session_state.get('cell_query_value_saved', '')
                )

    def _generate_zero_traffic_analysis(self, start_date, end_date):
        """生成零流量分析（支持时间范围，按小区聚合）"""
        try:
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 第一步：查询所有映射小区，包括没有性能数据的小区
            # 使用 LEFT JOIN 获取所有映射小区，并关联工参表获取物理站信息
            query = '''
                SELECT DISTINCT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, 
                    c.if_cell, c.if_online, c.lon, c.lat, e.phy_name
                FROM cell_mapping c
                LEFT JOIN engineering_params e ON c.cgi = e.cgi
            '''
            
            all_cells_df = pd.DataFrame(self.db_manager.execute_query(query))
            
            if all_cells_df.empty:
                return pd.DataFrame()
            
            # 第二步：查询时间范围内有性能数据的小区
            query_with_data = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, 
                    c.if_cell, c.if_online, c.lon, c.lat, e.phy_name,
                    p.start_time, p.flwor_day
                FROM cell_mapping c
                LEFT JOIN engineering_params e ON c.cgi = e.cgi
                LEFT JOIN performance_data p ON c.cgi = p.cgi 
                    AND p.start_time BETWEEN ? AND ? 
                    AND p.data_type = 'capacity'
                WHERE p.cgi IS NOT NULL
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(
                query_with_data, [start_str, end_str]
            ))
            
            # 第三步：按小区聚合，计算统计信息
            def aggregate_date_flow(group):
                """聚合日期和流量信息为一列，格式：2025-10-17(1.23)、2025-10-18(2.34)"""
                # 先按日期去重，确保每个日期只有一条记录（如果同一日期有多条，取最后一条）
                # 提取日期部分（去掉时分秒）
                group_copy = group.copy()
                group_copy['date_only'] = pd.to_datetime(group_copy['start_time']).dt.date
                
                # 再次验证日期范围，确保只处理在指定日期范围内的数据
                start_date_only = start_date
                end_date_only = end_date
                group_copy = group_copy[
                    (group_copy['date_only'] >= start_date_only) & 
                    (group_copy['date_only'] <= end_date_only)
                ]
                
                if group_copy.empty:
                    return ''
                
                # 按日期分组，取每组最后一条记录（保持最新数据）
                deduplicated = group_copy.sort_values('start_time').drop_duplicates(subset=['date_only'], keep='last')
                # 按日期排序
                sorted_data = deduplicated.sort_values('start_time')
                # 组合日期和流量
                date_flow_list = []
                for _, row in sorted_data.iterrows():
                    if pd.notna(row['start_time']) and pd.notna(row['flwor_day']):
                        date_flow_list.append(f"{row['start_time']}({row['flwor_day']:.2f})")
                return '、'.join(date_flow_list) if date_flow_list else ''
            
            # 处理有数据的小区
            agg_dict = {
                'celname': 'first',
                'grid_id': 'first',
                'zhishi': 'first',
                'pinduan': 'first',
                'grid_name': 'first',
                'grid_pp': 'first',
                'tt_mark': 'first',
                'if_flag': 'first',
                'if_cell': 'first',
                'if_online': 'first',
                'lon': 'first',
                'lat': 'first',
                'phy_name': 'first',
                'flwor_day': ['count', 'mean', 'max']
            }
            
            # 处理有数据的小区
            if not df.empty:
                # 再次过滤日期范围，确保只统计指定日期范围内的数据
                df['start_time_dt'] = pd.to_datetime(df['start_time'])
                start_date_dt = pd.to_datetime(start_str)
                end_date_dt = pd.to_datetime(end_str)
                df_filtered = df[
                    (df['start_time_dt'] >= start_date_dt) & 
                    (df['start_time_dt'] <= end_date_dt)
                ].copy()
                
                if df_filtered.empty:
                    grouped_df = pd.DataFrame()
                else:
                    # 添加日期列用于计算天数
                    df_filtered['date_only'] = pd.to_datetime(df_filtered['start_time']).dt.date
                    
                    # 修改聚合字典，正确计算天数
                    agg_dict_corrected = agg_dict.copy()
                    agg_dict_corrected['date_only'] = 'nunique'  # 计算唯一日期数
                    
                    grouped_df = df_filtered.groupby('cgi').agg(agg_dict_corrected).reset_index()
                    
                    # 展平多级列名
                    grouped_df.columns = [
                        'cgi', 'celname', 'grid_id', 'zhishi', 'pinduan',
                        'grid_name', 'grid_pp', 'tt_mark', 'if_flag', 'if_cell',
                        'if_online', 'lon', 'lat', 'phy_name', 'data_days', 'avg_flow', 'max_flow', 'actual_days'
                    ]
                    
                    # 使用实际天数替换原来的记录数
                    grouped_df['data_days'] = grouped_df['actual_days']
                    grouped_df = grouped_df.drop('actual_days', axis=1)
                    
                    # 添加日期流量明细列（使用过滤后的数据）
                    date_flow_detail = df_filtered.groupby('cgi').apply(aggregate_date_flow).reset_index()
                    date_flow_detail.columns = ['cgi', 'date_flow_detail']
                    
                    # 合并数据
                    grouped_df = grouped_df.merge(date_flow_detail, on='cgi', how='left')
                
            else:
                grouped_df = pd.DataFrame()
            
            # 第四步：处理没有数据的小区
            # 从所有小区中筛选出有数据的小区
            if not grouped_df.empty:
                cells_with_data = set(grouped_df['cgi'].unique())
            else:
                cells_with_data = set()
            
            # 获取所有映射小区中，在查询时间段内没有数据的小区
            all_cgis = set(all_cells_df['cgi'].unique())
            cells_without_data = all_cgis - cells_with_data
            
            # 为没有数据的小区创建记录
            no_data_list = []
            for cgi in cells_without_data:
                cell_info = all_cells_df[all_cells_df['cgi'] == cgi].iloc[0]
                no_data_list.append({
                    'cgi': cgi,
                    'celname': cell_info.get('celname'),
                    'grid_id': cell_info.get('grid_id'),
                    'zhishi': cell_info.get('zhishi'),
                    'pinduan': cell_info.get('pinduan'),
                    'grid_name': cell_info.get('grid_name'),
                    'grid_pp': cell_info.get('grid_pp'),
                    'tt_mark': cell_info.get('tt_mark'),
                    'if_flag': cell_info.get('if_flag'),
                    'if_cell': cell_info.get('if_cell'),
                    'if_online': cell_info.get('if_online'),
                    'lon': cell_info.get('lon'),
                    'lat': cell_info.get('lat'),
                    'phy_name': cell_info.get('phy_name'),
                    'data_days': 0,
                    'avg_flow': 0.0,
                    'max_flow': 0.0,
                    'date_flow_detail': ''
                })
            
            no_data_df = pd.DataFrame(no_data_list)
            
            # 合并有数据和无数据的小区
            if not grouped_df.empty and not no_data_df.empty:
                full_df = pd.concat([grouped_df, no_data_df], ignore_index=True)
            elif not grouped_df.empty:
                full_df = grouped_df
            elif not no_data_df.empty:
                full_df = no_data_df
            else:
                return pd.DataFrame()
            
            # 重新判断制式（基于 pinduan 和 zhishi）
            full_df['network_type'] = full_df.apply(self.determine_network_type, axis=1)
            
            # 第五步：筛选零流量小区
            # 包括：1) 有数据但最大流量为0的小区  2) 完全没有数据的小区
            full_df['is_zero_flow'] = (
                (full_df['data_days'] == 0) |  # 没有数据的小区
                ((full_df['data_days'] > 0) & (full_df['max_flow'] == 0))  # 有数据但流量为0的小区
            )
            
            zero_df = full_df[full_df['is_zero_flow']].copy()
            
            # 删除辅助列
            zero_df = zero_df.drop(columns=['is_zero_flow', 'max_flow'])
            
            # 添加问题类型标签
            # 区分：完全没有数据的标记为"零流量小区"，有数据但流量为0的标记为"零流量"
            zero_df['问题类型'] = zero_df.apply(
                lambda row: '零流量小区' if row['data_days'] == 0 else '零流量',
                axis=1
            )
            
            # 重命名列名为中文
            chinese_columns = {
                'cgi': 'CGI',
                'celname': '小区名称',
                'grid_id': '网格ID',
                'zhishi': '制式(原始)',
                'pinduan': '频段',
                'network_type': '制式',
                'grid_name': '网格名称',
                'grid_pp': '网格标签',
                'tt_mark': '备注',
                'if_flag': '是否缓冲区',
                'if_cell': '是否映射小区',
                'if_online': '是否在网管',
                'lon': '经度',
                'lat': '纬度',
                'phy_name': '物理站',
                'data_days': '数据天数',
                'avg_flow': '日平均流量(GB)',
                'date_flow_detail': '日期流量明细'
            }
            zero_df = zero_df.rename(columns=chinese_columns)
            
            # 删除原始制式列
            if '制式(原始)' in zero_df.columns:
                zero_df = zero_df.drop(columns=['制式(原始)'])
            
            return zero_df
            
        except Exception as e:
            self.logger.error(f"生成零流量分析失败: {e}")
            return pd.DataFrame()

    def _generate_low_traffic_analysis(self, start_date, end_date, 
                                       threshold_4g, threshold_5g):
        """生成低流量分析（支持时间范围，按小区聚合）"""
        try:
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 第一步：查询时间范围内有性能数据的小区的流量数据
            # 注意：使用 INNER JOIN 只查询有数据的小区，避免 NULL 值影响聚合结果
            query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, 
                    c.if_cell, c.if_online, c.lon, c.lat, e.phy_name,
                    p.start_time, p.flwor_day
                FROM cell_mapping c
                INNER JOIN performance_data p ON c.cgi = p.cgi 
                    AND p.start_time BETWEEN ? AND ? 
                    AND p.data_type = 'capacity'
                LEFT JOIN engineering_params e ON c.cgi = e.cgi
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(
                query, [start_str, end_str]
            ))
            if df.empty:
                return pd.DataFrame()
            
            # 第二步：按小区聚合，计算统计信息
            # 再次过滤日期范围，确保只统计指定日期范围内的数据
            df['start_time_dt'] = pd.to_datetime(df['start_time'])
            start_date_dt = pd.to_datetime(start_str)
            end_date_dt = pd.to_datetime(end_str)
            df_filtered = df[
                (df['start_time_dt'] >= start_date_dt) & 
                (df['start_time_dt'] <= end_date_dt)
            ].copy()
            
            if df_filtered.empty:
                return pd.DataFrame()
            
            def aggregate_date_flow(group):
                """聚合日期和流量信息为一列，格式：2025-10-17(1.23)、2025-10-18(2.34)"""
                # 先按日期去重，确保每个日期只有一条记录（如果同一日期有多条，取最后一条）
                # 提取日期部分（去掉时分秒）
                group_copy = group.copy()
                group_copy['date_only'] = pd.to_datetime(group_copy['start_time']).dt.date
                
                # 再次验证日期范围，确保只处理在指定日期范围内的数据
                start_date_only = start_date
                end_date_only = end_date
                group_copy = group_copy[
                    (group_copy['date_only'] >= start_date_only) & 
                    (group_copy['date_only'] <= end_date_only)
                ]
                
                if group_copy.empty:
                    return ''
                
                # 按日期分组，取每组最后一条记录（保持最新数据）
                deduplicated = group_copy.sort_values('start_time').drop_duplicates(subset=['date_only'], keep='last')
                # 按日期排序
                sorted_data = deduplicated.sort_values('start_time')
                # 组合日期和流量
                date_flow_list = []
                for _, row in sorted_data.iterrows():
                    if pd.notna(row['start_time']) and pd.notna(row['flwor_day']):
                        date_flow_list.append(f"{row['start_time']}({row['flwor_day']:.2f})")
                return '、'.join(date_flow_list) if date_flow_list else ''
            
            agg_dict = {
                'celname': 'first',
                'grid_id': 'first',
                'zhishi': 'first',
                'pinduan': 'first',
                'grid_name': 'first',
                'grid_pp': 'first',
                'tt_mark': 'first',
                'if_flag': 'first',
                'if_cell': 'first',
                'if_online': 'first',
                'lon': 'first',
                'lat': 'first',
                'phy_name': 'first',
                'flwor_day': ['count', 'mean', 'max']
            }
            
            # 添加日期列用于计算天数
            df_filtered['date_only'] = pd.to_datetime(df_filtered['start_time']).dt.date
            
            # 修改聚合字典，正确计算天数
            agg_dict_corrected = agg_dict.copy()
            agg_dict_corrected['date_only'] = 'nunique'  # 计算唯一日期数
            
            # 先进行基本聚合（使用过滤后的数据）
            grouped_df = df_filtered.groupby('cgi').agg(agg_dict_corrected).reset_index()
            
            # 展平多级列名
            grouped_df.columns = [
                    'cgi', 'celname', 'grid_id', 'zhishi', 'pinduan',
                    'grid_name', 'grid_pp', 'tt_mark', 'if_flag', 'if_cell',
                'if_online', 'lon', 'lat', 'phy_name', 'data_days', 'avg_flow', 'max_flow', 'actual_days'
            ]
            
            # 使用实际天数替换原来的记录数
            grouped_df['data_days'] = grouped_df['actual_days']
            grouped_df = grouped_df.drop('actual_days', axis=1)
            
            # 添加日期流量明细列（使用过滤后的数据）
            date_flow_detail = df_filtered.groupby('cgi').apply(aggregate_date_flow).reset_index()
            date_flow_detail.columns = ['cgi', 'date_flow_detail']
            
            # 合并数据
            grouped_df = grouped_df.merge(date_flow_detail, on='cgi', how='left')
            
            # 重新判断制式（基于 pinduan 和 zhishi）
            grouped_df['network_type'] = grouped_df.apply(self.determine_network_type, axis=1)
            
            # 第三步：筛选低流量小区
            # 逻辑：查询时间段内平均流量 < 阈值 的小区
            # 条件：max_flow > 0（排除全零流量）且 avg_flow < 阈值
            low_4g = (grouped_df['network_type'] == '4g') & \
                     (grouped_df['max_flow'] > 0) & \
                     (grouped_df['avg_flow'] < threshold_4g)
            low_5g = (grouped_df['network_type'] == '5g') & \
                     (grouped_df['max_flow'] > 0) & \
                     (grouped_df['avg_flow'] < threshold_5g)
            
            grouped_df = grouped_df[low_4g | low_5g].copy()
            
            if grouped_df.empty:
                return pd.DataFrame()
            
            # 删除max_flow列（仅用于筛选）
            grouped_df = grouped_df.drop(columns=['max_flow'])
            
            # 添加问题类型标签
            grouped_df['问题类型'] = '低流量'
            
            # 重命名列名为中文
            chinese_columns = {
                'cgi': 'CGI',
                'celname': '小区名称',
                'grid_id': '网格ID',
                'zhishi': '制式(原始)',
                'pinduan': '频段',
                'network_type': '制式',
                'grid_name': '网格名称',
                'grid_pp': '网格标签',
                'tt_mark': '备注',
                'if_flag': '是否缓冲区',
                'if_cell': '是否映射小区',
                'if_online': '是否在网管',
                'lon': '经度',
                'lat': '纬度',
                'phy_name': '物理站',
                'data_days': '数据天数',
                'avg_flow': '日平均流量(GB)',
                'date_flow_detail': '日期流量明细'
            }
            grouped_df = grouped_df.rename(columns=chinese_columns)
            
            # 删除原始制式列
            if '制式(原始)' in grouped_df.columns:
                grouped_df = grouped_df.drop(columns=['制式(原始)'])
            
            return grouped_df
            
        except Exception as e:
            self.logger.error(f"生成低流量分析失败: {e}")
            return pd.DataFrame()

    def _generate_traffic_drop_analysis(self, before_start_date, before_end_date, 
                                        after_start_date, after_end_date, drop_threshold):
        """生成流量骤降分析（时间段对比）"""
        try:
            before_start_str = before_start_date.strftime('%Y-%m-%d 00:00:00')
            before_end_str = before_end_date.strftime('%Y-%m-%d 23:59:59')
            after_start_str = after_start_date.strftime('%Y-%m-%d 00:00:00')
            after_end_str = after_end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 使用 LEFT JOIN 查询，包含对比前有数据但对比后可能没有数据的小区
            compare_query = '''
                SELECT
                    before_data.cgi,
                    before_data.avg_flow_before,
                    after_data.avg_flow_after,
                    CASE 
                        WHEN after_data.avg_flow_after IS NULL THEN 1 
                        ELSE 0 
                    END as is_after_no_data
                FROM (
                    SELECT
                        cgi,
                        AVG(flwor_day) as avg_flow_before
                    FROM performance_data
                    WHERE start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    GROUP BY cgi
                ) before_data
                LEFT JOIN (
                    SELECT
                        cgi,
                        AVG(flwor_day) as avg_flow_after
                    FROM performance_data
                    WHERE start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    GROUP BY cgi
                ) after_data ON before_data.cgi = after_data.cgi
            '''
            
            compare_df = pd.DataFrame(self.db_manager.execute_query(
                compare_query, [before_start_str, before_end_str, after_start_str, after_end_str]
            ))
            
            if compare_df.empty:
                st.warning("⚠️ 对比前时间段内没有数据")
                return pd.DataFrame()
            
            # 处理对比后没有数据的情况
            compare_df['avg_flow_after'] = compare_df['avg_flow_after'].fillna(0)
            
            # 计算流量降幅
            compare_df['flow_drop_ratio'] = (
                (compare_df['avg_flow_before'] - compare_df['avg_flow_after']) / 
                compare_df['avg_flow_before'] * 100
            )
            
            # 计算流量下降（GB）
            compare_df['flow_drop_gb'] = compare_df['avg_flow_before'] - compare_df['avg_flow_after']
            
            # 筛选骤降小区（降幅 >= 阈值）
            threshold_ratio = drop_threshold
            drop_df = compare_df[compare_df['flow_drop_ratio'] >= threshold_ratio].copy()
            
            if drop_df.empty:
                st.info("✅ 未发现符合条件的流量骤降小区")
                return pd.DataFrame()
            
            # 关联小区映射信息和工程参数信息
            mapping_query = '''
                SELECT 
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.grid_name, c.grid_pp,
                    c.tt_mark, c.if_flag, c.if_cell, c.if_online, c.lon, c.lat,
                    e.phy_name, e.pinduan, e.antenna_name
                FROM cell_mapping c
                LEFT JOIN engineering_params e ON c.cgi = e.cgi
                WHERE c.cgi IN ({})
            '''.format(','.join(['?'] * len(drop_df)))
            
            mapping_df = pd.DataFrame(self.db_manager.execute_query(
                mapping_query, drop_df['cgi'].tolist()
            ))
            
            # 合并映射信息
            result_df = drop_df.merge(mapping_df, on='cgi', how='left')
            
            # 应用制式判断
            result_df['network_type'] = result_df.apply(self.determine_network_type, axis=1)
            
            # 处理对比后没有数据的情况，显示特殊标记
            def format_flow_value(row):
                if row['is_after_no_data'] == 1:
                    return "0（无数据）"
                else:
                    return f"{row['avg_flow_after']:.2f}"
            
            result_df['对比后平均流量(GB)'] = result_df.apply(format_flow_value, axis=1)
            
            # 重命名列名为中文
            chinese_columns = {
                'cgi': 'CGI',
                'celname': '小区名称',
                'grid_id': '网格ID',
                'zhishi': '制式(原始)',
                'network_type': '制式',
                'pinduan': '频段',
                'antenna_name': '天线名字',
                'grid_name': '网格名称',
                'grid_pp': '网格标签',
                'tt_mark': '备注',
                'if_flag': '是否缓冲区',
                'if_cell': '是否映射小区',
                'if_online': '是否在网管',
                'lon': '经度',
                'lat': '纬度',
                'phy_name': '物理站',
                'avg_flow_before': '对比前平均流量(GB)',
                'flow_drop_ratio': '流量降幅(%)',
                'flow_drop_gb': '流量下降(GB)'
            }
            result_df = result_df.rename(columns=chinese_columns)
            
            # 删除原始制式列
            if '制式(原始)' in result_df.columns:
                result_df = result_df.drop(columns=['制式(原始)'])
            
            # 按降幅排序
            result_df = result_df.sort_values('流量降幅(%)', ascending=False)
            
            return result_df
            
        except Exception as e:
            self.logger.error(f"生成流量骤降分析失败: {e}")
            st.error(f"生成流量骤降分析失败: {e}")
            return pd.DataFrame()

    def _generate_high_load_analysis(self, start_date, end_date):
        """生成高负荷小区分析"""
        try:
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 查询高负荷小区汇总（使用LEFT JOIN，即使不在映射表中也能显示）
            summary_query = '''
                SELECT
                    COALESCE(c.cgi, p.cgi) as cgi,
                    COALESCE(c.celname, p.celname) as celname,
                    c.grid_id,
                    COALESCE(c.zhishi, '') as zhishi,
                    COALESCE(c.pinduan, p.pinduan, '') as pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat,
                    COUNT(*) as 高负荷次数,
                    GROUP_CONCAT(p.start_time) as 高负荷日期
                FROM performance_data p
                LEFT JOIN cell_mapping c ON c.cgi = p.cgi
                WHERE p.if_overcel = 't'
                  AND p.start_time BETWEEN ? AND ?
                  AND p.data_type = 'capacity'
                GROUP BY COALESCE(c.cgi, p.cgi),
                         COALESCE(c.celname, p.celname),
                         c.grid_id, COALESCE(c.zhishi, ''),
                         COALESCE(c.pinduan, p.pinduan, ''),
                         c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                         c.lon, c.lat
                ORDER BY 高负荷次数 DESC
            '''
            
            summary_df = pd.DataFrame(self.db_manager.execute_query(summary_query, [start_str, end_str]))
            
            # 查询高负荷小区详细数据（使用LEFT JOIN，即使不在映射表中也能显示）
            detail_query = '''
                SELECT
                    COALESCE(c.cgi, p.cgi) as cgi,
                    COALESCE(c.celname, p.celname) as celname,
                    c.grid_id,
                    COALESCE(c.zhishi, '') as zhishi,
                    COALESCE(c.pinduan, p.pinduan, '') as pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day, p.if_overcel,
                    p.ul_prb_mang, p.dl_prb_mang, p.pdcch_mang, p.rrc_average, p.rrc_max
                FROM performance_data p
                LEFT JOIN cell_mapping c ON c.cgi = p.cgi
                WHERE p.if_overcel = 't'
                  AND p.start_time BETWEEN ? AND ?
                  AND p.data_type = 'capacity'
                ORDER BY COALESCE(c.cgi, p.cgi), p.start_time
            '''
            
            detail_df = pd.DataFrame(self.db_manager.execute_query(detail_query, [start_str, end_str]))
            
            # 重命名列名为中文
            chinese_columns = {
                'cgi': 'CGI',
                'celname': '小区名称',
                'grid_id': '网格ID',
                'zhishi': '制式',
                'pinduan': '频段',
                'grid_name': '网格名',
                'grid_pp': '网格标签',
                'tt_mark': '备注',
                'if_flag': '是否缓冲区',
                'if_cell': '是否映射小区',
                'if_online': '是否在网管',
                'lon': '经度',
                'lat': '纬度',
                'start_time': '日期',
                'flwor_day': '日流量',
                'if_overcel': '是否高负荷',
                'ul_prb_mang': '上行PRB利用率',
                'dl_prb_mang': '下行PRB利用率',
                'pdcch_mang': 'PDCCH利用率',
                'rrc_average': 'RRC平均连接数',
                'rrc_max': 'RRC最大连接数'
            }
            
            if not summary_df.empty:
                summary_df = summary_df.rename(columns=chinese_columns)
            if not detail_df.empty:
                detail_df = detail_df.rename(columns=chinese_columns)
            
            return summary_df, detail_df
            
        except Exception as e:
            self.logger.error(f"生成高负荷小区分析失败: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def _generate_cell_query(self, query_type, query_value, start_date, end_date):
        """生成小区查询（仅从性能表查询，不关联映射表）"""
        try:
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 根据查询类型构建查询条件（仅支持按CGI和按小区名称）
            if query_type == "按小区名称":
                where_condition = "p.celname LIKE ?"
                query_param = f"%{query_value}%"
            elif query_type == "按CGI":
                where_condition = "p.cgi LIKE ?"
                query_param = f"%{query_value}%"
            else:
                return pd.DataFrame()
            
            # 直接从性能表查询，不关联映射表
            query = f'''
                SELECT
                    p.cgi, p.celname, p.pinduan, p.phy_name, p.cco_area_name,
                    p.start_time, p.flwor_day, p.if_overcel,
                    p.ul_prb_mang, p.dl_prb_mang, p.pdcch_mang, 
                    p.rrc_average, p.rrc_max, p.flwor_ul_mang, p.flwor_dl_mang, p.prb_max
                FROM performance_data p
                WHERE p.start_time BETWEEN ? AND ? 
                    AND p.data_type = 'capacity'
                    AND {where_condition}
                ORDER BY p.cgi, p.start_time
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(query, [start_str, end_str, query_param]))
            
            if df.empty:
                return pd.DataFrame()
            
            # 重命名列名为中文
            chinese_columns = {
                'cgi': 'CGI',
                'celname': '小区名称',
                'pinduan': '频段',
                'phy_name': '物理站',
                'cco_area_name': 'CCO区域名称',
                'start_time': '日期',
                'flwor_day': '日流量(GB)',
                'if_overcel': '是否高负荷',
                'ul_prb_mang': '上行PRB利用率',
                'dl_prb_mang': '下行PRB利用率',
                'pdcch_mang': 'PDCCH利用率',
                'rrc_average': 'RRC平均连接数',
                'rrc_max': 'RRC最大连接数',
                'flwor_ul_mang': '上行流量(GB)',
                'flwor_dl_mang': '下行流量(GB)',
                'prb_max': 'PRB最大值'
            }
            df = df.rename(columns=chinese_columns)
            
            return df
            
        except Exception as e:
            self.logger.error(f"生成小区查询失败: {e}")
            return pd.DataFrame()

    def _export_zero_low_traffic_excel(self, zero_df, low_df, start_date, end_date, threshold_4g, threshold_5g):
        """导出零低流量分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"零低流量分析报告_{start_date}至{end_date}_{timestamp}.xlsx"
            
            # 复制数据框，避免修改原始数据
            zero_export = zero_df.copy() if not zero_df.empty else pd.DataFrame()
            low_export = low_df.copy() if not low_df.empty else pd.DataFrame()
            
            # 更新零流量小区的问题类型
            if not zero_export.empty and '问题类型' in zero_export.columns:
                zero_export['问题类型'] = '零流量（流量为0）'
            
            # 更新低流量小区的问题类型（根据制式显示不同阈值）
            if not low_export.empty and '问题类型' in low_export.columns:
                if '制式' in low_export.columns:
                    # 根据制式设置不同的问题类型描述
                    low_export['问题类型'] = low_export['制式'].apply(
                        lambda x: f'低流量（流量低于{threshold_5g}GB）' if x == '5g' 
                        else f'低流量（流量低于{threshold_4g}GB）'
                    )
                else:
                    # 如果没有制式列，使用4G阈值作为默认
                    low_export['问题类型'] = f'低流量（流量低于{threshold_4g}GB）'
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if not zero_export.empty:
                    zero_export.to_excel(writer, sheet_name='零流量小区', index=False)
                if not low_export.empty:
                    low_export.to_excel(writer, sheet_name='低流量小区', index=False)
            
            # 提供下载
            st.download_button(
                label="下载Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出零低流量分析Excel失败: {e}")

    def _export_traffic_drop_excel(self, df, before_start, before_end, after_start, after_end):
        """导出流量骤降分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"流量骤降分析报告_对比前{before_start}至{before_end}_对比后{after_start}至{after_end}_{timestamp}.xlsx"
            
            # 定义列顺序
            column_order = [
                'CGI', '小区名称', '制式', '频段', '天线名字', '物理站', '网格ID', '网格名称', '网格标签', '备注',
                '是否缓冲区', '是否映射小区', '是否在网管', '对比前平均流量(GB)', '对比后平均流量(GB)',
                'avg_flow_after', 'is_after_no_data', '流量降幅(%)', '流量下降(GB)', '经度', '纬度'
            ]
            
            # 重新排列列顺序，只保留存在的列
            existing_columns = [col for col in column_order if col in df.columns]
            df_reordered = df[existing_columns]
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_reordered.to_excel(writer, sheet_name="流量骤降分析", index=False)
            
            # 提供下载
            st.download_button(
                label="下载Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出流量骤降分析Excel失败: {e}")

    def _export_high_load_excel(self, summary_df, detail_df, start_date, end_date):
        """导出高负荷小区分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"高负荷小区分析报告_{start_date}_{end_date}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if not summary_df.empty:
                    summary_df.to_excel(writer, sheet_name='小区汇总清单', index=False)
                if not detail_df.empty:
                    detail_df.to_excel(writer, sheet_name='小区负荷详细清单', index=False)
            
            # 提供下载
            st.download_button(
                label="下载Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出高负荷小区分析Excel失败: {e}")

    def _export_cell_query_excel(self, df, query_type, query_value):
        """导出小区查询Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"小区查询结果_{query_type}_{query_value}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="小区查询结果", index=False)
            
            # 提供下载
            st.download_button(
                label="下载Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出小区查询Excel失败: {e}")
    
    def _get_available_dates(self):
        """获取数据库中有数据的日期列表"""
        try:
            query = '''
                SELECT DISTINCT DATE(start_time) as date_str
                FROM performance_data
                WHERE data_type = 'capacity'
                ORDER BY date_str DESC
                LIMIT 90
            '''
            result = self.db_manager.execute_query(query)
            if result:
                # 将字符串日期转换为 date 对象
                dates = []
                for row in result:
                    date_str = row['date_str']
                    if date_str:
                        try:
                            # 解析日期字符串
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            dates.append(date_obj)
                        except:
                            pass
                return dates
            return []
        except Exception as e:
            self.logger.error(f"获取可用日期失败: {e}")
            return []
    
    def _display_date_availability(self, available_dates, start_date, end_date):
        """显示日期可用性提示"""
        try:
            if not available_dates:
                return
            
            # 获取最早和最晚的数据日期
            min_date = min(available_dates)
            max_date = max(available_dates)
            
            # 检查选择的日期范围内有多少天有数据
            selected_dates = []
            current = start_date
            while current <= end_date:
                if current in available_dates:
                    selected_dates.append(current)
                current += timedelta(days=1)
            
            # 显示提示信息
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if selected_dates:
                    st.success(f"✅ 选择范围内有 {len(selected_dates)} 天有数据")
                else:
                    st.warning(f"⚠️ 选择范围内没有数据")
            
            with col2:
                with st.expander("📅 查看详情"):
                    st.write(f"**数据日期范围：**")
                    st.write(f"最早：{min_date}")
                    st.write(f"最晚：{max_date}")
                    st.write(f"**共 {len(available_dates)} 天**")
                    
                    if len(selected_dates) > 0:
                        st.write(f"\n**已选范围内的数据日期：**")
                        # 显示最多前10个日期
                        display_dates = sorted(selected_dates, reverse=True)[:10]
                        for d in display_dates:
                            st.write(f"🟢 {d}")
                        if len(selected_dates) > 10:
                            st.write(f"... 还有 {len(selected_dates) - 10} 天")
                    
        except Exception as e:
            self.logger.error(f"显示日期可用性失败: {e}")

    def _find_traffic_drop_date(self, daily_data, drop_threshold=50, window_size=7):
        """使用滑动窗口算法查找流量突降日期
        
        算法思路：
        1. 使用滑动窗口计算每个窗口的平均流量
        2. 窗口大小：可自定义（默认7天）
        3. 阈值：可自定义（默认50%）
        4. 检查前窗口和后窗口的平均流量变化
        
        Args:
            daily_data: DataFrame，包含date和flwor_day列
            drop_threshold: 下降阀值（百分比），默认50%
            window_size: 滑动窗口大小（天），默认7天
            
        Returns:
            datetime.date: 突降日期，如果未找到突降则返回None
        """
        try:
            # 至少需要3个窗口的数据（前窗口 + 突降日 + 后续窗口）
            min_days = window_size * 2 + 1
            if len(daily_data) < min_days:
                return None
            
            # 计算阈值比例
            threshold_ratio = drop_threshold / 100.0
            
            # 遍历数据，查找突降点
            for i in range(window_size, len(daily_data)):
                current_date = daily_data.iloc[i]['date']
                current_flow = daily_data.iloc[i]['flwor_day']
                
                # 前窗口（突降前的N天，不包括当前日）
                before_window = daily_data.iloc[i-window_size:i]
                if len(before_window) < window_size:
                    continue
                
                avg_before = before_window['flwor_day'].mean()
                
                # 后窗口（突降后的N天，包括当前日）
                after_window = daily_data.iloc[i:i+window_size]
                if len(after_window) < window_size:
                    continue
                
                avg_after = after_window['flwor_day'].mean()
                
                # 动态阈值判断：
                # 1. 前窗口平均流量 > 1GB
                # 2. 当前日流量 < 前窗口平均 * (1 - threshold_ratio)（下降超过阈值）
                # 3. 后窗口平均流量 < 前窗口平均 * (1 - threshold_ratio * 1.5)（确认持续低流量）
                drop_ratio = 1 - threshold_ratio
                confirm_ratio = 1 - threshold_ratio * 1.5
                
                if (avg_before > 1.0 and 
                    current_flow < avg_before * drop_ratio and 
                    avg_after < avg_before * confirm_ratio):
                    
                    # 找到第一个符合条件的日期作为突降日期
                    return current_date
            
            # 如果没找到明确的突降点，尝试更宽松的条件
            # 仅检查当前日流量对比前窗口平均是否下降超过阈值
            for i in range(window_size, len(daily_data)):
                current_date = daily_data.iloc[i]['date']
                current_flow = daily_data.iloc[i]['flwor_day']
                
                before_window = daily_data.iloc[i-window_size:i]
                if len(before_window) < window_size:
                    continue
                
                avg_before = before_window['flwor_day'].mean()
                drop_ratio = 1 - threshold_ratio
                
                # 更宽松的条件：前窗口平均 > 1GB 且当前日流量 < 前窗口平均 * drop_ratio
                if avg_before > 1.0 and current_flow < avg_before * drop_ratio:
                    return current_date
            
            return None
            
        except Exception as e:
            self.logger.error(f"查找流量突降日期失败: {e}")
            return None

    def _render_traffic_spike_analysis(self):
        """渲染流量突降分析页面"""
        st.subheader("🎯 流量突降分析")
        st.caption("分析指定CGI在时间段内的流量突降情况")
        
        # 输入配置
        st.markdown("#### 📋 输入配置")
        
        # 分析类型选择
        analysis_type = st.radio(
            "选择分析类型",
            ["指定CGI分析", "全网小区分析", "扇区级分析"],
            horizontal=True,
            key="traffic_spike_analysis_type"
        )
        
        cgi_input = ""
        if analysis_type == "指定CGI分析":
            # CGI输入
            st.markdown("**CGI列表（每行一个）**")
            cgi_input = st.text_area(
                "输入CGI（每行一个）",
                height=150,
                help="可输入一个或多个CGI，每行一个",
                placeholder="460-00-12635644-1\n460-00-12635523-16\n460-00-12635495-3"
            )
        elif analysis_type == "全网小区分析":
            st.info("🌐 全网小区分析：将分析所有工参小区，可能需要较长时间")
        else:
            st.info("🏢 扇区级分析：分析扇区整体下降vs单个小区下降，判断是否共天线")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "开始日期",
                value=date.today() - timedelta(days=30),
                key="spike_start_date"
            )
        with col2:
            end_date = st.date_input(
                "结束日期",
                value=date.today(),
                key="spike_end_date"
            )
        
        st.markdown("#### ⚙️ 分析参数配置")
        col3, col4 = st.columns(2)
        with col3:
            drop_threshold = st.slider(
                "下降阀值 (%)",
                min_value=10,
                max_value=90,
                value=50,
                step=5,
                help="流量相比前一个窗口下降的比例，超过此值认为是突降"
            )
        with col4:
            window_size = st.slider(
                "滑动窗口 (天)",
                min_value=3,
                max_value=14,
                value=7,
                step=1,
                help="滑动窗口大小，用于计算平均流量和判断突降"
            )
        
        st.info(f"📊 当前配置：下降阀值 {drop_threshold}%，滑动窗口 {window_size} 天")
        
        # 分析按钮
        if st.button("🔍 开始分析", type="primary", use_container_width=True):
            if analysis_type == "指定CGI分析":
                if not cgi_input.strip():
                    st.error("请输入至少一个CGI")
                    return
                
                # 解析CGI列表
                cgi_list = [cgi.strip() for cgi in cgi_input.strip().split('\n') if cgi.strip()]
                
                if not cgi_list:
                    st.error("请输入有效的CGI")
                    return
                
                st.info(f"📊 分析 {len(cgi_list)} 个CGI的流量突降情况...")
                result_df = self._generate_traffic_spike_analysis(cgi_list, start_date, end_date, drop_threshold, window_size)
                
            elif analysis_type == "全网小区分析":
                # 全网小区分析：获取所有映射小区
                cgi_list = None
                st.info(f"🌐 全网小区分析中...")
                result_df = self._generate_traffic_spike_analysis_with_progress(cgi_list, start_date, end_date, drop_threshold, window_size)
                
            else:
                # 扇区级分析
                st.info(f"🏢 扇区级分析中...")
                result_df = self._generate_sector_level_analysis(start_date, end_date, drop_threshold, window_size)
            
            st.info(f"⚙️ 分析参数：下降阀值 {drop_threshold}%，滑动窗口 {window_size} 天")
            
            if not result_df.empty:
                if analysis_type == "扇区级分析":
                    st.success(f"✅ 扇区级分析完成，共分析 {len(result_df)} 个扇区")
                    
                    # 显示扇区级分析结果
                    st.markdown("#### 📊 扇区级分析结果")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    
                    # 显示统计信息
                    st.markdown("#### 📈 分析统计")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        sector_total = len(result_df)
                        st.metric("分析扇区数", sector_total)
                    with col2:
                        sector_drop = len(result_df[result_df['下降类型'] == '扇区整体下降'])
                        st.metric("扇区整体下降", sector_drop)
                    with col3:
                        cell_drop = len(result_df[result_df['下降类型'] == '单个/部分小区下降'])
                        st.metric("单个小区下降", cell_drop)
                    
                    # 导出功能
                    st.markdown("#### 📥 导出功能")
                    self._export_sector_analysis_excel(result_df, start_date, end_date)
                else:
                    st.success(f"✅ 分析完成，共找到 {len(result_df)} 个流量突降小区")
                    
                    # 显示结果
                    st.markdown("#### 📊 分析结果")
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    
                    # 导出Excel
                    self._export_traffic_spike_excel(result_df, start_date, end_date)
            else:
                st.info("ℹ️ 未发现流量突降情况")
    
    def _generate_traffic_spike_analysis_with_progress(self, cgi_list, start_date, end_date, drop_threshold=50, window_size=7):
        """生成流量突降分析（带进度条）"""
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 标记是否为全网分析
            is_network_wide = (cgi_list is None)
            
            # 如果cgi_list为None，获取所有有数据小区的数量（用于进度条）
            if is_network_wide:
                status_text.text("🔍 步骤 1/5: 统计全网有性能数据的小区...")
                progress_bar.progress(5)
                
                start_str = start_date.strftime('%Y-%m-%d 00:00:00')
                end_str = end_date.strftime('%Y-%m-%d 23:59:59')
                
                # 统计有数据的小区数量
                count_query = "SELECT COUNT(DISTINCT cgi) as count FROM performance_data WHERE start_time BETWEEN ? AND ? AND data_type = 'capacity'"
                count_result = self.db_manager.execute_query(count_query, [start_str, end_str])
                total_cgis = count_result[0]['count'] if count_result else 0
                
                if total_cgis == 0:
                    progress_bar.empty()
                    status_text.empty()
                    return pd.DataFrame()
            else:
                total_cgis = len(cgi_list)
            
            status_text.text(f"📊 步骤 2/5: 查询 {total_cgis} 个CGI的流量数据...")
            progress_bar.progress(20)
            
            # 查询流量数据
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            if is_network_wide:
                # 全网分析：直接查询时间范围内的所有数据
                query = '''
                    SELECT
                        cgi,
                        start_time,
                        flwor_day
                    FROM performance_data
                    WHERE start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    ORDER BY cgi, start_time
                '''
                params = [start_str, end_str]
            else:
                # 指定CGI分析：使用IN查询
                query = '''
                    SELECT
                        cgi,
                        start_time,
                        flwor_day
                    FROM performance_data
                    WHERE cgi IN ({})
                        AND start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    ORDER BY cgi, start_time
                '''.format(','.join(['?'] * len(cgi_list)))
                params = cgi_list + [start_str, end_str]
            
            data = self.db_manager.execute_query(query, params)
            
            if not data:
                progress_bar.empty()
                status_text.empty()
                return pd.DataFrame()
            
            status_text.text(f"🔍 步骤 3/5: 分析 {total_cgis} 个CGI的流量突降情况...")
            progress_bar.progress(40)
            
            df = pd.DataFrame(data)
            df['start_time'] = pd.to_datetime(df['start_time'])
            df['date'] = df['start_time'].dt.date
            
            # 按CGI分组分析（优化：一次性按CGI分组，减少重复筛选）
            status_text.text(f"🔍 步骤 3/5: 按CGI分组数据...")
            progress_bar.progress(45)
            
            # 一次性按CGI分组
            grouped = df.groupby('cgi')
            
            # 按CGI分组分析
            results = []
            total_cgis_analyzed = len(grouped)
            
            min_required_days = window_size * 2 + 1
            
            # 为每个CGI添加增量进度显示
            for idx, (cgi, cgi_data) in enumerate(grouped):
                if (idx + 1) % 100 == 0:
                    progress = 50 + int((idx + 1) / total_cgis_analyzed * 30)
                    status_text.text(f"🔍 步骤 3/5: 已分析 {idx + 1}/{total_cgis_analyzed} 个CGI...")
                    progress_bar.progress(progress)
                
                # 至少需要足够的window_size数据才能分析
                if len(cgi_data) < min_required_days:
                    continue
                
                # 按日期聚合
                daily_data = cgi_data.groupby('date')['flwor_day'].mean().reset_index()
                daily_data = daily_data.sort_values('date')
                
                # 使用滑动窗口算法查找流量突降
                drop_date = self._find_traffic_drop_date(daily_data, drop_threshold, window_size)
                
                if drop_date is None:
                    continue
                
                # 计算突降前7日流量（不包括突降日）
                before_7days = daily_data[daily_data['date'] < drop_date].tail(7)
                avg_before = before_7days['flwor_day'].mean() if len(before_7days) >= 7 else 0
                
                # 计算突降后7日流量（包括突降日）
                after_7days = daily_data[daily_data['date'] >= drop_date].head(7)
                avg_after = after_7days['flwor_day'].mean() if len(after_7days) >= 7 else 0
                
                # 下降比例
                drop_ratio = ((avg_before - avg_after) / avg_before * 100) if avg_before > 0 else 0
                
                # 目前最新7日流量（最近7天）
                latest_7days = daily_data.tail(7)
                latest_7day = latest_7days['flwor_day'].mean() if len(latest_7days) >= 7 else 0
                
                # 判断是否恢复
                recovery_threshold = avg_before * 0.5
                if latest_7day >= recovery_threshold:
                    conclusion = "已恢复"
                else:
                    conclusion = "未恢复"
                
                results.append({
                    'cgi': cgi,
                    'drop_date': drop_date,
                    'avg_before': avg_before,
                    'avg_after': avg_after,
                    'drop_ratio': drop_ratio,
                    'latest_7day': latest_7day,
                    'conclusion': conclusion
                })
            
            status_text.text("✅ 步骤 4/5: 关联小区信息...")
            progress_bar.progress(85)
            
            if not results:
                progress_bar.empty()
                status_text.empty()
                return pd.DataFrame()
            
            result_df = pd.DataFrame(results)
            result_df['drop_date_str'] = result_df['drop_date'].apply(lambda x: x.strftime('%m月%d日'))
            
            # 关联小区信息（从工参表获取）
            mapping_query = '''
                SELECT 
                    cgi, celname, zhishi, phy_name, antenna_name,
                    grid_id_no_buffer, grid_name_no_buffer, grid_label_no_buffer,
                    grid_id_buffer_500m, grid_name_buffer_500m, grid_label_buffer_500m
                FROM engineering_params
                WHERE cgi IN ({})
            '''.format(','.join(['?'] * len(result_df)))
            
            mapping_df = pd.DataFrame(self.db_manager.execute_query(
                mapping_query, result_df['cgi'].tolist()
            ))
            
            # 合并信息
            result_df = result_df.merge(mapping_df, on='cgi', how='left')
            
            # 构建最终结果（只保留指定列，合并网格字段）
            final_results = []
            for _, row in result_df.iterrows():
                # 合并网格ID：将不缓冲和缓冲500米的网格ID合并
                grid_id_no_buffer = str(row.get('grid_id_no_buffer', '')).strip() if row.get('grid_id_no_buffer') else ''
                grid_id_buffer_500m = str(row.get('grid_id_buffer_500m', '')).strip() if row.get('grid_id_buffer_500m') else ''
                grid_id_list = []
                if grid_id_no_buffer:
                    grid_id_list.append(grid_id_no_buffer)
                if grid_id_buffer_500m:
                    grid_id_list.append(grid_id_buffer_500m)
                grid_id = ','.join(grid_id_list) if grid_id_list else ''
                
                # 合并网格名：将不缓冲和缓冲500米的网格名合并
                grid_name_no_buffer = str(row.get('grid_name_no_buffer', '')).strip() if row.get('grid_name_no_buffer') else ''
                grid_name_buffer_500m = str(row.get('grid_name_buffer_500m', '')).strip() if row.get('grid_name_buffer_500m') else ''
                grid_name_list = []
                if grid_name_no_buffer:
                    grid_name_list.append(grid_name_no_buffer)
                if grid_name_buffer_500m:
                    grid_name_list.append(grid_name_buffer_500m)
                grid_name = ','.join(grid_name_list) if grid_name_list else ''
                
                # 合并网格标签：将不缓冲和缓冲500米的网格标签合并
                grid_label_no_buffer = str(row.get('grid_label_no_buffer', '')).strip() if row.get('grid_label_no_buffer') else ''
                grid_label_buffer_500m = str(row.get('grid_label_buffer_500m', '')).strip() if row.get('grid_label_buffer_500m') else ''
                grid_label_list = []
                if grid_label_no_buffer:
                    grid_label_list.append(grid_label_no_buffer)
                if grid_label_buffer_500m:
                    grid_label_list.append(grid_label_buffer_500m)
                grid_label = ','.join(grid_label_list) if grid_label_list else ''
                
                final_results.append({
                    'CGI': row['cgi'],
                    '小区名称': row.get('celname', ''),
                    '制式': row.get('zhishi', ''),
                    '物理站': row.get('phy_name', ''),
                    '天线': row.get('antenna_name', ''),
                    '网格ID': grid_id,
                    '网格名': grid_name,
                    '网格标签': grid_label,
                    '突降前流量日平均(GB)': round(row['avg_before'], 2),
                    '突降后流量日平均(GB)': round(row['avg_after'], 2),
                    '流量下降日期': row['drop_date_str'],
                    '下降比例': round(row['drop_ratio'], 2),
                    '目前最新7日日流量(GB)': round(row['latest_7day'], 2),
                    '结论': row.get('conclusion', '')
                })
            
            status_text.text(f"✅ 步骤 5/5: 分析完成，共发现 {len(final_results)} 个突降小区")
            progress_bar.progress(100)
            
            # 清空进度条
            progress_bar.empty()
            status_text.empty()
            
            return pd.DataFrame(final_results)
            
        except Exception as e:
            if 'progress_bar' in locals():
                progress_bar.empty()
            if 'status_text' in locals():
                status_text.empty()
            st.error(f"分析失败: {e}")
            self.logger.error(f"生成流量突降分析失败: {e}")
            return pd.DataFrame()
    
    def _generate_traffic_spike_analysis(self, cgi_list, start_date, end_date, drop_threshold=50, window_size=7):
        """生成流量突降分析"""
        try:
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            # 查询流量数据
            if cgi_list is None:
                # 全网小区分析：直接查询时间范围内的所有数据
                query = '''
                    SELECT
                        cgi,
                        start_time,
                        flwor_day
                    FROM performance_data
                    WHERE start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    ORDER BY cgi, start_time
                '''
                params = [start_str, end_str]
                
                # 如果需要获取cgi_list供后续使用（虽然下面逻辑改了，但为了兼容）
                # 注意：这里不需要显式获取所有CGI列表，因为我们直接遍历查询结果
            else:
                query = '''
                    SELECT
                        cgi,
                        start_time,
                        flwor_day
                    FROM performance_data
                    WHERE cgi IN ({})
                        AND start_time BETWEEN ? AND ?
                        AND data_type = 'capacity'
                    ORDER BY cgi, start_time
                '''.format(','.join(['?'] * len(cgi_list)))
                params = cgi_list + [start_str, end_str]
            
            data = self.db_manager.execute_query(query, params)
            
            if not data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data)
            df['start_time'] = pd.to_datetime(df['start_time'])
            df['date'] = df['start_time'].dt.date
            
            # 按CGI分组分析
            results = []
            
            # 使用groupby一次性分组，比遍历cgi_list更高效且支持全网分析
            grouped = df.groupby('cgi')
            
            for cgi, cgi_data in grouped:
                # 至少需要足够的window_size数据才能分析
                min_required_days = window_size * 2 + 1
                if len(cgi_data) < min_required_days:
                    continue
                
                # 按日期聚合
                daily_data = cgi_data.groupby('date')['flwor_day'].mean().reset_index()
                daily_data = daily_data.sort_values('date')
                
                # 使用滑动窗口算法查找流量突降
                drop_date = self._find_traffic_drop_date(daily_data, drop_threshold, window_size)
                
                if drop_date is None:
                    continue
                
                # 计算突降前7日流量（不包括突降日）
                before_7days = daily_data[daily_data['date'] < drop_date].tail(7)
                avg_before = before_7days['flwor_day'].mean() if len(before_7days) >= 7 else 0
                
                # 计算突降后7日流量（包括突降日）
                after_7days = daily_data[daily_data['date'] >= drop_date].head(7)
                avg_after = after_7days['flwor_day'].mean() if len(after_7days) >= 7 else 0
                
                # 下降比例
                drop_ratio = ((avg_before - avg_after) / avg_before * 100) if avg_before > 0 else 0
                
                # 目前最新7日流量（最近7天）
                latest_7days = daily_data.tail(7)
                latest_7day = latest_7days['flwor_day'].mean() if len(latest_7days) >= 7 else 0
                
                # 判断是否恢复
                # 如果最新7日流量 >= 突降前流量 * 0.5，认为已恢复
                recovery_threshold = avg_before * 0.5
                if latest_7day >= recovery_threshold:
                    conclusion = "已恢复"
                else:
                    conclusion = "未恢复"
                
                results.append({
                    'cgi': cgi,
                    'drop_date': drop_date,
                    'avg_before': avg_before,
                    'avg_after': avg_after,
                    'drop_ratio': drop_ratio,
                    'latest_7day': latest_7day,
                    'conclusion': conclusion
                })
            
            if not results:
                return pd.DataFrame()
            
            result_df = pd.DataFrame(results)
            result_df['drop_date_str'] = result_df['drop_date'].apply(lambda x: x.strftime('%m月%d日'))
            
            # 关联小区信息（从工参表获取）
            mapping_query = '''
                SELECT 
                    cgi, celname, zhishi, phy_name, antenna_name,
                    grid_id_no_buffer, grid_name_no_buffer, grid_label_no_buffer,
                    grid_id_buffer_500m, grid_name_buffer_500m, grid_label_buffer_500m
                FROM engineering_params
                WHERE cgi IN ({})
            '''.format(','.join(['?'] * len(result_df)))
            
            mapping_df = pd.DataFrame(self.db_manager.execute_query(
                mapping_query, result_df['cgi'].tolist()
            ))
            
            # 合并信息
            result_df = result_df.merge(mapping_df, on='cgi', how='left')
            
            # 构建最终结果（只保留指定列，合并网格字段）
            final_results = []
            for _, row in result_df.iterrows():
                # 合并网格ID：将不缓冲和缓冲500米的网格ID合并
                grid_id_no_buffer = str(row.get('grid_id_no_buffer', '')).strip() if row.get('grid_id_no_buffer') else ''
                grid_id_buffer_500m = str(row.get('grid_id_buffer_500m', '')).strip() if row.get('grid_id_buffer_500m') else ''
                grid_id_list = []
                if grid_id_no_buffer:
                    grid_id_list.append(grid_id_no_buffer)
                if grid_id_buffer_500m:
                    grid_id_list.append(grid_id_buffer_500m)
                grid_id = ','.join(grid_id_list) if grid_id_list else ''
                
                # 合并网格名：将不缓冲和缓冲500米的网格名合并
                grid_name_no_buffer = str(row.get('grid_name_no_buffer', '')).strip() if row.get('grid_name_no_buffer') else ''
                grid_name_buffer_500m = str(row.get('grid_name_buffer_500m', '')).strip() if row.get('grid_name_buffer_500m') else ''
                grid_name_list = []
                if grid_name_no_buffer:
                    grid_name_list.append(grid_name_no_buffer)
                if grid_name_buffer_500m:
                    grid_name_list.append(grid_name_buffer_500m)
                grid_name = ','.join(grid_name_list) if grid_name_list else ''
                
                # 合并网格标签：将不缓冲和缓冲500米的网格标签合并
                grid_label_no_buffer = str(row.get('grid_label_no_buffer', '')).strip() if row.get('grid_label_no_buffer') else ''
                grid_label_buffer_500m = str(row.get('grid_label_buffer_500m', '')).strip() if row.get('grid_label_buffer_500m') else ''
                grid_label_list = []
                if grid_label_no_buffer:
                    grid_label_list.append(grid_label_no_buffer)
                if grid_label_buffer_500m:
                    grid_label_list.append(grid_label_buffer_500m)
                grid_label = ','.join(grid_label_list) if grid_label_list else ''
                
                final_results.append({
                    'CGI': row['cgi'],
                    '小区名称': row.get('celname', ''),
                    '制式': row.get('zhishi', ''),
                    '物理站': row.get('phy_name', ''),
                    '天线': row.get('antenna_name', ''),
                    '网格ID': grid_id,
                    '网格名': grid_name,
                    '网格标签': grid_label,
                    '突降前流量日平均(GB)': round(row['avg_before'], 2),
                    '突降后流量日平均(GB)': round(row['avg_after'], 2),
                    '流量下降日期': row['drop_date_str'],
                    '下降比例': round(row['drop_ratio'], 2),
                    '目前最新7日日流量(GB)': round(row['latest_7day'], 2),
                    '结论': row.get('conclusion', '')
                })
            
            return pd.DataFrame(final_results)
            
        except Exception as e:
            self.logger.error(f"生成流量突降分析失败: {e}")
            st.error(f"生成流量突降分析失败: {e}")
            return pd.DataFrame()
    
    def _export_traffic_spike_excel(self, df, start_date, end_date):
        """导出流量突降分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"流量突降分析报告_{start_date}至{end_date}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="流量突降分析", index=False)
            
            # 提供下载
            st.download_button(
                label="📥 下载Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出流量突降分析Excel失败: {e}")
    
    def _export_sector_analysis_excel(self, df, start_date, end_date):
        """导出扇区级分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"扇区级流量突降分析_{start_date}至{end_date}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="扇区级分析", index=False)
            
            # 提供下载
            st.download_button(
                label="📥 下载扇区级分析Excel文件",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        except Exception as e:
            st.error(f"导出失败: {e}")
            self.logger.error(f"导出扇区级分析Excel失败: {e}")
    
    def _generate_sector_level_analysis(self, start_date, end_date, drop_threshold=50, window_size=7):
        """生成扇区级流量突降分析"""
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 步骤1：获取所有工参小区
            status_text.text("🔍 步骤 1/6: 获取所有工参小区...")
            progress_bar.progress(10)
            
            mapping_query = "SELECT DISTINCT cgi FROM engineering_params WHERE cgi IS NOT NULL"
            mapping_result = self.db_manager.execute_query(mapping_query)
            all_cgis = [row['cgi'] for row in mapping_result]
            
            if not all_cgis:
                progress_bar.empty()
                status_text.empty()
                return pd.DataFrame()
            
            # 步骤2：查询流量数据
            status_text.text(f"📊 步骤 2/6: 查询 {len(all_cgis)} 个CGI的流量数据...")
            progress_bar.progress(20)
            
            start_str = start_date.strftime('%Y-%m-%d 00:00:00')
            end_str = end_date.strftime('%Y-%m-%d 23:59:59')
            
            query = '''
                SELECT
                    cgi,
                    start_time,
                    flwor_day,
                    cco_area_name
                FROM performance_data
                WHERE cgi IN ({})
                    AND start_time BETWEEN ? AND ?
                    AND data_type = 'capacity'
                ORDER BY cgi, start_time
            '''.format(','.join(['?'] * len(all_cgis)))
            
            params = all_cgis + [start_str, end_str]
            data = self.db_manager.execute_query(query, params)
            
            if not data:
                progress_bar.empty()
                status_text.empty()
                return pd.DataFrame()
            
            # 步骤3：识别流量突降小区
            status_text.text(f"🔍 步骤 3/6: 识别流量突降小区...")
            progress_bar.progress(40)
            
            df = pd.DataFrame(data)
            df['start_time'] = pd.to_datetime(df['start_time'])
            df['date'] = df['start_time'].dt.date
            
            # 按CGI分组分析
            drop_cells = []
            grouped = df.groupby('cgi')
            
            for cgi, cgi_data in grouped:
                min_required_days = window_size * 2 + 1
                if len(cgi_data) < min_required_days:
                    continue
                
                # 按日期聚合
                daily_data = cgi_data.groupby('date')['flwor_day'].mean().reset_index()
                daily_data = daily_data.sort_values('date')
                
                # 使用滑动窗口算法查找流量突降
                drop_date = self._find_traffic_drop_date(daily_data, drop_threshold, window_size)
                
                if drop_date is not None:
                    # 获取该CGI的cco_area_name（取第一个非空值）
                    cco_area_name = cgi_data['cco_area_name'].dropna().iloc[0] if not cgi_data['cco_area_name'].dropna().empty else ''
                    drop_cells.append({
                        'cgi': cgi,
                        'drop_date': drop_date,
                        'cco_area_name': cco_area_name
                    })
            
            if not drop_cells:
                progress_bar.empty()
                status_text.empty()
                st.warning("⚠️ 未发现流量突降小区")
                return pd.DataFrame()
            
            # 步骤4：获取工参信息
            status_text.text(f"🏢 步骤 4/6: 获取 {len(drop_cells)} 个突降小区的工参信息...")
            progress_bar.progress(60)
            
            drop_cgis = [cell['cgi'] for cell in drop_cells]
            
            # 查询工参信息，使用物理站名作为扇区标识
            engineering_query = '''
                SELECT 
                    cgi,
                    phy_name,
                    antenna_name,
                    celname,
                    zhishi,
                    pinduan
                FROM engineering_params
                WHERE cgi IN ({})
            '''.format(','.join(['?'] * len(drop_cgis)))
            
            engineering_data = self.db_manager.execute_query(engineering_query, drop_cgis)
            
            if not engineering_data:
                progress_bar.empty()
                status_text.empty()
                st.warning("⚠️ 未找到工参信息")
                return pd.DataFrame()
            
            # 步骤5：扇区级分析
            status_text.text("🔍 步骤 5/6: 进行扇区级分析...")
            progress_bar.progress(80)
            
            # 创建工参DataFrame
            eng_df = pd.DataFrame(engineering_data)
            
            # 合并突降小区和工参信息
            drop_df = pd.DataFrame(drop_cells)
            merged_df = drop_df.merge(eng_df, on='cgi', how='left')
            
            # 按物理站（扇区）分组分析
            sector_analysis = []
            
            for phy_name, sector_cells in merged_df.groupby('phy_name'):
                if pd.isna(phy_name) or phy_name == '':
                    continue
                
                # 获取该扇区下所有小区（包括非突降小区）
                all_sector_cells_query = '''
                    SELECT cgi, celname, antenna_name, zhishi, pinduan
                    FROM engineering_params
                    WHERE phy_name = ?
                '''
                all_sector_cells = self.db_manager.execute_query(all_sector_cells_query, (phy_name,))
                all_sector_df = pd.DataFrame(all_sector_cells)
                
                # 统计扇区信息
                total_cells_in_sector = len(all_sector_df)
                drop_cells_in_sector = len(sector_cells)
                drop_ratio = (drop_cells_in_sector / total_cells_in_sector * 100) if total_cells_in_sector > 0 else 0
                
                # 判断扇区级下降类型
                if drop_ratio == 100:
                    drop_type = "扇区整体下降"
                elif drop_ratio > 0:
                    drop_type = "单个/部分小区下降"
                else:
                    drop_type = "无突降"
                
                # 分析天线情况
                drop_antennas = sector_cells['antenna_name'].dropna().unique()
                all_antennas = all_sector_df['antenna_name'].dropna().unique()
                
                # 判断是否共天线
                if len(drop_antennas) == 1 and len(all_antennas) == 1:
                    antenna_status = "共天线"
                elif len(drop_antennas) == 1:
                    antenna_status = "突降小区共天线"
                else:
                    antenna_status = "不共天线"
                
                # 获取扇区名字（cco_area_name）
                sector_names = sector_cells['cco_area_name'].dropna().unique()
                sector_name = ', '.join(sector_names) if len(sector_names) > 0 else ''
                
                # 获取突降日期
                drop_dates = sector_cells['drop_date'].dropna().unique()
                drop_date_str = ', '.join([str(d) for d in drop_dates]) if len(drop_dates) > 0 else ''
                
                # 计算扇区级流量统计
                sector_traffic_before = 0
                sector_traffic_after = 0
                sector_traffic_drop = 0
                sector_drop_ratio = 0
                
                # 获取该扇区所有突降小区的流量数据
                sector_drop_cgis = sector_cells['cgi'].tolist()
                if sector_drop_cgis:
                    # 查询这些小区的流量数据
                    sector_traffic_query = '''
                        SELECT cgi, start_time, flwor_day
                        FROM performance_data
                        WHERE cgi IN ({})
                            AND start_time BETWEEN ? AND ?
                            AND data_type = 'capacity'
                        ORDER BY cgi, start_time
                    '''.format(','.join(['?'] * len(sector_drop_cgis)))
                    
                    sector_traffic_data = self.db_manager.execute_query(
                        sector_traffic_query, 
                        sector_drop_cgis + [start_str, end_str]
                    )
                    
                    if sector_traffic_data:
                        sector_traffic_df = pd.DataFrame(sector_traffic_data)
                        sector_traffic_df['start_time'] = pd.to_datetime(sector_traffic_df['start_time'])
                        sector_traffic_df['date'] = sector_traffic_df['start_time'].dt.date
                        
                        # 按CGI分组计算每个小区的突降前后流量
                        total_before = 0
                        total_after = 0
                        valid_cells = 0
                        
                        for cgi in sector_drop_cgis:
                            cgi_data = sector_traffic_df[sector_traffic_df['cgi'] == cgi]
                            if len(cgi_data) < window_size * 2 + 1:
                                continue
                                
                            daily_data = cgi_data.groupby('date')['flwor_day'].mean().reset_index()
                            daily_data = daily_data.sort_values('date')
                            
                            # 找到突降日期
                            drop_date = self._find_traffic_drop_date(daily_data, drop_threshold, window_size)
                            if drop_date is None:
                                continue
                            
                            # 计算突降前后流量
                            before_data = daily_data[daily_data['date'] < drop_date].tail(window_size)
                            after_data = daily_data[daily_data['date'] >= drop_date].head(window_size)
                            
                            if len(before_data) >= window_size and len(after_data) >= window_size:
                                avg_before = before_data['flwor_day'].mean()
                                avg_after = after_data['flwor_day'].mean()
                                
                                total_before += avg_before
                                total_after += avg_after
                                valid_cells += 1
                        
                        if valid_cells > 0:
                            sector_traffic_before = round(total_before, 2)
                            sector_traffic_after = round(total_after, 2)
                            sector_traffic_drop = round(total_before - total_after, 2)
                            sector_drop_ratio = round((total_before - total_after) / total_before * 100, 2) if total_before > 0 else 0
                
                # 收集扇区分析结果
                sector_analysis.append({
                    '物理站': phy_name,
                    '扇区名字': sector_name,
                    '扇区总小区数': total_cells_in_sector,
                    '突降小区数': drop_cells_in_sector,
                    '下降类型': drop_type,
                    '天线状态': antenna_status,
                    '制式': ', '.join(sector_cells['zhishi'].dropna().unique()),
                    '频段': ', '.join(sector_cells['pinduan'].dropna().unique()),
                    '突降前流量(GB)': sector_traffic_before,
                    '突降后流量(GB)': sector_traffic_after,
                    '突降流量(GB)': sector_traffic_drop,
                    '突降比例(%)': sector_drop_ratio,
                    '突降日期': drop_date_str,
                    '突降小区列表': ', '.join(sector_cells['cgi'].tolist())
                })
            
            # 步骤6：生成最终结果
            status_text.text("✅ 步骤 6/6: 生成分析结果...")
            progress_bar.progress(100)
            
            result_df = pd.DataFrame(sector_analysis)
            
            # 清空进度条
            progress_bar.empty()
            status_text.empty()
            
            return result_df
            
        except Exception as e:
            if 'progress_bar' in locals():
                progress_bar.empty()
            if 'status_text' in locals():
                status_text.empty()
            st.error(f"扇区级分析失败: {e}")
            self.logger.error(f"扇区级分析失败: {e}")
            return pd.DataFrame()
