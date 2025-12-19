# -*- coding: utf-8 -*-
"""
优化百宝箱工具集 - 统一数据库管理模块
提供统一的数据库连接、表结构管理和数据操作接口

最后更新: 2025-11-12
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

# 常量定义
DEFAULT_DB_NAME = 'optimization_toolbox.db'
BEIJING_TIMEZONE_OFFSET = '+8 hours'
DEFAULT_TOOL_VERSION = '1.0.0'
DEFAULT_IMPORT_LOG_LIMIT = 100

# 中文字段到英文字段的映射
GRID_FIELD_MAPPING = {
    # 中文字段名 -> 英文字段名
    '网格ID_不缓冲': 'grid_id_no_buffer',
    '网格名_不缓冲': 'grid_name_no_buffer', 
    '网格标签_不缓冲': 'grid_label_no_buffer',
    '网格ID_缓冲500米': 'grid_id_buffer_500m',
    '网格名_缓冲500米': 'grid_name_buffer_500m',
    '网格标签_缓冲500米': 'grid_label_buffer_500m'
}

# 英文字段到中文字段的反向映射
GRID_FIELD_REVERSE_MAPPING = {v: k for k, v in GRID_FIELD_MAPPING.items()}

# 允许动态添加的网格字段白名单（防止SQL注入）
ALLOWED_GRID_COLUMNS = {
    # 中文字段名（向后兼容）
    '网格ID_不缓冲',
    '网格名_不缓冲',
    '网格标签_不缓冲',
    '网格ID_缓冲500米',
    '网格名_缓冲500米',
    '网格标签_缓冲500米',
    # 英文字段名（新标准）
    'grid_id_no_buffer',
    'grid_name_no_buffer',
    'grid_label_no_buffer',
    'grid_id_buffer_500m',
    'grid_name_buffer_500m',
    'grid_label_buffer_500m'
}

class DatabaseManager:
    """统一数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径，默认为当前目录下的optimization_toolbox.db
        """
        if db_path is None:
            # 使用脚本所在目录作为数据库路径，避免多实例冲突
            currentDir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(currentDir, DEFAULT_DB_NAME)
        else:
            self.db_path = db_path
        
        # 初始化日志记录器以追踪数据库操作和错误
        self.logger = logging.getLogger(__name__)
        
        # 创建数据库目录以避免文件写入失败
        dbDir = os.path.dirname(self.db_path)
        if dbDir:
            os.makedirs(dbDir, exist_ok=True)
        
        # 初始化数据库表结构和索引
        self._init_database()
    
    def _init_database(self):
        """
        初始化数据库表结构
        
        创建所有必要的表、索引和视图，确保数据库架构完整
        
        Raises:
            Exception: 当数据库初始化失败时抛出异常
        """
        try:
            with self.get_connection() as conn:
                self._create_tables(conn)
                self._migrate_panel_data_table(conn)
                self._create_indexes(conn)
                self._create_views(conn)
                self._load_excluded_scheme_list(conn)
            self.logger.info("数据库初始化完成")
        except sqlite3.Error as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
    
    def get_connection(self):
        """
        获取数据库连接
        
        配置连接参数以确保数据完整性和正确的时区处理
        
        Returns:
            sqlite3.Connection: 配置好的数据库连接对象
        """
        conn = sqlite3.connect(self.db_path)
        # 使用Row工厂以支持字典式访问查询结果
        conn.row_factory = sqlite3.Row
        # 启用外键约束以保证数据引用完整性
        conn.execute('PRAGMA foreign_keys = ON')
        # 允许多线程访问以支持并发操作
        conn.execute('PRAGMA check_same_thread = False')
        # 设置时区为东8区以确保时间戳正确
        conn.execute("PRAGMA timezone = '+08:00'")
        return conn

    def _configure_bulk_pragmas(self, conn: sqlite3.Connection) -> Dict[str, Optional[str]]:
        """为批量写入配置高性能PRAGMA，返回原始配置以便恢复"""
        pragmas = {
            'synchronous': 'OFF',
            'journal_mode': 'MEMORY',
            'temp_store': 'MEMORY'
        }
        previous = {}
        try:
            for key, value in pragmas.items():
                try:
                    prev_row = conn.execute(f"PRAGMA {key}").fetchone()
                    previous[key] = prev_row[0] if prev_row else None
                except sqlite3.Error:
                    previous[key] = None
                conn.execute(f"PRAGMA {key} = {value}")
        except sqlite3.Error as e:
            self.logger.warning(f"配置批量PRAGMA失败: {e}")
        return previous

    def _restore_pragmas(self, conn: sqlite3.Connection, previous: Dict[str, Optional[str]]):
        """恢复批量写入前的PRAGMA设置"""
        if not previous:
            return
        for key, value in previous.items():
            if value in (None, ''):
                continue
            try:
                conn.execute(f"PRAGMA {key} = {value}")
            except sqlite3.Error as e:
                self.logger.warning(f"恢复PRAGMA {key} 失败: {e}")
    
    def _create_tables(self, conn: sqlite3.Connection):
        """
        创建所有必要的表
        
        定义完整的数据库架构，包括所有业务表和系统表
        
        Args:
            conn: 数据库连接对象
        """
        cursor = conn.cursor()
        
        # 1. 工具信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL UNIQUE,
            tool_type TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0.0',
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            config_json TEXT
        )
        ''')
        
        # 2. 统一小区映射表（整合两个脚本的小区表）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cell_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cgi TEXT NOT NULL,
            celname TEXT,
            grid_id TEXT,
            grid_name TEXT,
            grid_pp TEXT,
            zhishi TEXT,
            pinduan TEXT,
            tt_mark TEXT,
            if_cell TEXT,
            if_flag TEXT,
            if_online TEXT,
            lon REAL,
            lat REAL,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            UNIQUE (cgi, grid_id)
        )
        ''')
        
        # 3. 工参表（统一工参信息）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS engineering_params (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cgi TEXT NOT NULL UNIQUE,
            celname TEXT,
            lat REAL,
            lon REAL,
            zhishi TEXT,
            pinduan TEXT,
            ant_dir REAL,
            phy_name TEXT,
            phy_id TEXT,
            antenna_name TEXT,
            elect_tilt REAL,
            mech_tilt REAL,
            ant_height REAL,
            stauts_unit TEXT,
            jifang_name TEXT,
            manufacturer TEXT,
            area_compy TEXT,
            site_type TEXT,
            pl_item TEXT,
            grid_id_no_buffer TEXT,
            grid_name_no_buffer TEXT,
            grid_label_no_buffer TEXT,
            grid_id_buffer_500m TEXT,
            grid_name_buffer_500m TEXT,
            grid_label_buffer_500m TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 动态添加网格字段以支持历史数据库的平滑升级
        cursor.execute("PRAGMA table_info(engineering_params)")
        existingColumns = [row[1] for row in cursor.fetchall()]
        
        # 需要添加的字段列表（使用英文字段名）
        gridColumns = [
            'grid_id_no_buffer',
            'grid_name_no_buffer',
            'grid_label_no_buffer',
            'grid_id_buffer_500m',
            'grid_name_buffer_500m',
            'grid_label_buffer_500m'
        ]
        
        # 添加缺失的字段（使用白名单验证防止SQL注入）
        for colName in gridColumns:
            if colName not in existingColumns:
                # 验证字段名在白名单中
                if colName not in ALLOWED_GRID_COLUMNS:
                    self.logger.warning(f"字段名不在白名单中，跳过: {colName}")
                    continue
                try:
                    # 使用参数化查询的替代方案：白名单验证后拼接
                    sql = f"ALTER TABLE engineering_params ADD COLUMN {colName} TEXT"
                    cursor.execute(sql)
                    self.logger.info(f"成功添加字段: {colName}")
                except sqlite3.OperationalError as e:
                    self.logger.warning(f"添加字段失败 {colName}: {e}")
        
        # 4. 干扰数据表（来自app_streamlit.py）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS interference_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_str TEXT NOT NULL,
            cgi TEXT NOT NULL,
            celname TEXT,
            zhishi TEXT,
            pinduan TEXT,
            rip_str TEXT,
            if_rip TEXT,
            interference_type TEXT,
            omcr TEXT,
            data_points INTEGER,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            UNIQUE (date_str, cgi)
        )
        ''')
        
        # 5. 性能数据表（合并容量数据和流量数据）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_type TEXT NOT NULL,
            start_time TEXT NOT NULL,
            cgi TEXT NOT NULL,
            celname TEXT,
            pinduan TEXT,
            phy_name TEXT,
            flwor_day REAL,
            if_overcel TEXT,
            ul_prb_mang REAL,
            dl_prb_mang REAL,
            pdcch_mang REAL,
            rrc_average REAL,
            rrc_max REAL,
            flwor_ul_mang REAL,
            flwor_dl_mang REAL,
            prb_max REAL,
            cco_area_name TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            UNIQUE (data_type, start_time, cgi)
        )
        ''')
        
        
        # 7. 系统配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE,
            config_value TEXT,
            config_type TEXT DEFAULT 'string',
            description TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 8. 数据导入日志表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS import_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            file_name TEXT,
            import_type TEXT,
            records_count INTEGER,
            success_count INTEGER,
            error_count INTEGER,
            status TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 9. 版本历史表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS version_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_version TEXT,
            to_version TEXT,
            update_type TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 10. 迁移历史表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_file TEXT UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 11. 面板数据表（存储面板读取的数据）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS panel_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT,
            optimize_number TEXT,
            process_status TEXT,
            start_time TEXT,
            grid_code TEXT NOT NULL,
            grid_name TEXT,
            label TEXT,
            city TEXT NOT NULL,
            district TEXT,
            reason_category TEXT,
            root_cause TEXT,
            scheme_category TEXT,
            measures TEXT,
            scheme_type TEXT,
            cell_name TEXT,
            adjust_param TEXT,
            adjust_before_value TEXT,
            target_value TEXT,
            sub_order_number TEXT,
            sub_order_status TEXT,
            implement_results TEXT,
            scheme_id TEXT,
            exclude_status TEXT,
            update_label TEXT,
            scheme_submit_time TEXT,
            scheme_complete_time TEXT,
            scheme_execution_time REAL,
            scheme_standard_time REAL,
            scheme_status TEXT,
            filename TEXT,
            import_batch_id TEXT,
            vcoptimize_object_name TEXT,
            vcisvail TEXT,
            vcmeasure_code TEXT,
            current_act_name TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 12. 面板数据导入批次表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS panel_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL UNIQUE,
            import_time TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            file_count INTEGER,
            total_records INTEGER,
            success_records INTEGER,
            error_records INTEGER,
            status TEXT DEFAULT 'completed',
            description TEXT
        )
        ''')
        
        # 13. 面板数据评估结果表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS panel_evaluation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            city TEXT NOT NULL,
            grid_code TEXT NOT NULL,
            grid_name TEXT,
            process_score REAL,
            scheme_count INTEGER,
            scheme_stats_json TEXT,
            evaluation_params_json TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            FOREIGN KEY (batch_id) REFERENCES panel_import_batches(batch_id)
        )
        ''')
        
        # 14. 面板数据地市汇总表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS panel_city_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            city TEXT NOT NULL,
            grid_type TEXT NOT NULL,
            total_grids INTEGER,
            avg_score REAL,
            total_score REAL,
            scheme_stats_json TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            FOREIGN KEY (batch_id) REFERENCES panel_import_batches(batch_id),
            UNIQUE (batch_id, city, grid_type)
        )
        ''')
        
        # 15. 超时方案清单表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeout_scheme_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_id TEXT NOT NULL UNIQUE,
            order_number TEXT,
            optimize_number TEXT,
            process_status TEXT,
            start_time TEXT,
            grid_code TEXT,
            grid_name TEXT,
            label TEXT,
            city TEXT,
            district TEXT,
            reason_category TEXT,
            root_cause TEXT,
            scheme_category TEXT,
            measures TEXT,
            scheme_type TEXT,
            cell_name TEXT,
            adjust_param TEXT,
            adjust_before_value TEXT,
            target_value TEXT,
            sub_order_number TEXT,
            sub_order_status TEXT,
            implement_results TEXT,
            exclude_status TEXT,
            update_label TEXT,
            scheme_submit_time TEXT,
            scheme_complete_time TEXT,
            scheme_execution_time REAL,
            scheme_standard_time REAL,
            scheme_status TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 16. 网格结果得分表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS grid_result_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_period TEXT NOT NULL,
            grid_code TEXT NOT NULL,
            province TEXT,
            grid_name TEXT,
            scene_detail TEXT,
            scene_merged TEXT,
            city TEXT,
            city_district TEXT,
            city_company TEXT,
            scene_area_attribute TEXT,
            group_name TEXT,
            supervise_label_2025 TEXT,
            final_score REAL,
            complaint_count INTEGER,
            daily_max_rrc_users INTEGER,
            grid_result_data_json TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            UNIQUE(time_period, grid_code)
        )
        ''')
        
        # 17. 排除方案清单表（存储24年完成的方案ID，不参与过程分计算）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS excluded_scheme_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
        )
        ''')
        
        # 18. 北向小区基站数据表（字段名已改为英文）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS north_cell_base_station_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            manufacturer TEXT,
            network_type TEXT,
            cell_name TEXT,
            cgi TEXT NOT NULL,
            base_station_id TEXT,
            base_station_name TEXT,
            celllocalid TEXT,
            check_localcellid TEXT,
            cell_lifecycle_status TEXT,
            station_lifecycle_status TEXT,
            coverage_type TEXT,
            zte_lte_subnet TEXT,
            zte_lte_meid TEXT,
            zte_5g_subnet TEXT,
            zte_5g_meid TEXT,
            created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            updated_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
            UNIQUE(cgi)
        )
        ''')
        
        conn.commit()
    
    def _migrate_panel_data_table(self, conn: sqlite3.Connection):
        """
        迁移panel_data表结构，添加新字段
        如果表已存在但缺少新字段，则添加这些字段
        """
        cursor = conn.cursor()
        
        try:
            # 检查表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='panel_data'
            """)
            if not cursor.fetchone():
                return  # 表不存在，会在_create_tables中创建
            
            # 获取现有列名
            cursor.execute("PRAGMA table_info(panel_data)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            # 定义需要添加的新字段（按顺序）
            new_columns = [
                ('order_number', 'TEXT'),
                ('optimize_number', 'TEXT'),
                ('process_status', 'TEXT'),
                ('start_time', 'TEXT'),
                ('district', 'TEXT'),
                ('reason_category', 'TEXT'),
                ('root_cause', 'TEXT'),
                ('scheme_category', 'TEXT'),
                ('measures', 'TEXT'),
                ('cell_name', 'TEXT'),
                ('adjust_param', 'TEXT'),
                ('adjust_before_value', 'TEXT'),
                ('target_value', 'TEXT'),
                ('sub_order_number', 'TEXT'),
                ('sub_order_status', 'TEXT'),
                ('exclude_status', 'TEXT'),
                ('update_label', 'TEXT'),
                ('scheme_submit_time', 'TEXT'),
                ('scheme_complete_time', 'TEXT'),
                ('scheme_execution_time', 'REAL'),
                ('scheme_standard_time', 'REAL'),
                ('scheme_status', 'TEXT'),
            ]
            
            # 添加缺失的列
            for column_name, column_type in new_columns:
                if column_name not in existing_columns:
                    try:
                        # 使用参数化查询避免SQL注入（虽然这里column_name是受控的）
                        cursor.execute(f"ALTER TABLE panel_data ADD COLUMN {column_name} {column_type}")
                        self.logger.info(f"已添加列: {column_name} ({column_type})")
                    except sqlite3.Error as e:
                        self.logger.warning(f"添加列 {column_name} 失败: {e}")
                        # 继续处理其他列，不中断迁移过程
            
            # 检查并重命名旧字段（如果需要）
            # 如果存在旧字段名，需要迁移数据
            old_to_new_mapping = {
                'scheme': 'measures',  # 旧字段scheme对应新字段measures
                'order_type': 'scheme_type',  # 旧字段order_type对应新字段scheme_type
                'is_valid': 'exclude_status',  # 旧字段is_valid对应新字段exclude_status
            }
            
            # 检查是否需要迁移数据
            for old_col, new_col in old_to_new_mapping.items():
                if old_col in existing_columns and new_col in existing_columns:
                    try:
                        # 如果旧字段有数据但新字段为空，则迁移数据
                        cursor.execute(f"""
                            UPDATE panel_data 
                            SET {new_col} = {old_col} 
                            WHERE ({new_col} IS NULL OR {new_col} = '') 
                            AND {old_col} IS NOT NULL AND {old_col} != ''
                        """)
                        if cursor.rowcount > 0:
                            self.logger.info(f"已迁移数据: {old_col} -> {new_col} ({cursor.rowcount} 条记录)")
                    except sqlite3.Error as e:
                        self.logger.warning(f"迁移数据 {old_col} -> {new_col} 失败: {e}")
                        # 继续处理其他字段
            
            conn.commit()
            self.logger.info("panel_data表迁移完成")
            
        except sqlite3.Error as e:
            self.logger.error(f"迁移panel_data表失败: {e}")
            conn.rollback()
    
    def _create_indexes(self, conn: sqlite3.Connection):
        """
        创建索引以提高查询性能
        
        为常用查询字段创建索引，显著提升大数据量场景下的查询速度
        
        Args:
            conn: 数据库连接对象
        """
        cursor = conn.cursor()
        
        indexes = [
            # 小区映射表索引
            "CREATE INDEX IF NOT EXISTS idx_cell_mapping_cgi ON cell_mapping(cgi)",
            "CREATE INDEX IF NOT EXISTS idx_cell_mapping_grid_id ON cell_mapping(grid_id)",
            # 网格结果得分表索引
            "CREATE INDEX IF NOT EXISTS idx_grid_result_scores_time_period ON grid_result_scores(time_period)",
            "CREATE INDEX IF NOT EXISTS idx_grid_result_scores_grid_code ON grid_result_scores(grid_code)",
            "CREATE INDEX IF NOT EXISTS idx_grid_result_scores_city ON grid_result_scores(city)",
            "CREATE INDEX IF NOT EXISTS idx_cell_mapping_if_cell ON cell_mapping(if_cell)",
            "CREATE INDEX IF NOT EXISTS idx_cell_mapping_if_flag ON cell_mapping(if_flag)",
            
            # 干扰数据表索引
            "CREATE INDEX IF NOT EXISTS idx_interference_date_cgi ON interference_data(date_str, cgi)",
            "CREATE INDEX IF NOT EXISTS idx_interference_cgi ON interference_data(cgi)",
            "CREATE INDEX IF NOT EXISTS idx_interference_date ON interference_data(date_str)",
            
            # 性能数据表索引（优化查询性能）
            "CREATE INDEX IF NOT EXISTS idx_performance_type_time_cgi ON performance_data(data_type, start_time, cgi)",
            "CREATE INDEX IF NOT EXISTS idx_performance_cgi ON performance_data(cgi)",
            "CREATE INDEX IF NOT EXISTS idx_performance_start_time ON performance_data(start_time)",
            
            # 北向小区基站数据表索引
            "CREATE INDEX IF NOT EXISTS idx_north_cell_cgi ON north_cell_base_station_data(cgi)",
            "CREATE INDEX IF NOT EXISTS idx_north_cell_city ON north_cell_base_station_data(city)",
            "CREATE INDEX IF NOT EXISTS idx_north_cell_manufacturer ON north_cell_base_station_data(manufacturer)",
            "CREATE INDEX IF NOT EXISTS idx_north_cell_network_type ON north_cell_base_station_data(network_type)",
            "CREATE INDEX IF NOT EXISTS idx_performance_data_type ON performance_data(data_type)",
            "CREATE INDEX IF NOT EXISTS idx_performance_if_overcel ON performance_data(if_overcel)",
            "CREATE INDEX IF NOT EXISTS idx_performance_flwor_day ON performance_data(flwor_day)",
            
            # 工参表索引
            "CREATE INDEX IF NOT EXISTS idx_engineering_cgi ON engineering_params(cgi)",
            "CREATE INDEX IF NOT EXISTS idx_engineering_phy_name ON engineering_params(phy_name)",
            
            # 系统表索引
            "CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(tool_name)",
            "CREATE INDEX IF NOT EXISTS idx_import_logs_tool ON import_logs(tool_name)",
            "CREATE INDEX IF NOT EXISTS idx_import_logs_created_at ON import_logs(created_at)",
            
            # 版本管理索引
            "CREATE INDEX IF NOT EXISTS idx_version_history_from_version ON version_history(from_version)",
            "CREATE INDEX IF NOT EXISTS idx_version_history_to_version ON version_history(to_version)",
            "CREATE INDEX IF NOT EXISTS idx_migration_history_file ON migration_history(migration_file)",
        ]
        
        # 执行索引创建（忽略已存在的索引）
        for indexSql in indexes:
            try:
                cursor.execute(indexSql)
            except sqlite3.OperationalError as e:
                self.logger.warning(f"创建索引失败: {e}")
        
        # 为网格字段创建索引以优化网格相关查询性能
        try:
            cursor.execute("PRAGMA table_info(engineering_params)")
            existingColumns = [row[1] for row in cursor.fetchall()]
            
            if 'grid_id_no_buffer' in existingColumns:
                try:
                    sql = """CREATE INDEX IF NOT EXISTS 
                             idx_engineering_params_grid_id_no_buffer 
                             ON engineering_params(grid_id_no_buffer)"""
                    cursor.execute(sql)
                except sqlite3.OperationalError:
                    pass
            if 'grid_id_buffer_500m' in existingColumns:
                try:
                    sql = """CREATE INDEX IF NOT EXISTS 
                             idx_engineering_params_grid_id_buffer_500m 
                             ON engineering_params(grid_id_buffer_500m)"""
                    cursor.execute(sql)
                except sqlite3.OperationalError:
                    pass
        except Exception as e:
            self.logger.warning(f"创建网格字段索引失败: {e}")
        
        # 面板数据表索引
        panel_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_panel_data_city ON panel_data(city)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_grid_code ON panel_data(grid_code)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_batch_id ON panel_data(import_batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_scheme_type ON panel_data(scheme_type)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_implement_results ON panel_data(implement_results)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_label ON panel_data(label)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_created_at ON panel_data(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_vcoptimize_object_name ON panel_data(vcoptimize_object_name)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_vcisvail ON panel_data(vcisvail)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_vcmeasure_code ON panel_data(vcmeasure_code)",
            "CREATE INDEX IF NOT EXISTS idx_panel_data_current_act_name ON panel_data(current_act_name)",
            
            # 面板数据评估结果索引
            "CREATE INDEX IF NOT EXISTS idx_panel_evaluation_batch_id ON panel_evaluation_results(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_panel_evaluation_city ON panel_evaluation_results(city)",
            "CREATE INDEX IF NOT EXISTS idx_panel_evaluation_grid_code ON panel_evaluation_results(grid_code)",
            "CREATE INDEX IF NOT EXISTS idx_panel_evaluation_score ON panel_evaluation_results(process_score)",
            
            # 面板数据地市汇总索引
            "CREATE INDEX IF NOT EXISTS idx_panel_city_summary_batch_id ON panel_city_summary(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_panel_city_summary_city ON panel_city_summary(city)",
            "CREATE INDEX IF NOT EXISTS idx_panel_city_summary_grid_type ON panel_city_summary(grid_type)",
            "CREATE INDEX IF NOT EXISTS idx_panel_city_summary_avg_score ON panel_city_summary(avg_score)",
            
            # 超时方案清单表索引
            "CREATE INDEX IF NOT EXISTS idx_timeout_scheme_list_scheme_id ON timeout_scheme_list(scheme_id)",
            "CREATE INDEX IF NOT EXISTS idx_timeout_scheme_list_city ON timeout_scheme_list(city)",
            "CREATE INDEX IF NOT EXISTS idx_timeout_scheme_list_grid_code ON timeout_scheme_list(grid_code)",
            "CREATE INDEX IF NOT EXISTS idx_timeout_scheme_list_scheme_status ON timeout_scheme_list(scheme_status)"
        ]
        
        # 执行面板数据相关索引创建
        for indexSql in panel_indexes:
            try:
                cursor.execute(indexSql)
            except sqlite3.OperationalError as e:
                self.logger.warning(f"创建面板索引失败: {e}")
        
        conn.commit()
    
    def _create_views(self, conn: sqlite3.Connection):
        """
        创建视图以简化常用查询
        
        定义常用的联合查询视图，简化业务代码并提高开发效率
        
        Args:
            conn: 数据库连接对象
        """
        cursor = conn.cursor()
        
        # 小区完整信息视图
        cursor.execute('''
        CREATE VIEW IF NOT EXISTS cell_full_info AS
        SELECT 
            cm.cgi,
            cm.celname,
            cm.grid_id,
            cm.grid_name,
            cm.grid_pp,
            cm.zhishi,
            cm.pinduan,
            cm.tt_mark,
            cm.if_cell,
            cm.if_flag,
            cm.if_online,
            cm.lon,
            cm.lat,
            ep.ant_dir,
            ep.phy_name,
            ep.phy_id,
            ep.antenna_name,
            ep.elect_tilt,
            ep.mech_tilt,
            ep.ant_height,
            ep.ant_gain
        FROM cell_mapping cm
        LEFT JOIN engineering_params ep ON cm.cgi = ep.cgi
        ''')
        
        conn.commit()
    
    def _load_excluded_scheme_list(self, conn: sqlite3.Connection):
        """
        从 过滤方案ID清单/vcscheme_id.txt 文件加载24年完成的方案ID到数据库
        
        Args:
            conn: 数据库连接对象
        """
        try:
            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 路径改为：过滤方案ID清单/vcscheme_id.txt
            vcscheme_file = os.path.join(current_dir, '过滤方案ID清单', 'vcscheme_id.txt')
            
            if not os.path.exists(vcscheme_file):
                self.logger.warning(f"过滤方案ID清单/vcscheme_id.txt 文件不存在: {vcscheme_file}")
                return
            
            cursor = conn.cursor()
            
            # 读取文件内容
            scheme_ids = []
            with open(vcscheme_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 跳过第一行表头（如果有）
                start_idx = 0
                if lines and 'vcscheme_id' in lines[0]:
                    start_idx = 1
                
                for line in lines[start_idx:]:
                    scheme_id = line.strip()
                    if scheme_id and scheme_id != 'vcscheme_id':
                        scheme_ids.append((scheme_id,))
            
            if not scheme_ids:
                self.logger.info("过滤方案ID清单/vcscheme_id.txt 文件中没有有效的方案ID")
                return
            
            # 批量插入或更新（使用 INSERT OR IGNORE 避免重复）
            insert_sql = """
            INSERT OR IGNORE INTO excluded_scheme_list (scheme_id)
            VALUES (?)
            """
            cursor.executemany(insert_sql, scheme_ids)
            conn.commit()
            
            self.logger.info(f"成功加载 {len(scheme_ids)} 个排除方案ID到数据库")
        except Exception as e:
            self.logger.error(f"加载排除方案清单失败: {e}")
            # 不抛出异常，避免影响数据库初始化
    
    def is_scheme_excluded(self, scheme_id: str) -> bool:
        """
        检查方案ID是否在排除列表中
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            bool: 如果方案ID在排除列表中返回True，否则返回False
        """
        if not scheme_id:
            return False
        
        sql = "SELECT COUNT(*) as count FROM excluded_scheme_list WHERE scheme_id = ?"
        result = self.execute_query(sql, (scheme_id,))
        return result[0]['count'] > 0 if result else False
    
    def execute_query(self, sql: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        执行查询并返回结果
        
        Args:
            sql: SQL查询语句
            params: 查询参数元组
            
        Returns:
            List[Dict[str, Any]]: 查询结果列表，每行为字典格式
            
        Raises:
            Exception: 查询执行失败时抛出异常
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params or ())
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self.logger.error(f"查询执行失败: {e}")
            raise
    
    def execute_update(self, sql: str, params: tuple = None) -> bool:
        """
        执行更新操作
        
        Args:
            sql: SQL更新语句（INSERT/UPDATE/DELETE）
            params: 更新参数元组
            
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params or ())
                conn.commit()
                return True
        except sqlite3.Error as e:
            self.logger.error(f"更新执行失败: {e}")
            return False
    
    def execute_many(self, sql: str, params_list: List[tuple], chunk_size: int = 2000, optimize: bool = True) -> bool:
        """批量执行操作，支持分块与PRAGMA优化"""
        if not params_list:
            return True
        conn = None
        previous_pragmas: Dict[str, Optional[str]] = {}
        try:
            conn = self.get_connection()
            if optimize:
                previous_pragmas = self._configure_bulk_pragmas(conn)
            cursor = conn.cursor()
            if chunk_size and len(params_list) > chunk_size:
                for i in range(0, len(params_list), chunk_size):
                    chunk = params_list[i:i + chunk_size]
                    cursor.executemany(sql, chunk)
            else:
                cursor.executemany(sql, params_list)
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"批量执行失败: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                if optimize and previous_pragmas:
                    self._restore_pragmas(conn, previous_pragmas)
                conn.close()
    
    def get_dataframe(self, sql: str, params: tuple = None) -> pd.DataFrame:
        """执行查询并返回DataFrame"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query(sql, conn, params=params or ())
        except Exception as e:
            self.logger.error(f"DataFrame查询失败: {e}")
            raise
    
    def register_tool(self, tool_name: str, tool_type: str, 
                     version: str = DEFAULT_TOOL_VERSION, 
                     description: str = "", config_json: str = None) -> bool:
        """
        注册工具到系统
        
        Args:
            tool_name: 工具名称
            tool_type: 工具类型
            version: 工具版本号，默认为1.0.0
            description: 工具描述
            config_json: 工具配置JSON字符串
            
        Returns:
            bool: 注册成功返回True，失败返回False
        """
        sql = f'''
        INSERT OR REPLACE INTO tools 
        (tool_name, tool_type, version, description, config_json, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now', '{BEIJING_TIMEZONE_OFFSET}'))
        '''
        return self.execute_update(
            sql, (tool_name, tool_type, version, description, config_json)
        )
    
    def log_import(self, tool_name: str, file_name: str, import_type: str, 
                   records_count: int, success_count: int, error_count: int, 
                   status: str, error_message: str = None) -> bool:
        """记录导入日志"""
        sql = '''
        INSERT INTO import_logs (tool_name, file_name, import_type, records_count, 
                               success_count, error_count, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        return self.execute_update(sql, (tool_name, file_name, import_type, records_count,
                                       success_count, error_count, status, error_message))
    
    def get_system_config(self, config_key: str) -> Optional[str]:
        """获取系统配置"""
        result = self.execute_query("SELECT config_value FROM system_config WHERE config_key = ?", (config_key,))
        return result[0]['config_value'] if result else None
    
    def set_system_config(self, config_key: str, config_value: str, 
                         config_type: str = 'string', description: str = None) -> bool:
        """设置系统配置"""
        sql = '''
        INSERT OR REPLACE INTO system_config (config_key, config_value, config_type, description, updated_at)
        VALUES (?, ?, ?, ?, datetime('now', '+8 hours'))
        '''
        return self.execute_update(sql, (config_key, config_value, config_type, description))
    
    def get_tools_list(self) -> List[Dict[str, Any]]:
        """获取所有工具列表"""
        return self.execute_query("SELECT * FROM tools ORDER BY tool_name")
    
    def get_import_logs(self, tool_name: str = None, 
                       limit: int = DEFAULT_IMPORT_LOG_LIMIT) -> List[Dict[str, Any]]:
        """
        获取导入日志
        
        Args:
            tool_name: 工具名称，为None时返回所有工具的日志
            limit: 返回记录数限制
            
        Returns:
            List[Dict[str, Any]]: 导入日志列表
        """
        if tool_name:
            sql = """SELECT * FROM import_logs 
                     WHERE tool_name = ? 
                     ORDER BY created_at DESC LIMIT ?"""
            return self.execute_query(sql, (tool_name, limit))
        else:
            sql = "SELECT * FROM import_logs ORDER BY created_at DESC LIMIT ?"
            return self.execute_query(sql, (limit,))
    
    def backup_database(self, backup_path: str) -> bool:
        """备份数据库"""
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            self.logger.info(f"数据库备份完成: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"数据库备份失败: {e}")
            return False
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            Dict[str, Any]: 包含各表记录数和数据库大小的统计信息
        """
        stats = {}
        
        # 统计各表记录数以监控数据量
        tables = [
            'cell_mapping', 'engineering_params', 'interference_data', 
            'performance_data', 'tools', 'system_config', 'import_logs'
        ]
        
        for table in tables:
            result = self.execute_query(f"SELECT COUNT(*) as count FROM {table}")
            stats[f"{table}_count"] = result[0]['count'] if result else 0
        
        # 计算数据库文件大小以监控存储使用情况
        try:
            fileSizeBytes = os.path.getsize(self.db_path)
            stats['db_size_mb'] = fileSizeBytes / (1024 * 1024)
        except OSError:
            stats['db_size_mb'] = 0
        
        return stats
    
    def optimize_database(self):
        """
        优化数据库性能
        
        执行VACUUM回收空间，ANALYZE更新统计信息，提升查询性能
        
        Returns:
            bool: 优化成功返回True，失败返回False
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 执行VACUUM回收已删除数据占用的空间
                cursor.execute("VACUUM")
                
                # 执行ANALYZE更新查询优化器的统计信息
                cursor.execute("ANALYZE")
                
                # 执行PRAGMA optimize优化索引
                cursor.execute("PRAGMA optimize")
                
                conn.commit()
            
            self.logger.info("数据库优化完成")
            return True
            
        except sqlite3.Error as e:
            self.logger.error(f"数据库优化失败: {e}")
            return False
    
    def get_query_performance_info(self, query: str):
        """获取查询性能信息"""
        try:
            import time
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 启用查询计划
                cursor.execute("EXPLAIN QUERY PLAN " + query)
                plan = cursor.fetchall()
                
                # 执行查询并测量时间
                start_time = time.time()
                cursor.execute(query)
                results = cursor.fetchall()
                end_time = time.time()
            
            return {
                'execution_time': end_time - start_time,
                'result_count': len(results),
                'query_plan': plan
            }
            
        except Exception as e:
            self.logger.error(f"获取查询性能信息失败: {e}")
            return None
    
    # ==================== 面板数据管理方法 ====================
    
    def clear_panel_data(self) -> bool:
        """清空所有面板数据"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 清空所有面板相关表
                cursor.execute("DELETE FROM panel_data")
                cursor.execute("DELETE FROM panel_evaluation_results")
                cursor.execute("DELETE FROM panel_city_summary")
                cursor.execute("DELETE FROM panel_import_batches")
                conn.commit()
            self.logger.info("面板数据清空完成")
            return True
        except Exception as e:
            self.logger.error(f"清空面板数据失败: {e}")
            return False
    
    def create_panel_import_batch(self, batch_id: str, file_count: int, description: str = "") -> bool:
        """创建面板数据导入批次"""
        sql = '''
        INSERT INTO panel_import_batches (batch_id, file_count, description)
        VALUES (?, ?, ?)
        '''
        return self.execute_update(sql, (batch_id, file_count, description))
    
    def update_panel_import_batch(self, batch_id: str, total_records: int, 
                                success_records: int, error_records: int, status: str = "completed") -> bool:
        """更新面板数据导入批次统计"""
        sql = '''
        UPDATE panel_import_batches 
        SET total_records = ?, success_records = ?, error_records = ?, status = ?
        WHERE batch_id = ?
        '''
        return self.execute_update(sql, (total_records, success_records, error_records, status, batch_id))
    
    def insert_panel_data(self, data_list: List[Dict[str, Any]], batch_id: str) -> bool:
        """批量插入面板数据"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 准备插入数据
                insert_data = []
                for record in data_list:
                    insert_data.append((
                        record.get('order_number', ''),
                        record.get('optimize_number', ''),
                        record.get('process_status', ''),
                        record.get('start_time', ''),
                        record.get('grid_code', ''),
                        record.get('grid_name', ''),
                        record.get('label', ''),
                        record.get('city', ''),
                        record.get('district', ''),
                        record.get('reason_category', ''),
                        record.get('root_cause', ''),
                        record.get('scheme_category', ''),
                        record.get('measures', ''),
                        record.get('scheme_type', ''),
                        record.get('cell_name', ''),
                        record.get('adjust_param', ''),
                        record.get('adjust_before_value', ''),
                        record.get('target_value', ''),
                        record.get('sub_order_number', ''),
                        record.get('sub_order_status', ''),
                        record.get('implement_results', ''),
                        record.get('scheme_id', ''),
                        record.get('exclude_status', ''),
                        record.get('update_label', ''),
                        record.get('scheme_submit_time', ''),
                        record.get('scheme_complete_time', ''),
                        record.get('scheme_execution_time'),
                        record.get('scheme_standard_time'),
                        record.get('scheme_status', ''),
                        record.get('filename', ''),
                        batch_id,
                        record.get('vcoptimize_object_name', ''),
                        record.get('vcisvail', ''),
                        record.get('vcmeasure_code', ''),
                        record.get('current_act_name', '')
                    ))
                
                # 批量插入
                cursor.executemany('''
                INSERT INTO panel_data (order_number, optimize_number, process_status, start_time,
                                      grid_code, grid_name, label, city, district, reason_category,
                                      root_cause, scheme_category, measures, scheme_type, cell_name,
                                      adjust_param, adjust_before_value, target_value, sub_order_number,
                                      sub_order_status, implement_results, scheme_id, exclude_status,
                                      update_label, scheme_submit_time, scheme_complete_time,
                                      scheme_execution_time, scheme_standard_time, scheme_status,
                                      filename, import_batch_id, vcoptimize_object_name, vcisvail,
                                      vcmeasure_code, current_act_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
                
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"插入面板数据失败: {e}")
            return False
    
    def get_panel_data_by_batch(self, batch_id: str) -> List[Dict[str, Any]]:
        """根据批次ID获取面板数据"""
        sql = "SELECT * FROM panel_data WHERE import_batch_id = ? ORDER BY city, grid_code"
        return self.execute_query(sql, (batch_id,))
    
    def get_panel_data_by_city(self, city: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据城市获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE city = ? AND import_batch_id = ? ORDER BY grid_code"
            return self.execute_query(sql, (city, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE city = ? ORDER BY grid_code"
            return self.execute_query(sql, (city,))
    
    def get_panel_data_by_grid(self, grid_code: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据网格代码获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE grid_code = ? AND import_batch_id = ?"
            return self.execute_query(sql, (grid_code, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE grid_code = ?"
            return self.execute_query(sql, (grid_code,))
    
    def get_panel_data_summary(self, batch_id: str = None) -> Dict[str, Any]:
        """获取面板数据汇总统计"""
        if batch_id:
            sql = '''
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT city) as city_count,
                COUNT(DISTINCT grid_code) as grid_count,
                COUNT(DISTINCT scheme_type) as scheme_type_count
            FROM panel_data 
            WHERE import_batch_id = ?
            '''
            result = self.execute_query(sql, (batch_id,))
        else:
            sql = '''
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT city) as city_count,
                COUNT(DISTINCT grid_code) as grid_count,
                COUNT(DISTINCT scheme_type) as scheme_type_count
            FROM panel_data
            '''
            result = self.execute_query(sql)
        
        return result[0] if result else {}
    
    def get_panel_data_by_scheme_type(self, scheme_type: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据方案类型获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE scheme_type = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (scheme_type, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE scheme_type = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (scheme_type,))
    
    def get_panel_data_by_implement_results(self, implement_results: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据实施结果获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE implement_results = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (implement_results, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE implement_results = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (implement_results,))
    
    def get_panel_data_by_label(self, label_pattern: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据标签模式获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE label LIKE ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (f"%{label_pattern}%", batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE label LIKE ? ORDER BY city, grid_code"
            return self.execute_query(sql, (f"%{label_pattern}%",))
    
    def get_panel_import_batches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取面板数据导入批次列表"""
        sql = '''
        SELECT * FROM panel_import_batches 
        ORDER BY import_time DESC 
        LIMIT ?
        '''
        return self.execute_query(sql, (limit,))
    
    def get_latest_panel_batch_id(self) -> str:
        """获取最新的面板数据批次ID"""
        sql = '''
        SELECT batch_id FROM panel_import_batches 
        ORDER BY import_time DESC 
        LIMIT 1
        '''
        result = self.execute_query(sql)
        return result[0]['batch_id'] if result else None
    
    def save_panel_evaluation_results(self, batch_id: str, evaluation_results: List[Dict[str, Any]]) -> bool:
        """保存面板数据评估结果"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 准备评估结果数据
                insert_data = []
                for result in evaluation_results:
                    import json
                    insert_data.append((
                        batch_id,
                        result.get('city', ''),
                        result.get('grid_code', ''),
                        result.get('grid_name', ''),
                        result.get('process_score', 0.0),
                        result.get('scheme_count', 0),
                        json.dumps(result.get('scheme_stats', {}), ensure_ascii=False),
                        json.dumps(result.get('evaluation_params', {}), ensure_ascii=False)
                    ))
                
                # 批量插入评估结果
                cursor.executemany('''
                INSERT INTO panel_evaluation_results (batch_id, city, grid_code, grid_name, 
                                                   process_score, scheme_count, scheme_stats_json, evaluation_params_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
                
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"保存面板评估结果失败: {e}")
            return False
    
    def save_panel_city_summary(self, batch_id: str, city_summary: List[Dict[str, Any]]) -> bool:
        """保存面板数据地市汇总"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 准备地市汇总数据
                insert_data = []
                for summary in city_summary:
                    import json
                    insert_data.append((
                        batch_id,
                        summary.get('city', ''),
                        summary.get('grid_type', ''),
                        summary.get('total_grids', 0),
                        summary.get('avg_score', 0.0),
                        summary.get('total_score', 0.0),
                        json.dumps(summary.get('scheme_stats', {}), ensure_ascii=False)
                    ))
                
                # 批量插入地市汇总
                cursor.executemany('''
                INSERT INTO panel_city_summary (batch_id, city, grid_type, total_grids, 
                                              avg_score, total_score, scheme_stats_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
                
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"保存面板地市汇总失败: {e}")
            return False
    
    def get_panel_evaluation_results(self, batch_id: str = None) -> List[Dict[str, Any]]:
        """获取面板数据评估结果"""
        if batch_id:
            sql = '''
            SELECT * FROM panel_evaluation_results 
            WHERE batch_id = ? 
            ORDER BY city, grid_code
            '''
            return self.execute_query(sql, (batch_id,))
        else:
            sql = '''
            SELECT * FROM panel_evaluation_results 
            ORDER BY created_at DESC, city, grid_code
            '''
            return self.execute_query(sql)
    
    def get_panel_city_summary(self, batch_id: str = None) -> List[Dict[str, Any]]:
        """获取面板数据地市汇总"""
        if batch_id:
            sql = '''
            SELECT * FROM panel_city_summary 
            WHERE batch_id = ? 
            ORDER BY city, grid_type
            '''
            return self.execute_query(sql, (batch_id,))
        else:
            sql = '''
            SELECT * FROM panel_city_summary 
            ORDER BY created_at DESC, city, grid_type
            '''
            return self.execute_query(sql)
    
    def search_panel_data(self, filters: Dict[str, Any], batch_id: str = None) -> List[Dict[str, Any]]:
        """根据条件搜索面板数据"""
        conditions = []
        params = []
        
        # 构建查询条件
        if batch_id:
            conditions.append("p.import_batch_id = ?")
            params.append(batch_id)
        
        if filters.get('city'):
            conditions.append("p.city = ?")
            params.append(filters['city'])
        
        if filters.get('grid_code'):
            conditions.append("p.grid_code = ?")
            params.append(filters['grid_code'])
        
        if filters.get('scheme_type'):
            conditions.append("p.scheme_type = ?")
            params.append(filters['scheme_type'])
        
        if filters.get('implement_results'):
            conditions.append("p.implement_results = ?")
            params.append(filters['implement_results'])
        elif filters.get('implement_results_is_null'):
            conditions.append("(p.implement_results IS NULL OR p.implement_results = '')")
        
        if filters.get('label_pattern'):
            conditions.append("p.label LIKE ?")
            params.append(f"%{filters['label_pattern']}%")
        
        if filters.get('date_from'):
            conditions.append("p.created_at >= ?")
            params.append(filters['date_from'])
        
        if filters.get('date_to'):
            conditions.append("p.created_at <= ?")
            params.append(filters['date_to'])
        
        if filters.get('vcoptimize_object_name'):
            conditions.append("p.vcoptimize_object_name = ?")
            params.append(filters['vcoptimize_object_name'])
        
        if filters.get('vcisvail'):
            conditions.append("p.vcisvail = ?")
            params.append(filters['vcisvail'])
        elif filters.get('vcisvail_is_null'):
            conditions.append("(p.vcisvail IS NULL OR p.vcisvail = '')")
        
        if filters.get('vcmeasure_code'):
            conditions.append("p.vcmeasure_code = ?")
            params.append(filters['vcmeasure_code'])
        
        if filters.get('current_act_name'):
            conditions.append("p.current_act_name = ?")
            params.append(filters['current_act_name'])
        
        # 构建SQL查询，LEFT JOIN timeout_scheme_list 表以获取方案提交时间、方案完成时间和是否超时
        sql = """
        SELECT 
            p.*,
            t.scheme_submit_time,
            t.scheme_complete_time,
            CASE 
                WHEN t.scheme_status IN ('已超时未完成', '超时已完成') THEN '是'
                ELSE '否'
            END as is_timeout
        FROM panel_data p
        LEFT JOIN timeout_scheme_list t ON p.scheme_id = t.scheme_id
        """
        
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY p.city, p.grid_code"
        
        if filters.get('limit'):
            sql += " LIMIT ?"
            params.append(filters['limit'])
        
        return self.execute_query(sql, tuple(params))
    
    def get_panel_data_by_vcoptimize_object_name(self, vcoptimize_object_name: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据优化对象名称获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE vcoptimize_object_name = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcoptimize_object_name, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE vcoptimize_object_name = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcoptimize_object_name,))
    
    def get_panel_data_by_vcisvail(self, vcisvail: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据vcisvail获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE vcisvail = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcisvail, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE vcisvail = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcisvail,))
    
    def get_panel_data_by_vcmeasure_code(self, vcmeasure_code: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据vcmeasure_code获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE vcmeasure_code = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcmeasure_code, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE vcmeasure_code = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (vcmeasure_code,))
    
    def get_panel_data_by_current_act_name(self, current_act_name: str, batch_id: str = None) -> List[Dict[str, Any]]:
        """根据current_act_name获取面板数据"""
        if batch_id:
            sql = "SELECT * FROM panel_data WHERE current_act_name = ? AND import_batch_id = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (current_act_name, batch_id))
        else:
            sql = "SELECT * FROM panel_data WHERE current_act_name = ? ORDER BY city, grid_code"
            return self.execute_query(sql, (current_act_name,))
    
    def get_available_vcoptimize_object_names(self) -> List[str]:
        """获取可用的优化对象名称列表"""
        try:
            sql = """SELECT DISTINCT vcoptimize_object_name 
                     FROM panel_data 
                     WHERE vcoptimize_object_name IS NOT NULL 
                     AND vcoptimize_object_name != '' 
                     ORDER BY vcoptimize_object_name"""
            results = self.execute_query(sql)
            return [row['vcoptimize_object_name'] for row in results]
        except (sqlite3.Error, KeyError) as e:
            self.logger.warning(f"获取优化对象名称失败: {e}")
            return []
    
    def get_available_vcisvail_values(self) -> List[str]:
        """获取可用的vcisvail值列表"""
        try:
            sql = """SELECT DISTINCT vcisvail 
                     FROM panel_data 
                     WHERE vcisvail IS NOT NULL 
                     AND vcisvail != '' 
                     ORDER BY vcisvail"""
            results = self.execute_query(sql)
            return [row['vcisvail'] for row in results]
        except (sqlite3.Error, KeyError) as e:
            self.logger.warning(f"获取vcisvail值失败: {e}")
            return []
    
    def get_available_vcmeasure_codes(self) -> List[str]:
        """获取可用的vcmeasure_code列表"""
        try:
            sql = """SELECT DISTINCT vcmeasure_code 
                     FROM panel_data 
                     WHERE vcmeasure_code IS NOT NULL 
                     AND vcmeasure_code != '' 
                     ORDER BY vcmeasure_code"""
            results = self.execute_query(sql)
            return [row['vcmeasure_code'] for row in results]
        except (sqlite3.Error, KeyError) as e:
            self.logger.warning(f"获取vcmeasure_code失败: {e}")
            return []
    
    def get_available_current_act_names(self) -> List[str]:
        """获取可用的current_act_name列表"""
        try:
            sql = """SELECT DISTINCT current_act_name 
                     FROM panel_data 
                     WHERE current_act_name IS NOT NULL 
                     AND current_act_name != '' 
                     ORDER BY current_act_name"""
            results = self.execute_query(sql)
            return [row['current_act_name'] for row in results]
        except (sqlite3.Error, KeyError) as e:
            self.logger.warning(f"获取current_act_name失败: {e}")
            return []
    
    def insert_grid_result_scores(self, data_list: List[Dict[str, Any]]) -> tuple:
        """
        批量插入网格结果得分数据
        
        Args:
            data_list: 数据列表，每个字典包含网格结果得分的字段
            
        Returns:
            tuple: (成功插入/更新的记录数, 更新的记录数)
        """
        if not data_list:
            return 0, 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                insert_count = 0
                update_count = 0
                
                for data in data_list:
                    try:
                        # 使用 INSERT OR REPLACE 处理唯一约束（时间+网格ID）
                        sql = '''
                        INSERT OR REPLACE INTO grid_result_scores 
                        (time_period, grid_code, province, grid_name, scene_detail, scene_merged,
                         city, city_district, city_company, scene_area_attribute, group_name,
                         supervise_label_2025, final_score, complaint_count, daily_max_rrc_users,
                         grid_result_data_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+8 hours'))
                        '''
                        
                        params = (
                            data.get('time_period'),
                            data.get('grid_code'),
                            data.get('province'),
                            data.get('grid_name'),
                            data.get('scene_detail'),
                            data.get('scene_merged'),
                            data.get('city'),
                            data.get('city_district'),
                            data.get('city_company'),
                            data.get('scene_area_attribute'),
                            data.get('group_name'),
                            data.get('supervise_label_2025'),
                            data.get('final_score'),
                            data.get('complaint_count'),
                            data.get('daily_max_rrc_users'),
                            data.get('grid_result_data_json')
                        )
                        
                        # 检查记录是否已存在
                        check_sql = "SELECT id FROM grid_result_scores WHERE time_period = ? AND grid_code = ?"
                        cursor.execute(check_sql, (data.get('time_period'), data.get('grid_code')))
                        existing = cursor.fetchone()
                        
                        cursor.execute(sql, params)
                        
                        if existing:
                            update_count += 1
                        else:
                            insert_count += 1
                            
                    except sqlite3.IntegrityError as e:
                        # 唯一约束冲突，使用更新
                        self.logger.warning(f"记录已存在，执行更新: {str(e)}")
                        try:
                            update_sql = '''
                            UPDATE grid_result_scores SET
                                province = ?, grid_name = ?, scene_detail = ?, scene_merged = ?,
                                city = ?, city_district = ?, city_company = ?, scene_area_attribute = ?,
                                group_name = ?, supervise_label_2025 = ?, final_score = ?,
                                complaint_count = ?, daily_max_rrc_users = ?, grid_result_data_json = ?,
                                updated_at = datetime('now', '+8 hours')
                            WHERE time_period = ? AND grid_code = ?
                            '''
                            update_params = (
                                data.get('province'),
                                data.get('grid_name'),
                                data.get('scene_detail'),
                                data.get('scene_merged'),
                                data.get('city'),
                                data.get('city_district'),
                                data.get('city_company'),
                                data.get('scene_area_attribute'),
                                data.get('group_name'),
                                data.get('supervise_label_2025'),
                                data.get('final_score'),
                                data.get('complaint_count'),
                                data.get('daily_max_rrc_users'),
                                data.get('grid_result_data_json'),
                                data.get('time_period'),
                                data.get('grid_code')
                            )
                            cursor.execute(update_sql, update_params)
                            update_count += 1
                        except Exception as e2:
                            self.logger.error(f"更新记录失败: {str(e2)}")
                    except Exception as e:
                        self.logger.error(f"插入记录失败: {str(e)}")
                        continue
                
                conn.commit()
                return insert_count + update_count, update_count
                
        except Exception as e:
            self.logger.error(f"批量插入网格结果得分数据失败: {str(e)}")
            return 0, 0
    
    def get_grid_result_score(self, grid_code: str, time_period: str = None) -> Optional[Dict[str, Any]]:
        """
        获取网格结果得分数据
        
        Args:
            grid_code: 网格ID
            time_period: 时间周期，如果为None则获取最新的一条
            
        Returns:
            网格结果得分数据字典，如果不存在返回None
        """
        try:
            if time_period:
                sql = "SELECT * FROM grid_result_scores WHERE grid_code = ? AND time_period = ? ORDER BY updated_at DESC LIMIT 1"
                results = self.execute_query(sql, (grid_code, time_period))
            else:
                sql = "SELECT * FROM grid_result_scores WHERE grid_code = ? ORDER BY updated_at DESC LIMIT 1"
                results = self.execute_query(sql, (grid_code,))
            
            if results:
                return results[0]
            return None
        except Exception as e:
            self.logger.error(f"获取网格结果得分数据失败: {str(e)}")
            return None
    
    def get_grid_result_scores_by_time(self, time_period: str) -> List[Dict[str, Any]]:
        """
        根据时间周期获取所有网格结果得分数据
        
        Args:
            time_period: 时间周期
            
        Returns:
            网格结果得分数据列表
        """
        try:
            sql = "SELECT * FROM grid_result_scores WHERE time_period = ? ORDER BY grid_code"
            return self.execute_query(sql, (time_period,))
        except Exception as e:
            self.logger.error(f"根据时间周期获取网格结果得分数据失败: {str(e)}")
            return []
    
    def get_available_time_periods(self) -> List[str]:
        """获取可用的时间周期列表"""
        try:
            sql = "SELECT DISTINCT time_period FROM grid_result_scores ORDER BY time_period DESC"
            results = self.execute_query(sql)
            return [row['time_period'] for row in results]
        except Exception as e:
            self.logger.error(f"获取可用时间周期列表失败: {str(e)}")
            return []

    # 字段映射支持方法
    def add_grid_field_with_mapping(self, english_field_name: str, data_dict: dict):
        """
        使用英文字段名添加网格字段数据
        
        Args:
            english_field_name: 英文字段名
            data_dict: 包含CGI和字段值的字典
        """
        try:
            # 转换为中文字段名
            chinese_field_name = GRID_FIELD_REVERSE_MAPPING.get(english_field_name)
            
            # 验证字段名有效性
            if chinese_field_name is None:
                self.logger.warning(f"无效的英文字段名: {english_field_name}")
                return
            
            # 构建SQL更新语句
            sql = f"UPDATE engineering_params SET {chinese_field_name} = ? WHERE cgi = ?"
            
            # 批量更新数据
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for cgi, value in data_dict.items():
                    cursor.execute(sql, (value, cgi))
                conn.commit()
                
            self.logger.info(f"成功更新字段 {english_field_name} -> {chinese_field_name}")
            
        except Exception as e:
            self.logger.error(f"添加网格字段数据失败: {e}")
            raise

    def get_grid_field_with_mapping(self, english_field_name: str, cgi_list: List[str] = None) -> dict:
        """
        使用英文字段名获取网格字段数据
        
        Args:
            english_field_name: 英文字段名
            cgi_list: CGI列表，为空则获取所有
            
        Returns:
            dict: {cgi: field_value} 的字典
        """
        try:
            # 转换为中文字段名
            chinese_field_name = GRID_FIELD_REVERSE_MAPPING.get(english_field_name)
            
            # 验证字段名有效性
            if chinese_field_name is None:
                self.logger.warning(f"无效的英文字段名: {english_field_name}")
                return {}
            
            # 构建SQL查询语句
            if cgi_list:
                placeholders = ','.join(['?' for _ in cgi_list])
                sql = f"SELECT cgi, {chinese_field_name} FROM engineering_params WHERE cgi IN ({placeholders})"
                results = self.execute_query(sql, tuple(cgi_list))
            else:
                sql = f"SELECT cgi, {chinese_field_name} FROM engineering_params WHERE {chinese_field_name} IS NOT NULL"
                results = self.execute_query(sql)
            
            # 构建返回字典
            return {row['cgi']: row[chinese_field_name] for row in results}
            
        except Exception as e:
            self.logger.error(f"获取网格字段数据失败: {e}")
            return {}

    def update_grid_fields_batch_with_mapping(self, field_data: dict):
        """
        批量更新多个网格字段（使用英文字段名）
        
        Args:
            field_data: {english_field_name: {cgi: value}} 的嵌套字典
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for english_field, cgi_values in field_data.items():
                    # 转换为中文字段名
                    chinese_field = GRID_FIELD_REVERSE_MAPPING.get(english_field)
                    
                    # 验证字段名
                    if chinese_field is None:
                        self.logger.warning(f"跳过无效字段: {english_field}")
                        continue
                    
                    # 批量更新
                    sql = f"UPDATE engineering_params SET {chinese_field} = ? WHERE cgi = ?"
                    for cgi, value in cgi_values.items():
                        cursor.execute(sql, (value, cgi))
                
                conn.commit()
                self.logger.info(f"批量更新完成，涉及字段: {list(field_data.keys())}")
                
        except Exception as e:
            self.logger.error(f"批量更新网格字段失败: {e}")
            raise

    def get_all_grid_fields_with_mapping(self, cgi: str) -> dict:
        """
        获取指定CGI的所有网格字段（返回英文字段名）
        
        Args:
            cgi: 小区CGI
            
        Returns:
            dict: {english_field_name: value} 的字典
        """
        try:
            # 获取所有网格字段的中文名
            chinese_fields = list(GRID_FIELD_MAPPING.keys())
            field_list = ','.join(chinese_fields)
            
            sql = f"SELECT {field_list} FROM engineering_params WHERE cgi = ?"
            results = self.execute_query(sql, (cgi,))
            
            if not results:
                return {}
            
            row = results[0]
            # 转换为英文字段名
            english_data = {}
            for chinese_field in chinese_fields:
                english_field = GRID_FIELD_MAPPING.get(chinese_field)
                if row[chinese_field] is not None:
                    english_data[english_field] = row[chinese_field]
            
            return english_data
            
        except Exception as e:
            self.logger.error(f"获取CGI网格字段失败: {e}")
            return {}

    def migrate_chinese_fields_to_english(self) -> bool:
        """
        数据迁移：将中文字段数据迁移到对应的英文字段
        
        Returns:
            bool: 迁移是否成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. 检查表结构，确保英文字段存在
                cursor.execute("PRAGMA table_info(engineering_params)")
                existing_columns = [row[1] for row in cursor.fetchall()]
                
                # 2. 添加缺失的英文字段
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    if english_field not in existing_columns:
                        try:
                            sql = f"ALTER TABLE engineering_params ADD COLUMN {english_field} TEXT"
                            cursor.execute(sql)
                            self.logger.info(f"添加英文字段: {english_field}")
                        except sqlite3.OperationalError as e:
                            self.logger.warning(f"添加英文字段失败 {english_field}: {e}")
                
                # 3. 重新获取表结构（包含新添加的英文字段）
                cursor.execute("PRAGMA table_info(engineering_params)")
                updated_columns = [row[1] for row in cursor.fetchall()]
                
                # 4. 数据迁移：将中文字段的数据复制到英文字段
                migration_count = 0
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    if chinese_field in updated_columns and english_field in updated_columns:
                        try:
                            # 复制非空数据到英文字段
                            sql = f"""
                            UPDATE engineering_params 
                            SET {english_field} = {chinese_field} 
                            WHERE {chinese_field} IS NOT NULL 
                            AND {chinese_field} != ''
                            AND ({english_field} IS NULL OR {english_field} = '')
                            """
                            cursor.execute(sql)
                            affected_rows = cursor.rowcount
                            if affected_rows > 0:
                                migration_count += affected_rows
                                self.logger.info(f"迁移字段 {chinese_field} -> {english_field}: {affected_rows} 条记录")
                        except Exception as e:
                            self.logger.error(f"迁移字段失败 {chinese_field} -> {english_field}: {e}")
                
                conn.commit()
                self.logger.info(f"字段迁移完成，共迁移 {migration_count} 条记录")
                return True
                
        except Exception as e:
            self.logger.error(f"字段迁移失败: {e}")
            return False

    def get_field_name(self, field_key: str, prefer_english: bool = True) -> str:
        """
        获取字段名（支持中英文映射）
        
        Args:
            field_key: 字段键（可以是中文或英文）
            prefer_english: 是否优先返回英文字段名
            
        Returns:
            str: 实际的字段名
        """
        # 如果是中文字段且需要英文字段
        if field_key in GRID_FIELD_MAPPING and prefer_english:
            return GRID_FIELD_MAPPING[field_key]
        
        # 如果是英文字段且需要中文字段
        if field_key in GRID_FIELD_REVERSE_MAPPING and not prefer_english:
            return GRID_FIELD_REVERSE_MAPPING[field_key]
        
        # 返回原字段名
        return field_key

    def get_grid_data_with_mapping(self, cgi: str, use_english_fields: bool = True) -> dict:
        """
        获取网格数据（支持字段映射）
        
        Args:
            cgi: 小区CGI
            use_english_fields: 是否使用英文字段名返回
            
        Returns:
            dict: 网格数据
        """
        try:
            # 构建查询字段列表（优先使用英文字段，回退到中文字段）
            select_fields = []
            field_mapping = {}
            
            for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                if use_english_fields:
                    select_fields.append(f"COALESCE({english_field}, {chinese_field}) as {english_field}")
                    field_mapping[english_field] = english_field
                else:
                    select_fields.append(f"COALESCE({english_field}, {chinese_field}) as {chinese_field}")
                    field_mapping[chinese_field] = chinese_field
            
            if not select_fields:
                return {}
            
            sql = f"SELECT {', '.join(select_fields)} FROM engineering_params WHERE cgi = ?"
            results = self.execute_query(sql, (cgi,))
            
            return results[0] if results else {}
            
        except Exception as e:
            self.logger.error(f"获取网格数据失败: {e}")
            return {}

    def update_grid_field_with_mapping(self, cgi: str, field_key: str, value: str, update_both: bool = True) -> bool:
        """
        更新网格字段（支持字段映射）
        
        Args:
            cgi: 小区CGI
            field_key: 字段键（中文或英文）
            value: 字段值
            update_both: 是否同时更新中英文字段
            
        Returns:
            bool: 更新是否成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 确定要更新的字段
                fields_to_update = []
                
                if field_key in GRID_FIELD_MAPPING:
                    # 中文字段
                    fields_to_update.append(field_key)
                    if update_both:
                        fields_to_update.append(GRID_FIELD_MAPPING[field_key])
                elif field_key in GRID_FIELD_REVERSE_MAPPING:
                    # 英文字段
                    fields_to_update.append(field_key)
                    if update_both:
                        fields_to_update.append(GRID_FIELD_REVERSE_MAPPING[field_key])
                else:
                    # 普通字段
                    fields_to_update.append(field_key)
                
                # 执行更新
                for field_name in fields_to_update:
                    if field_name in ALLOWED_GRID_COLUMNS:
                        sql = f"UPDATE engineering_params SET {field_name} = ? WHERE cgi = ?"
                        cursor.execute(sql, (value, cgi))
                
                conn.commit()
                self.logger.info(f"更新字段成功: {field_key} = {value} (CGI: {cgi})")
                return True
                
        except Exception as e:
            self.logger.error(f"更新字段失败: {e}")
            return False


# 全局数据库管理器实例
db_manager = DatabaseManager()
