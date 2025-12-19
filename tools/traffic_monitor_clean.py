#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流量监控分析工具 - 清洁版本
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

    def render(self):
        """渲染流量监控界面"""
        st.title("📈 流量监控分析工具")
        st.caption("网络流量监控和小区性能分析平台")

        # 功能导航
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 零低流量分析", 
            "📈 流量骤降分析", 
            "⚡ 高负荷小区查询",
            "🔍 小区查询"
        ])

        with tab1:
            self._render_zero_low_traffic_analysis()

        with tab2:
            self._render_traffic_drop_analysis()

        with tab3:
            self._render_high_load_analysis()

        with tab4:
            self._render_cell_query()

    def _render_zero_low_traffic_analysis(self):
        """渲染零低流量分析页面"""
        st.subheader("📊 零低流量分析")
        st.caption("分析零流量和低流量小区，支持4G/5G不同阈值")
        
        # 日期选择
        analysis_date = st.date_input(
            "选择分析日期",
            value=date.today(),
            key="zero_low_analysis_date"
        )
        
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
            try:
                # 生成零流量分析
                zero_df = self._generate_zero_traffic_analysis(analysis_date)
                st.success(f"✅ 零流量分析完成，共发现 {len(zero_df)} 个零流量小区")
                
                # 生成低流量分析
                low_df = self._generate_low_traffic_analysis(analysis_date, threshold_4g, threshold_5g)
                st.success(f"✅ 低流量分析完成，共发现 {len(low_df)} 个低流量小区")
                
                # 保存到session state
                st.session_state['zero_traffic_df'] = zero_df
                st.session_state['low_traffic_df'] = low_df
                st.session_state['analysis_date'] = analysis_date
                
            except Exception as e:
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
                self._export_zero_low_traffic_excel(zero_df, low_df, st.session_state['analysis_date'])

    def _render_traffic_drop_analysis(self):
        """渲染流量骤降分析页面"""
        st.subheader("📈 流量骤降分析")
        st.caption("分析流量骤降小区，支持自定义阈值和对比时间")
        
        # 参数设置
        col1, col2 = st.columns(2)
        with col1:
            analysis_date = st.date_input(
                "选择分析日期",
                value=date.today(),
                key="traffic_drop_analysis_date"
            )
        
        with col2:
            drop_threshold = st.slider(
                "骤降阈值 (%)",
                min_value=10,
                max_value=90,
                value=50,
                step=10,
                key="traffic_drop_threshold",
                help="流量下降超过此百分比将被识别为骤降"
            )
        
        # 对比时间设置
        st.markdown("#### 对比时间设置")
        col1, col2 = st.columns(2)
        with col1:
            compare_days = st.number_input(
                "对比天数",
                min_value=1,
                max_value=30,
                value=1,
                step=1,
                key="compare_days",
                help="与多少天前的数据进行对比"
            )
        with col2:
            compare_weeks = st.number_input(
                "对比周数",
                min_value=1,
                max_value=4,
                value=1,
                step=1,
                key="compare_weeks",
                help="与多少周前的数据进行对比"
            )
        
        if st.button("开始分析", key="analyze_traffic_drop"):
            try:
                df = self._generate_traffic_drop_analysis(analysis_date, drop_threshold, compare_days, compare_weeks)
                st.success(f"✅ 流量骤降分析完成，共发现 {len(df)} 个骤降小区")
                
                # 保存到session state
                st.session_state['traffic_drop_df'] = df
                st.session_state['traffic_drop_date'] = analysis_date
                
            except Exception as e:
                st.error(f"分析失败: {e}")
                self.logger.error(f"流量骤降分析失败: {e}")
        
        # 显示分析结果
        if 'traffic_drop_df' in st.session_state and not st.session_state['traffic_drop_df'].empty:
            df = st.session_state['traffic_drop_df']
            
            # 显示统计信息
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("总骤降小区数", len(df))
            with col2:
                st.metric("对比前1天骤降", len(df[df['流量骤降_对比前1天'] == '是']) if '流量骤降_对比前1天' in df.columns else 0)
            with col3:
                st.metric("对比前1周骤降", len(df[df['流量骤降_对比前1周'] == '是']) if '流量骤降_对比前1周' in df.columns else 0)
            
            # 显示数据表格
            st.dataframe(df, use_container_width=True)
            
            # 导出Excel文件
            if st.button("导出Excel文件", key="export_traffic_drop"):
                self._export_traffic_drop_excel(df, st.session_state['traffic_drop_date'])

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
                
                # 保存到session state
                st.session_state['high_load_summary'] = summary_df
                st.session_state['high_load_detail'] = detail_df
                st.session_state['high_load_query_start_date'] = start_date
                st.session_state['high_load_query_end_date'] = end_date
                
                st.success("✅ 高负荷小区查询完成")
                
            except Exception as e:
                st.error(f"查询失败: {e}")
                self.logger.error(f"高负荷小区查询失败: {e}")
        
        # 显示查询结果
        if 'high_load_summary' in st.session_state and not st.session_state['high_load_summary'].empty:
            summary_df = st.session_state['high_load_summary']
            detail_df = st.session_state['high_load_detail']
            
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
            
            # 导出Excel文件
            if st.button("导出Excel文件", key="export_high_load"):
                self._export_high_load_excel(summary_df, detail_df, st.session_state['high_load_query_start_date'], st.session_state['high_load_query_end_date'])

    def _render_cell_query(self):
        """渲染小区查询页面"""
        st.subheader("🔍 小区查询")
        st.caption("查询小区基本信息和性能数据")
        
        # 查询条件
        col1, col2 = st.columns(2)
        with col1:
            query_type = st.selectbox(
                "查询类型",
                ["按小区名称", "按CGI", "按网格ID", "按制式"],
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
                
                # 保存到session state
                st.session_state['cell_query_df'] = df
                st.session_state['cell_query_type'] = query_type
                st.session_state['cell_query_value'] = query_value
                
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
                self._export_cell_query_excel(df, st.session_state['cell_query_type'], st.session_state['cell_query_value'])

    def _generate_zero_traffic_analysis(self, analysis_date):
        """生成零流量分析"""
        try:
            date_str = analysis_date.strftime('%Y-%m-%d')
            
            query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day
                FROM cell_mapping c
                LEFT JOIN performance_data p ON c.cgi = p.cgi AND p.start_time = ? AND p.data_type = 'capacity'
                WHERE (p.flwor_day IS NULL OR p.flwor_day = 0)
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(query, [date_str]))
            
            if df.empty:
                return pd.DataFrame()
            
            # 处理当天流量为空的情况，视为0
            df['flwor_day'] = df['flwor_day'].fillna(0)
            
            # 添加问题类型标签
            df['问题类型'] = '零流量'
            
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
                'flwor_day': '日流量'
            }
            df = df.rename(columns=chinese_columns)
            
            # 确保制式列存在且为小写
            if '制式' in df.columns:
                df['制式'] = df['制式'].str.lower()
            
            return df
            
        except Exception as e:
            self.logger.error(f"生成零流量分析失败: {e}")
            return pd.DataFrame()

    def _generate_low_traffic_analysis(self, analysis_date, threshold_4g, threshold_5g):
        """生成低流量分析"""
        try:
            date_str = analysis_date.strftime('%Y-%m-%d')
            
            query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day
                FROM cell_mapping c
                LEFT JOIN performance_data p ON c.cgi = p.cgi AND p.start_time = ? AND p.data_type = 'capacity'
                WHERE p.flwor_day IS NOT NULL AND p.flwor_day > 0
                AND ((c.zhishi = '4g' AND p.flwor_day < ?) OR (c.zhishi = '5g' AND p.flwor_day < ?))
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(query, [date_str, threshold_4g, threshold_5g]))
            
            if df.empty:
                return pd.DataFrame()
            
            # 添加问题类型标签
            df['问题类型'] = '低流量'
            
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
                'flwor_day': '日流量'
            }
            df = df.rename(columns=chinese_columns)
            
            # 确保制式列存在且为小写
            if '制式' in df.columns:
                df['制式'] = df['制式'].str.lower()
            
            return df
            
        except Exception as e:
            self.logger.error(f"生成低流量分析失败: {e}")
            return pd.DataFrame()

    def _generate_traffic_drop_analysis(self, analysis_date, drop_threshold, compare_days=1, compare_weeks=1):
        """生成流量骤降分析"""
        try:
            date_str = analysis_date.strftime('%Y-%m-%d')
            prev_day = (analysis_date - timedelta(days=compare_days)).strftime('%Y-%m-%d')
            prev_week = (analysis_date - timedelta(days=compare_weeks*7)).strftime('%Y-%m-%d')
            
            query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day,
                    p_prev_day.flwor_day AS prev_day_flwor,
                    p_prev_week.flwor_day AS prev_week_flwor
                FROM cell_mapping c
                LEFT JOIN performance_data p ON c.cgi = p.cgi AND p.start_time = ? AND p.data_type = 'capacity'
                LEFT JOIN performance_data p_prev_day ON c.cgi = p_prev_day.cgi AND p_prev_day.start_time = ? AND p_prev_day.data_type = 'capacity'
                LEFT JOIN performance_data p_prev_week ON c.cgi = p_prev_week.cgi AND p_prev_week.start_time = ? AND p_prev_week.data_type = 'capacity'
                WHERE
                    ((p_prev_day.flwor_day IS NOT NULL AND (p.flwor_day IS NULL OR p.flwor_day < p_prev_day.flwor_day * ?)) OR
                    (p_prev_week.flwor_day IS NOT NULL AND (p.flwor_day IS NULL OR p.flwor_day < p_prev_week.flwor_day * ?)))
            '''
            
            threshold_ratio = (100 - drop_threshold) / 100
            df = pd.DataFrame(self.db_manager.execute_query(query, [date_str, prev_day, prev_week, threshold_ratio, threshold_ratio]))
            
            if df.empty:
                return pd.DataFrame()
            
            # 处理当天流量为空的情况，视为0
            df['flwor_day'] = df['flwor_day'].fillna(0)
            
            # 添加骤降标签
            df['流量骤降_对比前1天'] = df.apply(
                lambda row: '是' if row['prev_day_flwor'] is not None and row['flwor_day'] < row['prev_day_flwor'] * threshold_ratio else '否',
                axis=1
            )
            df['流量骤降_对比前1周'] = df.apply(
                lambda row: '是' if row['prev_week_flwor'] is not None and row['flwor_day'] < row['prev_week_flwor'] * threshold_ratio else '否',
                axis=1
            )
            
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
                'prev_day_flwor': f'前{compare_days}天流量',
                'prev_week_flwor': f'前{compare_weeks}周流量'
            }
            df = df.rename(columns=chinese_columns)
            
            return df
            
        except Exception as e:
            self.logger.error(f"生成流量骤降分析失败: {e}")
            return pd.DataFrame()

    def _generate_high_load_analysis(self, start_date, end_date):
        """生成高负荷小区分析"""
        try:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # 查询高负荷小区汇总
            summary_query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat,
                    COUNT(*) as 高负荷次数,
                    GROUP_CONCAT(p.start_time) as 高负荷日期
                FROM cell_mapping c
                JOIN performance_data p ON c.cgi = p.cgi AND p.start_time BETWEEN ? AND ? AND p.data_type = 'capacity'
                WHERE p.if_overcel = 't'
                GROUP BY c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                         c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                         c.lon, c.lat
                ORDER BY 高负荷次数 DESC
            '''
            
            summary_df = pd.DataFrame(self.db_manager.execute_query(summary_query, [start_str, end_str]))
            
            # 查询高负荷小区详细数据
            detail_query = '''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day, p.if_overcel,
                    p.ul_prb_mang, p.dl_prb_mang, p.pdcch_mang, p.rrc_average, p.rrc_max
                FROM cell_mapping c
                JOIN performance_data p ON c.cgi = p.cgi AND p.start_time BETWEEN ? AND ? AND p.data_type = 'capacity'
                WHERE p.if_overcel = 't'
                ORDER BY c.cgi, p.start_time
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
        """生成小区查询"""
        try:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # 根据查询类型构建查询条件
            if query_type == "按小区名称":
                where_condition = "c.celname LIKE ?"
                query_param = f"%{query_value}%"
            elif query_type == "按CGI":
                where_condition = "c.cgi LIKE ?"
                query_param = f"%{query_value}%"
            elif query_type == "按网格ID":
                where_condition = "c.grid_id LIKE ?"
                query_param = f"%{query_value}%"
            elif query_type == "按制式":
                where_condition = "c.zhishi = ?"
                query_param = query_value.lower()
            else:
                return pd.DataFrame()
            
            # 查询小区信息
            query = f'''
                SELECT
                    c.cgi, c.celname, c.grid_id, c.zhishi, c.pinduan,
                    c.grid_name, c.grid_pp, c.tt_mark, c.if_flag, c.if_cell, c.if_online,
                    c.lon, c.lat, p.start_time, p.flwor_day, p.if_overcel,
                    p.ul_prb_mang, p.dl_prb_mang, p.pdcch_mang, p.rrc_average, p.rrc_max
                FROM cell_mapping c
                LEFT JOIN performance_data p ON c.cgi = p.cgi AND p.start_time BETWEEN ? AND ? AND p.data_type = 'capacity'
                WHERE {where_condition}
                ORDER BY c.cgi, p.start_time
            '''
            
            df = pd.DataFrame(self.db_manager.execute_query(query, [start_str, end_str, query_param]))
            
            if df.empty:
                return pd.DataFrame()
            
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
            df = df.rename(columns=chinese_columns)
            
            return df
            
        except Exception as e:
            self.logger.error(f"生成小区查询失败: {e}")
            return pd.DataFrame()

    def _export_zero_low_traffic_excel(self, zero_df, low_df, analysis_date):
        """导出零低流量分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"零低流量分析报告_{analysis_date}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if not zero_df.empty:
                    zero_df.to_excel(writer, sheet_name='零流量小区', index=False)
                if not low_df.empty:
                    low_df.to_excel(writer, sheet_name='低流量小区', index=False)
            
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

    def _export_traffic_drop_excel(self, df, analysis_date):
        """导出流量骤降分析Excel文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"流量骤降分析报告_{analysis_date}_{timestamp}.xlsx"
            
            # 创建Excel文件
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="流量骤降分析", index=False)
            
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