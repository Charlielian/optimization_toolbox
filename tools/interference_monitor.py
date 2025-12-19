import io
import logging
import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

# -*- coding: utf-8 -*-
"""
优化百宝箱工具集 - 干扰监控工具
整合原有的app_streamlit.py功能
"""


class InterferenceMonitor:
    """干扰监控工具"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)

        # 工具配置
        self.required_columns = [
            'celname', 'cgi', 'grid_id', 'grid_name', 'grid_pp',
            'pinduan', 'tt_mark', 'zhishi', 'if_cell', 'if_flag'
        ]

    def render(self):
        """渲染干扰分析引擎界面"""
        st.title("📡 干扰分析引擎")
        st.caption("统一干扰数据管理与智能分析平台")

        # 功能导航
        tab1, tab2, tab3 = st.tabs(["🔍 数据查询", "📊 北向分析", "📈 报告导出"])

        with tab1:
            self._render_query_page()

        with tab2:
            self._render_north_analysis_page()

        with tab3:
            self._render_export_page()

    def _render_import_page(self):
        """渲染数据导入页面"""
        st.subheader("📥 数据导入")
        st.info("支持拖拽或点击选择文件。干扰文件名需包含 '_nr_cel' (5G) 或 '_lte_cel' (4G)。")

        # 导入小区映射表
        st.markdown("#### 导入小区映射表")
        mapping_file = st.file_uploader(
            "选择映射表（Excel/CSV，最大600MB）",
            type=['xlsx', 'xls', 'csv'],
            key="mapping"
        )

        if st.button(
            "导入映射表",
            type="primary",
            use_container_width=True,
            disabled=(
                mapping_file is None)):
            try:
                df = self._read_excel_or_csv(mapping_file)
                success_count = self._import_cell_mapping(df)
                st.success(f"映射表导入成功，共导入 {success_count} 条。")
            except Exception as e:
                st.error(f"映射表导入失败: {e}")

        st.divider()

        # 批量导入干扰文件
        st.markdown("#### 批量导入干扰文件")
        files = st.file_uploader(
            "选择一个或多个干扰文件（Excel/CSV，最大600MB）",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            key="rip_files"
        )

        if st.button(
            "开始批量导入干扰文件",
            type="primary",
            use_container_width=True,
            disabled=(
                not files)):
            self._batch_import_interference_files(files)

        st.divider()

        # 显示导入统计
        self._show_import_stats()

    def _render_query_page(self):
        """渲染数据查询页面"""
        st.subheader("🔍 查询干扰小区")

        col1, col2, col3 = st.columns(3)
        with col1:
            start_d = st.date_input(
                "开始日期",
                value=date.today() -
                timedelta(
                    days=7))
        with col2:
            end_d = st.date_input("结束日期", value=date.today())
        with col3:
            only_above = st.checkbox("仅看干扰值 > -107", value=False)

        c1, c2, c3 = st.columns(3)
        with c1:
            kw_cgi = st.text_input("CGI 包含", value="")
        with c2:
            kw_cel = st.text_input("小区名包含", value="")
        with c3:
            run = st.button("查询", type="primary", use_container_width=True)

        if run:
            self._execute_query(start_d, end_d, kw_cgi, kw_cel, only_above)

    def _render_north_analysis_page(self):
        """渲染北向分析页面"""
        st.subheader("📊 北向干扰文件分析")
        st.info("支持分析【北向当日干扰】文件夹内的4G/5G干扰文件，自动识别干扰类型并汇聚干扰值。")

        # 文件上传
        st.markdown("#### 上传北向干扰文件")
        st.warning(
            "⚠️ 重要提示：虽然界面可能显示200MB限制，但系统已配置支持最大600MB的文件上传。如果您的文件超过200MB，请直接尝试上传。")

        uploaded_files = st.file_uploader(
            "选择北向干扰文件（CSV格式，最大600MB）",
            type=['csv'],
            accept_multiple_files=True,
            key="north_files",
            help="支持最大600MB的CSV文件上传"
        )

        if uploaded_files:
            st.info(f"已选择 {len(uploaded_files)} 个文件")

            # 显示文件列表
            with st.expander("查看文件列表"):
                for i, file in enumerate(uploaded_files, 1):
                    st.write(f"{i}. {file.name}")

            # 处理按钮
            if st.button(
                "开始分析北向干扰文件",
                type="primary",
                    use_container_width=True):
                self._process_north_interference_files(uploaded_files)

    def _render_export_page(self):
        """渲染报告导出页面"""
        st.subheader("📈 导出报告（Excel）")

        col1, col2 = st.columns(2)
        with col1:
            start_d = st.date_input(
                "开始日期",
                value=date.today() -
                timedelta(
                    days=7),
                key="e_start")
        with col2:
            end_d = st.date_input("结束日期", value=date.today(), key="e_end")

        if st.button("生成并下载 Excel", type="primary", use_container_width=True):
            self._generate_excel_report(start_d, end_d)

    def _read_excel_or_csv(self, uploaded_file):
        """读取Excel或CSV文件"""
        name = uploaded_file.name.lower()
        if name.endswith(('.xlsx', '.xls')):
            return pd.read_excel(uploaded_file)
        elif name.endswith('.csv'):
            uploaded_file.seek(0)
            content = uploaded_file.read()
            for enc in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
                try:
                    return pd.read_csv(io.BytesIO(content), encoding=enc)
                except UnicodeDecodeError:
                    continue
            raise Exception("无法解析CSV文件，请检查编码")
        else:
            raise Exception(f"不支持的文件类型: {name}")

    def _import_cell_mapping(self, df: pd.DataFrame) -> int:
        """导入小区映射表"""
        missing = [c for c in self.required_columns if c not in df.columns]
        if missing:
            raise Exception(f"导入失败：文件缺少必要的列: {', '.join(missing)}")

        df = df.fillna('')

        # 准备数据
        records = []
        for _, r in df.iterrows():
            records.append(
                (r['celname'],
                 r['cgi'],
                    r['grid_id'],
                    r['grid_name'],
                    r['grid_pp'],
                    r['pinduan'],
                    r['tt_mark'],
                    r['zhishi'],
                    r['if_cell'],
                    r['if_flag']))

        # 清空现有数据并插入新数据
        self.db_manager.execute_update("DELETE FROM cell_mapping")

        insert_sql = """
        INSERT INTO cell_mapping (
            celname, cgi, grid_id, grid_name, grid_pp,
            pinduan, tt_mark, zhishi, if_cell, if_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        success = self.db_manager.execute_many(insert_sql, records)
        if not success:
            raise Exception("数据库插入失败")

        # 记录导入日志
        self.db_manager.log_import(
            "interference_monitor", "cell_mapping", "mapping",
            len(records), len(records), 0, "success"
        )

        return len(records)

    def _batch_import_interference_files(self, files):
        """批量导入干扰文件"""
        total_ok, total_err, total_files = 0, 0, 0

        for f in files:
            total_files += 1
            try:
                df = self._read_excel_or_csv(f)
                ok_rows, err_rows = self._import_interference_data(df, f.name)
                total_ok += ok_rows
                total_err += err_rows
                st.success(f"{f.name} 导入成功：{ok_rows} 条；跳过错误行：{err_rows} 条")
            except Exception as e:
                st.error(f"{f.name} 导入失败：{e}")

        st.info(f"本次导入完成。文件数：{total_files}，成功记录：{total_ok}，错误行：{total_err}")

    def _import_interference_data(
            self,
            df: pd.DataFrame,
            file_name: str) -> tuple:
        """导入干扰数据"""
        is_5g = '_nr_cel' in file_name.lower()
        is_4g = '_lte_cel' in file_name.lower()

        if not (is_5g or is_4g):
            raise Exception("无法识别文件类型，文件名应包含 '_nr_cel'(5G) 或 '_lte_cel'(4G)")

        required = [
            '数据时间',
            'CGI',
            '小区名',
            '全频段均值'] if is_5g else [
            '数据时间',
            'CGI',
            '小区名',
            '平均干扰电平']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise Exception(f"文件缺少必要的列: {', '.join(missing)}")

        data_list, error_rows = [], 0

        for idx, row in df.iterrows():
            try:
                # 处理时间字段 - 支持多种日期格式
                dstr = str(row['数据时间']).replace('\t', '').strip()
                # 尝试多种日期格式
                date_formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d",
                    "%Y%m%d",
                    "%Y-%m-%d %H:%M",
                    "%Y/%m/%d %H:%M"
                ]
                d = None
                for fmt in date_formats:
                    try:
                        d = datetime.strptime(dstr, fmt)
                        break
                    except ValueError:
                        continue
                
                if d is None:
                    self.logger.warning(f"文件 {file_name} 第 {idx+1} 行: 无法解析日期格式 '{dstr}'，跳过此行")
                    error_rows += 1
                    continue

                date_str = d.strftime("%Y%m%d")
                cgi = str(row['CGI']).strip()
                celname = str(row['小区名']).strip()

                if is_5g:
                    zhishi = '5g'
                    rip_str = str(row['全频段均值']).strip()
                    pinduan = '700M' if 'CBN' in celname else '2.6G'
                else:
                    zhishi = '4g'
                    rip_str = str(row['平均干扰电平']).strip()
                    pinduan = 'lte'

                try:
                    if_rip = '1' if float(rip_str) > -107 else '0'
                except (ValueError, TypeError):
                    if_rip = 'n/a'

                data_list.append(
                    (date_str, cgi, celname, zhishi, pinduan, rip_str, if_rip))
            except Exception as e:
                error_rows += 1
                self.logger.warning(f"文件 {file_name} 第 {idx+1} 行处理失败: {str(e)}")
                if idx < 5:  # 只记录前5行的详细错误信息，避免日志过多
                    import traceback
                    self.logger.debug(f"错误详情: {traceback.format_exc()}")

        if not data_list:
            return 0, error_rows

        insert_sql = """
        INSERT OR REPLACE INTO interference_data (date_str, cgi, celname, zhishi, pinduan, rip_str, if_rip)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        success = self.db_manager.execute_many(insert_sql, data_list)
        if not success:
            raise Exception("批量插入数据库失败")

        # 记录导入日志
        self.db_manager.log_import(
            "interference_monitor", file_name, "interference",
            len(data_list), len(data_list), error_rows, "success"
        )

        return len(data_list), error_rows

    def _execute_query(self, start_d, end_d, kw_cgi, kw_cel, only_above):
        """执行查询"""
        try:
            s = self._to_yyyymmdd(start_d)
            e = self._to_yyyymmdd(end_d)

            if s > e:
                st.error("开始日期不能晚于结束日期")
                return

            df = self._query_interference_range(
                s, e, kw_cgi, kw_cel, only_above)

            if df.empty:
                st.warning("没有查询到数据")
                return

            out = self._summarize_interference(df, s, e)

            if out.empty:
                st.warning("汇总后无数据")
                return

            st.success(f"查询到 {len(df)} 条原始记录；汇总行数：{len(out)}")

            # 显示数据预览
            st.dataframe(out, use_container_width=True)

            # 下载功能
            csv = out.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "下载汇总CSV",
                data=csv,
                file_name=f"干扰小区汇总_{s}_{e}.csv",
                mime="text/csv"
            )

        except Exception as ex:
            st.error(f"查询失败：{ex}")

    def _query_interference_range(
            self,
            start_yyyymmdd: str,
            end_yyyymmdd: str,
            cgi_kw: str = "",
            cel_kw: str = "",
            only_above_threshold=False):
        """查询干扰数据范围"""
        base_sql = """
        SELECT r.date_str, r.cgi, r.celname, r.zhishi, r.pinduan, r.rip_str, r.if_rip
        FROM interference_data r
        WHERE r.date_str BETWEEN ? AND ?
        """
        params = [start_yyyymmdd, end_yyyymmdd]

        if cgi_kw:
            base_sql += " AND r.cgi LIKE ?"
            params.append(f"%{cgi_kw}%")
        if cel_kw:
            base_sql += " AND r.celname LIKE ?"
            params.append(f"%{cel_kw}%")
        if only_above_threshold:
            base_sql += " AND CAST(r.rip_str AS REAL) > -107"

        base_sql += " ORDER BY r.cgi, r.date_str"

        return self.db_manager.get_dataframe(base_sql, tuple(params))

    def _summarize_interference(
            self,
            df_rip: pd.DataFrame,
            start_yyyymmdd: str,
            end_yyyymmdd: str):
        """汇总干扰数据 - 以映射表为主，保留所有映射行"""
        if df_rip.empty:
            # 即使没有干扰数据，也要返回映射表数据
            return self._get_empty_result_with_mapping(start_yyyymmdd, end_yyyymmdd)

        # 生成完整的日期范围
        start_date = datetime.strptime(start_yyyymmdd, '%Y%m%d')
        end_date = datetime.strptime(end_yyyymmdd, '%Y%m%d')
        date_range = []
        current = start_date
        while current <= end_date:
            date_range.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)

        df = df_rip.copy()

        def gt_minus107(x):
            try:
                return float(x) > -107
            except Exception:
                return False

        # 统计干扰值大于-107的天数（按CGI统计）
        df['gt'] = df['rip_str'].apply(gt_minus107)
        count_df = df.groupby('cgi')['gt'].sum().reset_index().rename(
            columns={'gt': '干扰值> -107天数'})

        # 重要：先获取所有映射表数据（对于有干扰数据的CGI）
        cgi_list = df['cgi'].unique().tolist()
        cells = self._get_cells_by_cgi_list(cgi_list)
        
        if cells.empty:
            # 如果没有映射表数据，使用原来的逻辑，但仍需要包含网格相关列
            pivot = df.pivot_table(
                index=['cgi', 'celname', 'zhishi', 'pinduan'],
                columns='date_str',
                values='rip_str',
                aggfunc='first',
                fill_value='n/a(无数据)'
            )
            pivot = pivot.reset_index()
            
            # 确保所有日期列都存在
            for date_str in date_range:
                if date_str not in pivot.columns:
                    pivot[date_str] = 'n/a(无数据)'
            
            # 合并统计信息
            out = pd.merge(pivot, count_df, on='cgi', how='left')
            
            # 添加网格相关列（即使没有映射表数据，也要包含这些列，值为空）
            out['grid_id'] = ''
            out['grid_name'] = ''
            out['grid_pp'] = ''
            out['tt_mark'] = ''
            out['if_cell'] = ''
            out['if_flag'] = ''
            
            # 按日期排序列
            date_cols = sorted([c for c in out.columns if c.isdigit() and len(c) == 8])
            base_cols = ['cgi', 'celname', 'zhishi', 'pinduan', 'grid_id', 'grid_name', 'grid_pp', 
                         'tt_mark', 'if_cell', 'if_flag', '干扰值> -107天数']
            out = out[base_cols + date_cols]
            
            # 应用中文列名映射
            out = self._apply_chinese_column_mapping(out)
            return out

        # 优化：使用向量化操作，避免循环
        # 先创建干扰数据的pivot table（只按CGI，不按其他字段分组）
        pivot = df.pivot_table(
            index='cgi',
            columns='date_str',
            values='rip_str',
            aggfunc='first',
            fill_value='n/a(无数据)'
        )
        pivot = pivot.reset_index()
        
        # 确保所有日期列都存在
        for date_str in date_range:
            if date_str not in pivot.columns:
                pivot[date_str] = 'n/a(无数据)'
        
        # 合并统计信息到pivot
        pivot_with_count = pd.merge(pivot, count_df, on='cgi', how='left')
        pivot_with_count['干扰值> -107天数'] = pivot_with_count['干扰值> -107天数'].fillna(0)
        
        # 关键：以映射表为主，使用left merge保留所有映射行
        # 这样同一个CGI的多行映射都会保留
        result_df = pd.merge(
            cells,
            pivot_with_count,
            on='cgi',
            how='left',
            suffixes=('', '_dup')
        )
        
        # 对于没有干扰数据的日期列，填充为 'n/a(无数据)'
        date_cols = [col for col in result_df.columns if col.isdigit() and len(col) == 8]
        for col in date_cols:
            result_df[col] = result_df[col].fillna('n/a(无数据)')
        
        # 如果干扰值> -107天数列为空，填充为0
        if '干扰值> -107天数' in result_df.columns:
            result_df['干扰值> -107天数'] = result_df['干扰值> -107天数'].fillna(0)
        
        # 按日期排序列
        date_cols = sorted([c for c in result_df.columns if c.isdigit() and len(c) == 8])
        base_cols = ['cgi', 'celname', 'zhishi', 'pinduan', 'grid_id', 'grid_name', 'grid_pp', 
                     'tt_mark', 'if_cell', 'if_flag', '干扰值> -107天数']
        # 只保留存在的列
        existing_base_cols = [col for col in base_cols if col in result_df.columns]
        result_df = result_df[existing_base_cols + date_cols]
        
        # 应用中文列名映射
        result_df = self._apply_chinese_column_mapping(result_df)
        return result_df
    
    def _get_empty_result_with_mapping(self, start_yyyymmdd: str, end_yyyymmdd: str):
        """当没有干扰数据时，返回映射表数据（如果有的话）"""
        # 生成完整的日期范围
        start_date = datetime.strptime(start_yyyymmdd, '%Y%m%d')
        end_date = datetime.strptime(end_yyyymmdd, '%Y%m%d')
        date_range = []
        current = start_date
        while current <= end_date:
            date_range.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        
        # 获取所有映射表数据（这里可能需要根据实际情况调整查询条件）
        cells = self._get_cells()
        
        if cells.empty:
            return pd.DataFrame()
        
        # 为每个映射行创建一行，所有日期列填充为 'n/a(无数据)'
        result_rows = []
        for idx, cell_row in cells.iterrows():
            row = {
                'cgi': cell_row.get('cgi', ''),
                'celname': cell_row.get('celname', ''),
                'zhishi': cell_row.get('zhishi', ''),
                'pinduan': cell_row.get('pinduan', ''),
                'grid_id': cell_row.get('grid_id', ''),
                'grid_name': cell_row.get('grid_name', ''),
                'grid_pp': cell_row.get('grid_pp', ''),
                'tt_mark': cell_row.get('tt_mark', ''),
                'if_cell': cell_row.get('if_cell', ''),
                'if_flag': cell_row.get('if_flag', ''),
                '干扰值> -107天数': 0
            }
            
            for date_str in date_range:
                row[date_str] = 'n/a(无数据)'
            
            result_rows.append(row)
        
        result_df = pd.DataFrame(result_rows)
        
        # 按日期排序列
        date_cols = sorted([c for c in result_df.columns if c.isdigit() and len(c) == 8])
        base_cols = ['cgi', 'celname', 'zhishi', 'pinduan', 'grid_id', 'grid_name', 'grid_pp', 
                     'tt_mark', 'if_cell', 'if_flag', '干扰值> -107天数']
        existing_base_cols = [col for col in base_cols if col in result_df.columns]
        result_df = result_df[existing_base_cols + date_cols]
        
        result_df = self._apply_chinese_column_mapping(result_df)
        return result_df

    def _get_cells(self):
        """获取小区映射数据"""
        return self.db_manager.get_dataframe("""
            SELECT DISTINCT grid_id, grid_name, grid_pp, cgi, celname, zhishi, pinduan, tt_mark, if_cell, if_flag
            FROM cell_mapping
        """)
    
    def _get_cells_by_cgi_list(self, cgi_list):
        """根据CGI列表获取小区映射数据"""
        if not cgi_list:
            return pd.DataFrame()
        
        placeholders = ','.join(['?'] * len(cgi_list))
        # 移除DISTINCT，确保同一个CGI的多行映射都能返回
        # 因为cell_mapping表允许同一个CGI有多个不同的网格映射（通过UNIQUE (cgi, grid_id)约束）
        sql = f"""
            SELECT grid_id, grid_name, grid_pp, cgi, celname, zhishi, pinduan, tt_mark, if_cell, if_flag
            FROM cell_mapping
            WHERE cgi IN ({placeholders})
            ORDER BY cgi, grid_id
        """
        return self.db_manager.get_dataframe(sql, tuple(cgi_list))

    def _apply_chinese_column_mapping(self, df):
        """应用中文列名映射"""
        column_mapping = {
            'cgi': 'CGI',
            'celname': '小区名',
            'zhishi': '制式',
            'pinduan': '频段',
            'grid_id': '网格ID',
            'grid_name': '网格中文',
            'grid_pp': '网格标签',
            'tt_mark': '备注',
            'if_cell': '是否映射小区',
            'if_flag': '是否缓冲区',
            '干扰值> -107天数': '干扰值> -107天数'
        }

        # 重命名列
        df = df.rename(columns=column_mapping)

        # 重新排列列的顺序，将中文列名放在前面
        chinese_cols = [
            'CGI',
            '小区名',
            '制式',
            '频段',
            '网格ID',
            '网格中文',
            '网格标签',
            '备注',
            '是否映射小区',
            '是否缓冲区',
            '干扰值> -107天数']
        date_cols = [col for col in df.columns if col.isdigit()
                     and len(col) == 8]

        # 只保留存在的列
        existing_chinese_cols = [
            col for col in chinese_cols if col in df.columns]
        final_cols = existing_chinese_cols + date_cols

        return df[final_cols]

    def _to_yyyymmdd(self, d: date):
        """转换日期格式"""
        return d.strftime('%Y%m%d')

    def _convert_to_numeric(self, value):
        """将干扰值转换为数字"""
        if pd.isna(value) or value == 'n/a(无数据)' or value == '':
            return None

        try:
            # 尝试转换为浮点数
            return float(value)
        except (ValueError, TypeError):
            # 如果转换失败，返回None
            return None

    def _show_import_stats(self):
        """显示导入统计"""
        try:
            stats = self.db_manager.execute_query("""
                SELECT MIN(date_str) AS min_d, MAX(date_str) AS max_d, COUNT(*) AS cnt
                FROM interference_data
            """)

            if stats and stats[0]['cnt'] > 0:
                st.success(
                    f"已导入干扰数据：{
                        stats[0]['min_d']} 至 {
                        stats[0]['max_d']}，共 {
                        stats[0]['cnt']} 条")
            else:
                st.warning("数据库中尚无干扰数据")
        except Exception as e:
            st.error(f"获取统计信息失败: {e}")

    def _process_north_interference_files(self, uploaded_files):
        """处理北向干扰文件"""
        st.markdown("#### 北向干扰文件处理")
        st.info("📁 请上传北向干扰数据文件进行分析处理")

        # 文件上传
        uploaded_files = st.file_uploader(
            "选择北向干扰文件",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            help="支持Excel和CSV格式的北向干扰数据文件"
        )

        if uploaded_files:
            st.success(f"已选择 {len(uploaded_files)} 个文件")

            # 处理选项
            col1, col2 = st.columns(2)
            with col1:
                process_option = st.selectbox(
                    "处理方式",
                    ["数据预览", "数据导入", "数据分析"],
                    help="选择对上传文件的操作方式"
                )

            with col2:
                if st.button("开始处理", type="primary"):
                    self._handle_north_interference_processing(
                        uploaded_files, process_option)

    def _handle_north_interference_processing(self, files, process_option):
        """处理北向干扰文件"""
        try:
            if process_option == "数据预览":
                self._preview_north_interference_data(files)
            elif process_option == "数据导入":
                self._import_north_interference_data(files)
            elif process_option == "数据分析":
                self._analyze_north_interference_data(files)
        except Exception as e:
            st.error(f"处理失败: {e}")

    def _preview_north_interference_data(self, files):
        """预览北向干扰数据"""
        st.markdown("##### 📊 数据预览")

        for i, file in enumerate(files):
            st.markdown(f"**文件 {i + 1}: {file.name}**")

            try:
                if file.name.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    df = pd.read_csv(file)

                st.write(f"行数: {len(df)}, 列数: {len(df.columns)}")
                st.write("列名:", list(df.columns))
                st.dataframe(df.head(10), use_container_width=True)

            except Exception as e:
                st.error(f"文件 {file.name} 读取失败: {e}")

    def _import_north_interference_data(self, files):
        """导入北向干扰数据"""
        st.markdown("##### 📥 数据导入")

        total_imported = 0
        for file in files:
            try:
                if file.name.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    df = pd.read_csv(file)

                # 这里需要根据实际的北向干扰数据格式进行字段映射
                # 暂时显示数据统计
                st.success(f"文件 {file.name}: {len(df)} 条记录")
                total_imported += len(df)

            except Exception as e:
                st.error(f"文件 {file.name} 导入失败: {e}")

        st.success(f"总计导入 {total_imported} 条北向干扰数据")

    def _analyze_north_interference_data(self, files):
        """分析北向干扰数据"""
        st.markdown("##### 📈 数据分析")

        all_data = []
        for file in files:
            try:
                if file.name.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    df = pd.read_csv(file)

                all_data.append(df)

            except Exception as e:
                st.error(f"文件 {file.name} 读取失败: {e}")

        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            st.write(f"合并数据: {len(combined_df)} 条记录")

            # 基本统计
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("总记录数", len(combined_df))
            with col2:
                st.metric("文件数量", len(files))
            with col3:
                st.metric("平均每文件", f"{len(combined_df) // len(files)} 条")

            # 数据概览
            st.dataframe(combined_df.describe(), use_container_width=True)

    def _generate_excel_report(self, start_d, end_d):
        """生成Excel报告"""
        try:
            s = self._to_yyyymmdd(start_d)
            e = self._to_yyyymmdd(end_d)

            if s > e:
                st.error("开始日期不能晚于结束日期")
                return

            with st.spinner('正在生成 Excel 文件...'):
                df = self._query_interference_range(s, e)
                if df.empty:
                    st.warning("所选日期范围内无数据")
                else:
                    st.info(f"查询到 {len(df)} 条原始记录")
                    out = self._summarize_interference(df, s, e)
                    if out.empty:
                        st.warning("汇总后无数据")
                    else:
                        st.info(f"汇总后 {len(out)} 行数据，{len(out.columns)} 列")

                        # 生成Excel文件
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                            # 处理数据：将干扰值转换为数字
                            out_processed = out.copy()
                            date_cols = [
                                c for c in out.columns if c.isdigit() and len(c) == 8]

                            # 转换日期列的干扰值为数字
                            for col in date_cols:
                                out_processed[col] = out_processed[col].apply(
                                    lambda x: self._convert_to_numeric(x))

                            out_processed.to_excel(
                                writer, index=False, sheet_name='干扰监控数据')

                            # 应用条件格式
                            ws = writer.sheets['干扰监控数据']
                            date_col_indices = [
                                i for i, c in enumerate(
                                    out_processed.columns, start=1) if c.isdigit()]

                            if date_col_indices:
                                # 创建格式：黄色背景，红色字体
                                fmt = writer.book.add_format({
                                    'bg_color': '#FFFF00',  # 黄色背景
                                    'font_color': '#FF0000'  # 红色字体
                                })

                                # 对每个日期列应用条件格式
                                for col_idx in date_col_indices:
                                    # 应用条件格式：干扰值大于-107时显示黄色背景和红色字体
                                    ws.conditional_format(1,
                                                          col_idx - 1,
                                                          len(out_processed),
                                                          col_idx - 1,
                                                          {'type': 'cell',
                                                              'criteria': 'greater than',
                                                              'value': -107,
                                                              'format': fmt})

                        buffer.seek(0)
                        st.download_button(
                            "下载 Excel",
                            data=buffer.getvalue(),
                            file_name=f"干扰监控_{s}_{e}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True)
        except Exception as ex:
            st.error(f"导出失败：{ex}")
