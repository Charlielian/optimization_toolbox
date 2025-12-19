import json
import logging
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

# -*- coding: utf-8 -*-
"""
优化百宝箱工具集 - 系统管理工具
提供系统配置、数据管理、日志查看等功能
"""


class SystemManager:
    """系统管理工具"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)

    def render(self):
        """渲染系统管理界面"""
        st.title("⚙️ 系统管理")
        st.caption("系统配置、数据管理和维护工具")

        # 功能导航
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 系统状态", "⚙️ 系统配置", "💾 数据管理", "📋 日志查看", "🔧 系统维护"
        ])

        with tab1:
            self._render_system_status()

        with tab2:
            self._render_system_config()

        with tab3:
            self._render_data_management()

        with tab4:
            self._render_log_viewer()

        with tab5:
            self._render_system_maintenance()

    def _render_system_status(self):
        """渲染系统状态页面"""
        st.subheader("📊 系统状态")

        try:
            # 获取系统统计信息
            stats = self.db_manager.get_database_stats()

            # 显示关键指标
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "数据库大小",
                    f"{stats.get('db_size_mb', 0):.1f} MB",
                    help="数据库文件大小"
                )

            with col2:
                st.metric(
                    "小区映射",
                    f"{stats.get('cell_mapping_count', 0):,}",
                    help="小区映射记录数"
                )

            with col3:
                st.metric(
                    "干扰数据",
                    f"{stats.get('interference_data_count', 0):,}",
                    help="干扰监控数据记录数"
                )

            with col4:
                st.metric("容量数据", f"{self.db_manager.execute_query(
                    'SELECT COUNT(*) as count FROM performance_data WHERE data_type = \'capacity\'')[0]['count']:,}", help="容量监控数据记录数")

            st.divider()

            # 详细统计表格
            st.markdown("#### 详细统计信息")

            table_stats = {
                '表名': [
                    '小区映射表', '工参表', '干扰数据表', '容量数据表',
                    '流量数据表', '工具表', '配置表', '日志表'
                ],
                '记录数': [
                    stats.get('cell_mapping_count', 0),
                    stats.get('engineering_params_count', 0),
                    stats.get('interference_data_count', 0),
                    self.db_manager.execute_query("SELECT COUNT(*) as count FROM performance_data WHERE data_type = 'capacity'")[0]['count'],
                    self.db_manager.execute_query("SELECT COUNT(*) as count FROM performance_data WHERE data_type = 'traffic'")[0]['count'],
                    stats.get('tools_count', 0),
                    stats.get('system_config_count', 0),
                    stats.get('import_logs_count', 0)
                ]
            }

            df_stats = pd.DataFrame(table_stats)
            st.dataframe(df_stats, use_container_width=True, hide_index=True)

            # 工具状态
            st.markdown("#### 工具状态")
            tools_list = self.db_manager.get_tools_list()

            if tools_list:
                tools_df = pd.DataFrame(tools_list)
                st.dataframe(
                    tools_df[['tool_name', 'tool_type', 'version', 'status', 'updated_at']],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("暂无已注册的工具")

        except Exception as e:
            st.error(f"获取系统状态失败: {e}")

    def _render_system_config(self):
        """渲染系统配置页面"""
        st.subheader("⚙️ 系统配置")

        # 配置项管理
        st.markdown("#### 系统配置项")

        # 获取当前配置
        configs = [
            ("interference_threshold", "干扰阈值", "-107", "干扰值阈值设置"),
            ("traffic_threshold", "流量阈值", "0.1", "流量阈值设置"),
            ("auto_backup", "自动备份", "false", "是否启用自动备份"),
            ("log_retention", "日志保留天数", "30", "日志文件保留天数"),
            ("max_upload_size", "最大上传大小(MB)", "600", "文件上传大小限制"),
            ("backup_interval", "备份间隔(小时)", "24", "自动备份间隔时间")
        ]

        for config_key, config_name, default_value, description in configs:
            current_value = self.db_manager.get_system_config(
                config_key) or default_value

            col1, col2 = st.columns([2, 1])

            with col1:
                new_value = st.text_input(
                    f"{config_name} ({config_key})",
                    value=current_value,
                    help=description,
                    key=f"config_{config_key}"
                )

            with col2:
                if st.button(f"更新", key=f"update_{config_key}"):
                    if self.db_manager.set_system_config(
                            config_key, new_value, description=description):
                        st.success(f"{config_name} 更新成功")
                        st.rerun()
                    else:
                        st.error(f"{config_name} 更新失败")

        st.divider()

        # 批量配置操作
        st.markdown("#### 批量配置操作")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🔄 重置为默认值", use_container_width=True):
                self._reset_to_default_config()

        with col2:
            if st.button("💾 导出配置", use_container_width=True):
                self._export_config()

        with col3:
            if st.button("📥 导入配置", use_container_width=True):
                self._import_config()

    def _render_data_management(self):
        """渲染数据管理页面"""
        st.subheader("💾 数据管理")

        # 数据备份
        st.markdown("#### 数据备份")

        col1, col2 = st.columns(2)

        with col1:
            backup_name = st.text_input(
                "备份名称", value=f"backup_{
                    datetime.now().strftime('%Y%m%d_%H%M%S')}")

        with col2:
            if st.button("💾 创建备份", use_container_width=True):
                backup_path = f"{backup_name}.db"
                if self.db_manager.backup_database(backup_path):
                    st.success(f"数据库备份成功: {backup_path}")
                else:
                    st.error("数据库备份失败")

        st.divider()

        # 数据清理
        st.markdown("#### 数据清理")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🗑️ 清理旧日志", use_container_width=True):
                self._cleanup_old_logs()

        with col2:
            if st.button("🗑️ 清理临时数据", use_container_width=True):
                self._cleanup_temp_data()

        with col3:
            if st.button("🗑️ 清理重复数据", use_container_width=True):
                self._cleanup_duplicate_data()
        st.divider()

        # 按日期删除数据
        st.markdown("#### 按日期删除数据（干扰数据与性能数据）")
        st.info("根据日期范围批量删除干扰数据和性能数据，操作不可恢复，请谨慎使用。")

        col_type, col_mode = st.columns(2)
        with col_type:
            delete_data_type = st.selectbox(
                "选择数据类型",
                ["干扰数据", "性能数据（容量）", "干扰+性能（容量）"],
                key="delete_data_type"
            )
        with col_mode:
            delete_mode = st.radio(
                "删除范围",
                ["单日", "日期区间"],
                horizontal=True,
                key="delete_date_mode"
            )

        if delete_mode == "单日":
            target_date = st.date_input("选择日期", key="delete_single_date")
            start_date = end_date = target_date
        else:
            col_sd, col_ed = st.columns(2)
            with col_sd:
                start_date = st.date_input("开始日期", key="delete_range_start")
            with col_ed:
                end_date = st.date_input("结束日期", key="delete_range_end")

        st.warning(
            "⚠️ 将删除所选日期范围内的全部相关记录，删除后不可恢复，建议先备份数据库。"
        )
        confirm_text = st.text_input(
            "请输入 DELETE 以确认删除（区分大小写）",
            key="delete_data_confirm"
        )

        if st.button(
            "🗑️ 按日期删除数据",
            type="secondary",
            use_container_width=True,
            disabled=(confirm_text != "DELETE")
        ):
            self._delete_data_by_date_range(delete_data_type, start_date, end_date)

        # 数据统计
        st.markdown("#### 数据统计")

        if st.button("📊 生成数据统计报告", use_container_width=True):
            self._generate_data_statistics()

    def _render_log_viewer(self):
        """渲染日志查看页面"""
        st.subheader("📋 日志查看")

        # 日志筛选
        col1, col2, col3 = st.columns(3)

        with col1:
            tool_filter = st.selectbox(
                "工具筛选",
                options=["全部"] + [tool['tool_name'] for tool in self.db_manager.get_tools_list()],
                key="log_tool_filter"
            )

        with col2:
            status_filter = st.selectbox(
                "状态筛选",
                options=["全部", "success", "error", "warning"],
                key="log_status_filter"
            )

        with col3:
            limit = st.number_input(
                "显示条数",
                value=100,
                min_value=10,
                max_value=1000,
                step=10)

        # 查询日志
        if st.button("🔍 查询日志", type="primary"):
            self._display_logs(tool_filter, status_filter, limit)

        st.divider()

        # 日志操作
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📥 导出日志", use_container_width=True):
                self._export_logs()

        with col2:
            if st.button("🗑️ 清理日志", use_container_width=True):
                self._cleanup_logs()

        with col3:
            if st.button("🔄 刷新日志", use_container_width=True):
                st.rerun()

    def _render_system_maintenance(self):
        """渲染系统维护页面"""
        st.subheader("🔧 系统维护")

        # 数据库维护
        st.markdown("#### 数据库维护")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("🔧 优化数据库", use_container_width=True):
                self._optimize_database()

        with col2:
            if st.button("🔍 检查完整性", use_container_width=True):
                self._check_database_integrity()

        with col3:
            if st.button("📊 重建索引", use_container_width=True):
                self._rebuild_indexes()
        
        with col4:
            if st.button("🔎 检查网格名称映射", use_container_width=True):
                self._check_grid_name_mapping()

        st.divider()
        
        # 数据质量检查
        st.markdown("#### 数据质量检查")
        
        if st.button("🔍 检查网格名称错误映射（地市名称）", type="primary"):
            self._check_grid_name_city_mapping()
        
        st.divider()

        # 系统信息
        st.markdown("#### 系统信息")

        try:
            # 获取系统信息
            system_info = self._get_system_info()

            col1, col2 = st.columns(2)

            with col1:
                st.json(system_info)

            with col2:
                if st.button("📋 导出系统信息", use_container_width=True):
                    self._export_system_info(system_info)

        except Exception as e:
            st.error(f"获取系统信息失败: {e}")

        st.divider()

        # 危险操作
        st.markdown("#### ⚠️ 危险操作")

        with st.expander("重置系统", expanded=False):
            st.warning("⚠️ 此操作将清空所有数据，请谨慎操作！")

            confirm_text = st.text_input("请输入 'RESET' 确认重置")

            if st.button(
                "🗑️ 重置系统", type="secondary", disabled=(
                    confirm_text != "RESET")):
                self._reset_system()

    def _reset_to_default_config(self):
        """重置为默认配置"""
        default_configs = {
            "interference_threshold": "-107",
            "traffic_threshold": "0.1",
            "auto_backup": "false",
            "log_retention": "30",
            "max_upload_size": "600",
            "backup_interval": "24"
        }

        success_count = 0
        for key, value in default_configs.items():
            if self.db_manager.set_system_config(key, value):
                success_count += 1

        if success_count == len(default_configs):
            st.success("配置已重置为默认值")
        else:
            st.error(f"部分配置重置失败，成功 {success_count}/{len(default_configs)}")

    def _export_config(self):
        """导出配置"""
        try:
            configs = self.db_manager.execute_query(
                "SELECT * FROM system_config")
            config_df = pd.DataFrame(configs)

            csv = config_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "下载配置文件",
                data=csv,
                file_name=f"system_config_{
                    datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv")
        except Exception as e:
            st.error(f"导出配置失败: {e}")

    def _import_config(self):
        """导入配置"""
        uploaded_file = st.file_uploader(
            "选择配置文件", type=['csv'], key="config_import")

        if uploaded_file and st.button("导入配置"):
            try:
                df = pd.read_csv(uploaded_file)

                success_count = 0
                for _, row in df.iterrows():
                    if self.db_manager.set_system_config(
                        row['config_key'],
                        row['config_value'],
                        row.get('config_type', 'string'),
                        row.get('description', '')
                    ):
                        success_count += 1

                st.success(f"配置导入成功，共导入 {success_count} 条配置")
                st.rerun()

            except Exception as e:
                st.error(f"导入配置失败: {e}")

    def _cleanup_old_logs(self):
        """清理旧日志"""
        try:
            retention_days = int(
                self.db_manager.get_system_config("log_retention") or "30")
            cutoff_date = datetime.now() - timedelta(days=retention_days)

            result = self.db_manager.execute_update(
                "DELETE FROM import_logs WHERE created_at < ?",
                (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),)
            )

            if result:
                st.success(f"已清理 {retention_days} 天前的日志")
            else:
                st.error("日志清理失败")

        except Exception as e:
            st.error(f"清理旧日志失败: {e}")

    def _cleanup_temp_data(self):
        """清理临时数据"""
        st.markdown("#### 临时数据清理")

        # 清理选项
        st.markdown("##### 清理选项")
        col1, col2 = st.columns(2)
        with col1:
            clean_duplicates = st.checkbox(
                "清理重复数据", value=True, help="清理各表中的重复记录")
        with col2:
            clean_old_logs = st.checkbox(
                "清理旧日志", value=True, help="清理超过30天的导入日志")

        col3, col4 = st.columns(2)
        with col3:
            clean_empty_records = st.checkbox(
                "清理空记录", value=True, help="清理关键字段为空的记录")
        with col4:
            clean_orphaned_records = st.checkbox(
                "清理孤立记录", value=True, help="清理没有对应映射的小区记录")

        # 高级选项
        with st.expander("高级清理选项"):
            col5, col6 = st.columns(2)
            with col5:
                days_threshold = st.number_input(
                    "日志保留天数", value=30, min_value=1, max_value=365, help="保留最近N天的日志")
            with col6:
                batch_size = st.number_input(
                    "批处理大小",
                    value=1000,
                    min_value=100,
                    max_value=10000,
                    help="每次清理的记录数")

        if st.button("开始数据清理", type="primary"):
            self._execute_data_cleanup(
                clean_duplicates,
                clean_old_logs,
                clean_empty_records,
                clean_orphaned_records,
                days_threshold,
                batch_size)

    def _execute_data_cleanup(
            self,
            clean_duplicates,
            clean_old_logs,
            clean_empty_records,
            clean_orphaned_records,
            days_threshold,
            batch_size):
        """执行数据清理"""
        try:
            st.info("🧹 开始数据清理...")
            cleanup_results = {}

            # 1. 清理重复数据
            if clean_duplicates:
                st.write("1️⃣ 清理重复数据...")
                duplicates_result = self._clean_duplicate_data()
                cleanup_results['重复数据'] = duplicates_result
                st.success(f"✅ 重复数据清理完成: {duplicates_result}")

            # 2. 清理旧日志
            if clean_old_logs:
                st.write("2️⃣ 清理旧日志...")
                logs_result = self._clean_old_logs(days_threshold)
                cleanup_results['旧日志'] = logs_result
                st.success(f"✅ 旧日志清理完成: {logs_result}")

            # 3. 清理空记录
            if clean_empty_records:
                st.write("3️⃣ 清理空记录...")
                empty_result = self._clean_empty_records()
                cleanup_results['空记录'] = empty_result
                st.success(f"✅ 空记录清理完成: {empty_result}")

            # 4. 清理孤立记录
            if clean_orphaned_records:
                st.write("4️⃣ 清理孤立记录...")
                orphaned_result = self._clean_orphaned_records()
                cleanup_results['孤立记录'] = orphaned_result
                st.success(f"✅ 孤立记录清理完成: {orphaned_result}")

            # 显示清理结果
            st.markdown("##### 清理结果汇总")
            for item, result in cleanup_results.items():
                st.write(f"• {item}: {result}")

            st.success("🎉 数据清理完成！")

        except Exception as e:
            st.error(f"数据清理失败: {e}")

    def _clean_duplicate_data(self):
        """清理重复数据"""
        try:
            total_cleaned = 0

            # 清理性能数据重复
            performance_duplicates = self.db_manager.execute_update("""
                DELETE FROM performance_data
                WHERE id NOT IN (
                    SELECT MIN(id) FROM performance_data
                    GROUP BY data_type, start_time, cgi
                )
            """)
            total_cleaned += performance_duplicates

            # 清理干扰数据重复
            interference_duplicates = self.db_manager.execute_update("""
                DELETE FROM interference_data
                WHERE id NOT IN (
                    SELECT MIN(id) FROM interference_data
                    GROUP BY start_time, cgi
                )
            """)
            total_cleaned += interference_duplicates

            return f"清理了 {total_cleaned} 条重复记录"

        except Exception as e:
            return f"清理失败: {e}"

    def _clean_old_logs(self, days_threshold):
        """清理旧日志"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_threshold)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

            # 清理导入日志
            logs_cleaned = self.db_manager.execute_update("""
                DELETE FROM import_logs
                WHERE created_at < ?
            """, (cutoff_str,))

            return f"清理了 {logs_cleaned} 条旧日志记录"

        except Exception as e:
            return f"清理失败: {e}"

    def _clean_empty_records(self):
        """清理空记录"""
        try:
            total_cleaned = 0

            # 清理性能数据中的空记录
            empty_performance = self.db_manager.execute_update("""
                DELETE FROM performance_data
                WHERE cgi IS NULL OR cgi = '' OR start_time IS NULL OR start_time = ''
            """)
            total_cleaned += empty_performance

            # 清理干扰数据中的空记录
            empty_interference = self.db_manager.execute_update("""
                DELETE FROM interference_data
                WHERE cgi IS NULL OR cgi = '' OR start_time IS NULL OR start_time = ''
            """)
            total_cleaned += empty_interference

            return f"清理了 {total_cleaned} 条空记录"

        except Exception as e:
            return f"清理失败: {e}"

    def _clean_orphaned_records(self):
        """清理孤立记录"""
        try:
            total_cleaned = 0

            # 清理没有对应映射的性能数据
            orphaned_performance = self.db_manager.execute_update("""
                DELETE FROM performance_data
                WHERE cgi NOT IN (SELECT cgi FROM cell_mapping WHERE cgi IS NOT NULL)
            """)
            total_cleaned += orphaned_performance

            # 清理没有对应映射的干扰数据
            orphaned_interference = self.db_manager.execute_update("""
                DELETE FROM interference_data
                WHERE cgi NOT IN (SELECT cgi FROM cell_mapping WHERE cgi IS NOT NULL)
            """)
            total_cleaned += orphaned_interference

            return f"清理了 {total_cleaned} 条孤立记录"

        except Exception as e:
            return f"清理失败: {e}"

    def _delete_data_by_date_range(self, data_type_label, start_date, end_date):
        """按日期范围删除干扰数据和性能数据（容量）"""
        try:
            if start_date > end_date:
                st.error("开始日期不能晚于结束日期")
                return

            deleted_messages = []

            # 1. 干扰数据：使用 date_str (YYYYMMDD)
            if data_type_label in ("干扰数据", "干扰+性能（容量）"):
                s_str = start_date.strftime('%Y%m%d')
                e_str = end_date.strftime('%Y%m%d')

                # 查询将被删除的记录数
                count_sql = """
                SELECT COUNT(*) as count FROM interference_data
                WHERE date_str BETWEEN ? AND ?
                """
                count_result = self.db_manager.execute_query(count_sql, (s_str, e_str))
                del_count = count_result[0]['count'] if count_result else 0

                if del_count > 0:
                    delete_sql = """
                    DELETE FROM interference_data
                    WHERE date_str BETWEEN ? AND ?
                    """
                    ok = self.db_manager.execute_update(delete_sql, (s_str, e_str))
                    if ok:
                        deleted_messages.append(f"干扰数据 {del_count} 条")
                    else:
                        st.error("删除干扰数据失败")
                else:
                    deleted_messages.append("干扰数据 0 条（所选日期无数据）")

            # 2. 性能数据（容量）：使用 start_time，按日期截取
            if data_type_label in ("性能数据（容量）", "干扰+性能（容量）"):
                s_dt = start_date.strftime('%Y-%m-%d 00:00:00')
                e_dt = end_date.strftime('%Y-%m-%d 23:59:59')

                count_sql = """
                SELECT COUNT(*) as count FROM performance_data
                WHERE data_type = 'capacity'
                  AND start_time BETWEEN ? AND ?
                """
                count_result = self.db_manager.execute_query(count_sql, (s_dt, e_dt))
                del_count = count_result[0]['count'] if count_result else 0

                if del_count > 0:
                    delete_sql = """
                    DELETE FROM performance_data
                    WHERE data_type = 'capacity'
                      AND start_time BETWEEN ? AND ?
                    """
                    ok = self.db_manager.execute_update(delete_sql, (s_dt, e_dt))
                    if ok:
                        deleted_messages.append(f"性能数据（容量） {del_count} 条")
                    else:
                        st.error("删除性能数据（容量）失败")
                else:
                    deleted_messages.append("性能数据（容量） 0 条（所选日期无数据）")

            if deleted_messages:
                msg = "；".join(deleted_messages)
                st.success(f"删除完成：{msg}")
            else:
                st.info("未执行删除操作")

        except Exception as e:
            st.error(f"按日期删除数据失败: {e}")

    def _cleanup_duplicate_data(self):
        """清理重复数据"""
        try:
            # 清理重复的干扰数据
            interference_duplicates = self.db_manager.execute_update("""
                DELETE FROM interference_data
                WHERE id NOT IN (
                    SELECT MIN(id) FROM interference_data
                    GROUP BY date_str, cgi
                )
            """)

            # 清理重复的容量数据
            capacity_duplicates = self.db_manager.execute_update("""
                DELETE FROM capacity_data
                WHERE id NOT IN (
                    SELECT MIN(id) FROM capacity_data
                    GROUP BY start_time, cgi
                )
            """)

            # 清理重复的流量数据
            traffic_duplicates = self.db_manager.execute_update("""
                DELETE FROM performance_data
                WHERE data_type = 'traffic'
                AND id NOT IN (
                    SELECT MIN(id) FROM performance_data
                    WHERE data_type = 'traffic'
                    GROUP BY start_time, cgi
                )
            """)

            st.success("重复数据清理完成")

        except Exception as e:
            st.error(f"清理重复数据失败: {e}")

    def _generate_data_statistics(self):
        """生成数据统计报告"""
        try:
            stats = self.db_manager.get_database_stats()

            # 创建统计报告
            report = {
                "生成时间": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "数据库大小": f"{stats.get('db_size_mb', 0):.1f} MB",
                "各表记录数": {
                    "小区映射表": stats.get('cell_mapping_count', 0),
                    "工参表": stats.get('engineering_params_count', 0),
                    "干扰数据表": stats.get('interference_data_count', 0),
                    "容量数据表": stats.get('capacity_data_count', 0),
                    "流量数据表": self.db_manager.execute_query("SELECT COUNT(*) as count FROM performance_data WHERE data_type = 'traffic'")[0]['count'],
                    "工具表": stats.get('tools_count', 0),
                    "配置表": stats.get('system_config_count', 0),
                    "日志表": stats.get('import_logs_count', 0)
                }
            }

            st.json(report)

            # 下载统计报告
            report_json = json.dumps(report, ensure_ascii=False, indent=2)
            st.download_button(
                "下载统计报告",
                data=report_json.encode('utf-8'),
                file_name=f"data_statistics_{
                    datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json")

        except Exception as e:
            st.error(f"生成数据统计报告失败: {e}")

    def _display_logs(self, tool_filter, status_filter, limit):
        """显示日志"""
        try:
            # 构建查询条件
            where_conditions = []
            params = []

            if tool_filter != "全部":
                where_conditions.append("tool_name = ?")
                params.append(tool_filter)

            if status_filter != "全部":
                where_conditions.append("status = ?")
                params.append(status_filter)

            where_clause = " AND ".join(
                where_conditions) if where_conditions else "1=1"

            sql = """
            SELECT * FROM import_logs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """
            params.append(limit)

            logs = self.db_manager.execute_query(sql, tuple(params))

            if logs:
                logs_df = pd.DataFrame(logs)
                st.dataframe(
                    logs_df,
                    use_container_width=True,
                    hide_index=True)

                # 显示统计信息
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("总记录数", len(logs))
                with col2:
                    success_count = len(
                        [log for log in logs if log['status'] == 'success'])
                    st.metric("成功记录", success_count)
                with col3:
                    error_count = len(
                        [log for log in logs if log['status'] == 'error'])
                    st.metric("失败记录", error_count)
            else:
                st.info("没有找到符合条件的日志记录")

        except Exception as e:
            st.error(f"查询日志失败: {e}")

    def _export_logs(self):
        """导出日志"""
        try:
            logs = self.db_manager.get_import_logs(limit=1000)
            logs_df = pd.DataFrame(logs)

            csv = logs_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "下载日志文件",
                data=csv,
                file_name=f"import_logs_{
                    datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv")
        except Exception as e:
            st.error(f"导出日志失败: {e}")

    def _cleanup_logs(self):
        """清理日志"""
        try:
            # 保留最近30天的日志
            cutoff_date = datetime.now() - timedelta(days=30)

            result = self.db_manager.execute_update(
                "DELETE FROM import_logs WHERE created_at < ?",
                (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),)
            )

            if result:
                st.success("日志清理完成")
            else:
                st.error("日志清理失败")

        except Exception as e:
            st.error(f"清理日志失败: {e}")

    def _optimize_database(self):
        """优化数据库"""
        try:
            # 执行VACUUM操作
            self.db_manager.execute_update("VACUUM")
            st.success("数据库优化完成")
        except Exception as e:
            st.error(f"数据库优化失败: {e}")

    def _check_database_integrity(self):
        """检查数据库完整性"""
        try:
            # 执行PRAGMA integrity_check
            result = self.db_manager.execute_query("PRAGMA integrity_check")

            if result and result[0]['integrity_check'] == 'ok':
                st.success("数据库完整性检查通过")
            else:
                st.error("数据库完整性检查失败")

        except Exception as e:
            st.error(f"数据库完整性检查失败: {e}")

    def _rebuild_indexes(self):
        """重建索引"""
        try:
            # 删除所有索引
            indexes = self.db_manager.execute_query(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")

            for index in indexes:
                self.db_manager.execute_update(
                    f"DROP INDEX IF EXISTS {index['name']}")

            # 重新创建索引
            self.db_manager._create_indexes(self.db_manager.get_connection())

            st.success("索引重建完成")

        except Exception as e:
            st.error(f"索引重建失败: {e}")

    def _get_system_info(self):
        """获取系统信息"""
        try:
            stats = self.db_manager.get_database_stats()

            return {
                "系统版本": "优化百宝箱工具集 v1.0.0",
                "数据库路径": self.db_manager.db_path,
                "数据库大小": f"{stats.get('db_size_mb', 0):.1f} MB",
                "记录总数": sum([
                    stats.get('cell_mapping_count', 0),
                    stats.get('engineering_params_count', 0),
                    stats.get('interference_data_count', 0),
                    self.db_manager.execute_query("SELECT COUNT(*) as count FROM performance_data WHERE data_type = 'capacity'")[0]['count'],
                    stats.get('traffic_data_count', 0)
                ]),
                "工具数量": stats.get('tools_count', 0),
                "配置项数量": stats.get('system_config_count', 0)
            }
        except Exception as e:
            return {"错误": str(e)}

    def _export_system_info(self, system_info):
        """导出系统信息"""
        try:
            info_json = json.dumps(system_info, ensure_ascii=False, indent=2)
            st.download_button(
                "下载系统信息",
                data=info_json.encode('utf-8'),
                file_name=f"system_info_{
                    datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json")
        except Exception as e:
            st.error(f"导出系统信息失败: {e}")

    def _reset_system(self):
        """重置系统"""
        try:
            # 清空所有数据表
            tables = [
                'cell_mapping', 'engineering_params', 'interference_data',
                'capacity_data', 'traffic_data', 'import_logs'
            ]

            for table in tables:
                self.db_manager.execute_update(f"DELETE FROM {table}")

            st.success("系统重置完成")
            st.rerun()

        except Exception as e:
            st.error(f"系统重置失败: {e}")
    
    def _check_grid_name_mapping(self):
        """检查网格名称映射"""
        try:
            st.info("🔍 正在检查网格名称映射...")
            
            # 统计网格名称的分布情况
            query = """
                SELECT 
                    grid_name,
                    COUNT(*) as count,
                    COUNT(DISTINCT grid_id) as unique_grid_ids,
                    COUNT(DISTINCT cgi) as unique_cgis
                FROM cell_mapping
                WHERE grid_name IS NOT NULL AND grid_name != ''
                GROUP BY grid_name
                ORDER BY count DESC
                LIMIT 50
            """
            
            results = self.db_manager.execute_query(query)
            
            if results:
                df = pd.DataFrame(results)
                st.success(f"✅ 检查完成，共发现 {len(df)} 种不同的网格名称")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("⚠️ 未找到网格名称数据")
                
        except Exception as e:
            st.error(f"检查网格名称映射失败: {e}")
            self.logger.error(f"检查网格名称映射失败: {e}")
    
    def _check_grid_name_city_mapping(self):
        """检查网格名称错误映射为地市名称的记录"""
        try:
            st.info("🔍 正在检查网格名称错误映射（地市名称）...")
            
            # 常见的地市名称列表（可根据实际情况扩展）
            city_names = [
                '阳江', '广州', '深圳', '珠海', '汕头', '佛山', '韶关', '湛江',
                '肇庆', '江门', '茂名', '惠州', '梅州', '汕尾', '河源', '清远',
                '东莞', '中山', '潮州', '揭阳', '云浮', '阳江市', '广州市', '深圳市'
            ]
            
            # 构建查询条件
            city_conditions = "', '".join(city_names)
            query = f"""
                SELECT 
                    cgi,
                    celname,
                    grid_id,
                    grid_name,
                    COUNT(*) as count
                FROM cell_mapping
                WHERE grid_name IN ('{city_conditions}')
                GROUP BY cgi, grid_id, grid_name
                ORDER BY count DESC
            """
            
            results = self.db_manager.execute_query(query)
            
            if results:
                df = pd.DataFrame(results)
                
                # 统计信息
                total_records = len(df)
                unique_cgis = df['cgi'].nunique()
                unique_grid_ids = df['grid_id'].nunique()
                city_distribution = df['grid_name'].value_counts()
                
                st.warning(f"⚠️ **发现 {total_records} 条网格名称错误映射为地市名称的记录**")
                st.write(f"  • 涉及小区数: {unique_cgis:,}")
                st.write(f"  • 涉及网格ID数: {unique_grid_ids:,}")
                
                st.markdown("#### 地市分布统计")
                st.dataframe(city_distribution.reset_index().rename(columns={'index': '地市名称', 'grid_name': '记录数'}), use_container_width=True)
                
                st.markdown("#### 详细记录（前100条）")
                st.dataframe(df.head(100), use_container_width=True)
                
                # 提供修复建议
                st.markdown("#### 💡 修复建议")
                st.info("""
                这些记录的网格名称被错误地映射为地市名称。修复方法：
                1. 重新运行"映射小区数据导入"功能（已修复映射逻辑）
                2. 系统会优先从engineering_params表的"grid_name_no_buffer"或"grid_name_buffer_500m"字段获取网格名称
                3. 不再使用CSV文件的"地市"列作为网格名称
                """)
                
                # 导出功能
                if st.button("📥 导出错误映射记录", type="primary"):
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        "下载CSV文件",
                        data=csv,
                        file_name=f"网格名称错误映射检查_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            else:
                st.success("✅ 未发现网格名称错误映射为地市名称的记录")
                
        except Exception as e:
            st.error(f"检查网格名称错误映射失败: {e}")
            self.logger.error(f"检查网格名称错误映射失败: {e}")
