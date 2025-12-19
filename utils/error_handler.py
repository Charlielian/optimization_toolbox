# -*- coding: utf-8 -*-
"""
错误处理工具模块
提供统一的错误处理机制和用户友好的错误提示
"""

import logging
import traceback
from typing import Any, Callable, Dict, Optional, Tuple

import streamlit as st


class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def handle_database_error(self, error: Exception, operation: str, 
                            details: Optional[Dict[str, Any]] = None) -> None:
        """处理数据库相关错误"""
        error_msg = f"数据库操作失败: {operation}"
        
        if "no such table" in str(error):
            error_msg += " - 数据表不存在，请检查数据库架构"
        elif "UNIQUE constraint failed" in str(error):
            error_msg += " - 数据重复，请检查唯一性约束"
        elif "FOREIGN KEY constraint failed" in str(error):
            error_msg += " - 外键约束失败，请检查关联数据"
        elif "database is locked" in str(error):
            error_msg += " - 数据库被锁定，请稍后重试"
        else:
            error_msg += f" - {str(error)}"
        
        self.logger.error(f"{error_msg}: {traceback.format_exc()}")
        st.error(error_msg)
        
        if details:
            with st.expander("错误详情"):
                st.json(details)
    
    def handle_file_error(self, error: Exception, filename: str, 
                         operation: str) -> None:
        """处理文件相关错误"""
        error_msg = f"文件操作失败: {filename} - {operation}"
        
        if "Permission denied" in str(error):
            error_msg += " - 文件权限不足，请检查文件访问权限"
        elif "No such file or directory" in str(error):
            error_msg += " - 文件不存在，请检查文件路径"
        elif "Invalid file format" in str(error):
            error_msg += " - 文件格式无效，请检查文件类型"
        else:
            error_msg += f" - {str(error)}"
        
        self.logger.error(f"{error_msg}: {traceback.format_exc()}")
        st.error(error_msg)
    
    def handle_import_error(self, error: Exception, filename: str, 
                           row_number: Optional[int] = None) -> None:
        """处理数据导入错误"""
        error_msg = f"数据导入失败: {filename}"
        
        if row_number:
            error_msg += f" (第 {row_number} 行)"
        
        if "KeyError" in str(type(error)):
            error_msg += " - 缺少必要的列，请检查文件格式"
        elif "ValueError" in str(type(error)):
            error_msg += " - 数据格式错误，请检查数据类型"
        elif "TypeError" in str(type(error)):
            error_msg += " - 数据类型不匹配，请检查数据格式"
        else:
            error_msg += f" - {str(error)}"
        
        self.logger.error(f"{error_msg}: {traceback.format_exc()}")
        st.error(error_msg)
    
    def handle_validation_error(self, error: Exception, field: str, 
                              value: Any) -> None:
        """处理数据验证错误"""
        error_msg = f"数据验证失败: 字段 '{field}' 的值 '{value}' 无效"
        
        if "required" in str(error).lower():
            error_msg += " - 该字段为必填项"
        elif "format" in str(error).lower():
            error_msg += " - 数据格式不正确"
        elif "range" in str(error).lower():
            error_msg += " - 数据超出允许范围"
        else:
            error_msg += f" - {str(error)}"
        
        self.logger.error(f"{error_msg}: {traceback.format_exc()}")
        st.error(error_msg)
    
    def safe_execute(self, func: Callable, *args, **kwargs) -> Tuple[bool, Any]:
        """安全执行函数，返回执行结果和状态"""
        try:
            result = func(*args, **kwargs)
            return True, result
        except Exception as e:
            self.logger.error(f"函数执行失败 {func.__name__}: {e}")
            self.logger.error(f"异常详情: {traceback.format_exc()}")
            return False, e
    
    def show_user_friendly_error(self, error: Exception, 
                                context: str = "操作") -> None:
        """显示用户友好的错误信息"""
        error_type = type(error).__name__
        
        if error_type == "FileNotFoundError":
            st.error(f"❌ 文件未找到，请检查文件路径是否正确")
        elif error_type == "PermissionError":
            st.error(f"❌ 权限不足，请检查文件访问权限")
        elif error_type == "ValueError":
            st.error(f"❌ 数据格式错误，请检查输入数据")
        elif error_type == "KeyError":
            st.error(f"❌ 缺少必要的数据字段")
        elif error_type == "ConnectionError":
            st.error(f"❌ 连接失败，请检查网络连接")
        elif error_type == "TimeoutError":
            st.error(f"❌ 操作超时，请稍后重试")
        else:
            st.error(f"❌ {context}失败: {str(error)}")
        
        # 在开发模式下显示详细错误信息
        if st.session_state.get('debug_mode', False):
            with st.expander("详细错误信息"):
                st.code(traceback.format_exc())
    
    def log_and_show_error(self, error: Exception, operation: str, 
                          show_to_user: bool = True) -> None:
        """记录错误并显示给用户"""
        self.logger.error(f"{operation}失败: {error}")
        self.logger.error(f"异常详情: {traceback.format_exc()}")
        
        if show_to_user:
            self.show_user_friendly_error(error, operation)


# 全局错误处理器实例
error_handler = ErrorHandler()
