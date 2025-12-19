#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段迁移管理工具
用于管理中文字段到英文字段的迁移过程
"""

import logging
import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager, GRID_FIELD_MAPPING
from utils.field_mapper import FieldMapper


class FieldMigrationManager:
    """字段迁移管理器"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        """
        初始化迁移管理器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db_manager = db_manager or DatabaseManager()
        self.logger = logging.getLogger(__name__)
        
    def check_migration_status(self) -> Dict[str, any]:
        """
        检查迁移状态
        
        Returns:
            Dict[str, any]: 迁移状态信息
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取表结构
                cursor.execute("PRAGMA table_info(engineering_params)")
                columns = [row[1] for row in cursor.fetchall()]
                
                status = {
                    'chinese_fields_exist': [],
                    'english_fields_exist': [],
                    'chinese_fields_missing': [],
                    'english_fields_missing': [],
                    'data_migration_needed': [],
                    'migration_complete': True
                }
                
                # 检查字段存在性
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    if chinese_field in columns:
                        status['chinese_fields_exist'].append(chinese_field)
                    else:
                        status['chinese_fields_missing'].append(chinese_field)
                    
                    if english_field in columns:
                        status['english_fields_exist'].append(english_field)
                    else:
                        status['english_fields_missing'].append(english_field)
                        status['migration_complete'] = False
                
                # 检查数据迁移状态
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    if chinese_field in columns and english_field in columns:
                        # 检查是否有数据需要迁移
                        cursor.execute(f"""
                            SELECT COUNT(*) 
                            FROM engineering_params 
                            WHERE {chinese_field} IS NOT NULL 
                            AND {chinese_field} != ''
                            AND ({english_field} IS NULL OR {english_field} = '')
                        """)
                        count = cursor.fetchone()[0]
                        if count > 0:
                            status['data_migration_needed'].append({
                                'chinese_field': chinese_field,
                                'english_field': english_field,
                                'records_count': count
                            })
                            status['migration_complete'] = False
                
                return status
                
        except Exception as e:
            self.logger.error(f"检查迁移状态失败: {e}")
            return {'error': str(e)}
    
    def create_english_fields(self) -> bool:
        """
        创建英文字段
        
        Returns:
            bool: 是否成功
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取现有字段
                cursor.execute("PRAGMA table_info(engineering_params)")
                existing_columns = [row[1] for row in cursor.fetchall()]
                
                created_count = 0
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    if english_field not in existing_columns:
                        try:
                            sql = f"ALTER TABLE engineering_params ADD COLUMN {english_field} TEXT"
                            cursor.execute(sql)
                            created_count += 1
                            self.logger.info(f"创建英文字段: {english_field}")
                        except sqlite3.OperationalError as e:
                            self.logger.error(f"创建英文字段失败 {english_field}: {e}")
                            return False
                
                conn.commit()
                self.logger.info(f"成功创建 {created_count} 个英文字段")
                return True
                
        except Exception as e:
            self.logger.error(f"创建英文字段失败: {e}")
            return False
    
    def migrate_data(self, batch_size: int = 1000) -> bool:
        """
        迁移数据从中文字段到英文字段
        
        Args:
            batch_size: 批处理大小
            
        Returns:
            bool: 是否成功
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                total_migrated = 0
                
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    try:
                        # 批量迁移数据
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
                            total_migrated += affected_rows
                            self.logger.info(f"迁移字段 {chinese_field} -> {english_field}: {affected_rows} 条记录")
                        
                    except Exception as e:
                        self.logger.error(f"迁移字段失败 {chinese_field} -> {english_field}: {e}")
                        return False
                
                conn.commit()
                self.logger.info(f"数据迁移完成，共迁移 {total_migrated} 条记录")
                return True
                
        except Exception as e:
            self.logger.error(f"数据迁移失败: {e}")
            return False
    
    def validate_migration(self) -> Dict[str, any]:
        """
        验证迁移结果
        
        Returns:
            Dict[str, any]: 验证结果
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                validation_results = {
                    'field_pairs': [],
                    'data_consistency': True,
                    'total_records': 0,
                    'migrated_records': 0
                }
                
                # 获取总记录数
                cursor.execute("SELECT COUNT(*) FROM engineering_params")
                validation_results['total_records'] = cursor.fetchone()[0]
                
                for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                    field_result = {
                        'chinese_field': chinese_field,
                        'english_field': english_field,
                        'chinese_non_null_count': 0,
                        'english_non_null_count': 0,
                        'consistent_count': 0,
                        'inconsistent_count': 0
                    }
                    
                    # 统计中文字段非空记录数
                    cursor.execute(f"""
                        SELECT COUNT(*) 
                        FROM engineering_params 
                        WHERE {chinese_field} IS NOT NULL AND {chinese_field} != ''
                    """)
                    field_result['chinese_non_null_count'] = cursor.fetchone()[0]
                    
                    # 统计英文字段非空记录数
                    cursor.execute(f"""
                        SELECT COUNT(*) 
                        FROM engineering_params 
                        WHERE {english_field} IS NOT NULL AND {english_field} != ''
                    """)
                    field_result['english_non_null_count'] = cursor.fetchone()[0]
                    
                    # 统计一致的记录数
                    cursor.execute(f"""
                        SELECT COUNT(*) 
                        FROM engineering_params 
                        WHERE ({chinese_field} IS NULL OR {chinese_field} = '') 
                        AND ({english_field} IS NULL OR {english_field} = '')
                        OR {chinese_field} = {english_field}
                    """)
                    field_result['consistent_count'] = cursor.fetchone()[0]
                    
                    # 统计不一致的记录数
                    field_result['inconsistent_count'] = (
                        validation_results['total_records'] - field_result['consistent_count']
                    )
                    
                    if field_result['inconsistent_count'] > 0:
                        validation_results['data_consistency'] = False
                    
                    validation_results['field_pairs'].append(field_result)
                
                # 统计已迁移记录数
                validation_results['migrated_records'] = sum(
                    pair['english_non_null_count'] for pair in validation_results['field_pairs']
                )
                
                return validation_results
                
        except Exception as e:
            self.logger.error(f"验证迁移失败: {e}")
            return {'error': str(e)}
    
    def generate_migration_report(self) -> str:
        """
        生成迁移报告
        
        Returns:
            str: 迁移报告
        """
        try:
            status = self.check_migration_status()
            validation = self.validate_migration()
            
            report = []
            report.append("=" * 60)
            report.append("字段迁移报告")
            report.append("=" * 60)
            report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report.append("")
            
            # 迁移状态
            report.append("## 迁移状态")
            report.append(f"迁移完成: {'是' if status.get('migration_complete', False) else '否'}")
            report.append(f"中文字段存在: {len(status.get('chinese_fields_exist', []))}")
            report.append(f"英文字段存在: {len(status.get('english_fields_exist', []))}")
            report.append(f"需要迁移的数据: {len(status.get('data_migration_needed', []))}")
            report.append("")
            
            # 字段映射详情
            report.append("## 字段映射详情")
            for chinese_field, english_field in GRID_FIELD_MAPPING.items():
                chinese_exists = chinese_field in status.get('chinese_fields_exist', [])
                english_exists = english_field in status.get('english_fields_exist', [])
                report.append(f"- {chinese_field} -> {english_field}")
                report.append(f"  中文字段: {'存在' if chinese_exists else '缺失'}")
                report.append(f"  英文字段: {'存在' if english_exists else '缺失'}")
            report.append("")
            
            # 数据验证结果
            if 'error' not in validation:
                report.append("## 数据验证结果")
                report.append(f"总记录数: {validation['total_records']:,}")
                report.append(f"数据一致性: {'通过' if validation['data_consistency'] else '失败'}")
                report.append("")
                
                for pair in validation['field_pairs']:
                    report.append(f"### {pair['chinese_field']} -> {pair['english_field']}")
                    report.append(f"  中文字段非空记录: {pair['chinese_non_null_count']:,}")
                    report.append(f"  英文字段非空记录: {pair['english_non_null_count']:,}")
                    report.append(f"  一致记录数: {pair['consistent_count']:,}")
                    report.append(f"  不一致记录数: {pair['inconsistent_count']:,}")
                    report.append("")
            
            report.append("=" * 60)
            
            return "\n".join(report)
            
        except Exception as e:
            self.logger.error(f"生成迁移报告失败: {e}")
            return f"生成报告失败: {e}"
    
    def run_full_migration(self) -> bool:
        """
        执行完整的迁移流程
        
        Returns:
            bool: 是否成功
        """
        try:
            self.logger.info("开始执行完整迁移流程")
            
            # 1. 检查当前状态
            self.logger.info("1. 检查迁移状态...")
            status = self.check_migration_status()
            if 'error' in status:
                self.logger.error(f"检查状态失败: {status['error']}")
                return False
            
            # 2. 创建英文字段
            if status['english_fields_missing']:
                self.logger.info("2. 创建缺失的英文字段...")
                if not self.create_english_fields():
                    self.logger.error("创建英文字段失败")
                    return False
            else:
                self.logger.info("2. 所有英文字段已存在，跳过创建步骤")
            
            # 3. 迁移数据
            if status['data_migration_needed']:
                self.logger.info("3. 迁移数据...")
                if not self.migrate_data():
                    self.logger.error("数据迁移失败")
                    return False
            else:
                self.logger.info("3. 无需迁移数据")
            
            # 4. 验证迁移结果
            self.logger.info("4. 验证迁移结果...")
            validation = self.validate_migration()
            if 'error' in validation:
                self.logger.error(f"验证失败: {validation['error']}")
                return False
            
            if not validation['data_consistency']:
                self.logger.warning("数据一致性检查未通过")
            
            # 5. 生成报告
            self.logger.info("5. 生成迁移报告...")
            report = self.generate_migration_report()
            
            # 保存报告到文件
            report_file = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            self.logger.info(f"迁移完成，报告已保存到: {report_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"完整迁移流程失败: {e}")
            return False


def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建迁移管理器
    migration_manager = FieldMigrationManager()
    
    # 执行迁移
    success = migration_manager.run_full_migration()
    
    if success:
        print("✅ 字段迁移成功完成")
    else:
        print("❌ 字段迁移失败")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
