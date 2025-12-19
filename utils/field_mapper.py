#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射工具类
用于处理中英文字段名的转换和映射
"""

from typing import Optional, Dict, List, Set
from database import GRID_FIELD_MAPPING

class FieldMapper:
    """字段映射工具类"""
    
    # 中文字段到英文字段的映射
    FIELD_MAPPING = GRID_FIELD_MAPPING
    
    # 英文字段到中文字段的反向映射
    REVERSE_MAPPING = {v: k for k, v in FIELD_MAPPING.items()}
    
    # 字段描述映射
    FIELD_DESCRIPTIONS = {
        'grid_id_no_buffer': '网格ID（不缓冲）',
        'grid_name_no_buffer': '网格名称（不缓冲）',
        'grid_label_no_buffer': '网格标签（不缓冲）',
        'grid_id_buffer_500m': '网格ID（500米缓冲）',
        'grid_name_buffer_500m': '网格名称（500米缓冲）',
        'grid_label_buffer_500m': '网格标签（500米缓冲）'
    }
    
    @classmethod
    def chinese_to_english(cls, chinese_field: str) -> Optional[str]:
        """
        将中文字段名转换为英文字段名
        
        Args:
            chinese_field: 中文字段名
            
        Returns:
            Optional[str]: 对应的英文字段名，如果不存在则返回None
        """
        return cls.FIELD_MAPPING.get(chinese_field)
    
    @classmethod
    def english_to_chinese(cls, english_field: str) -> Optional[str]:
        """
        将英文字段名转换为中文字段名
        
        Args:
            english_field: 英文字段名
            
        Returns:
            Optional[str]: 对应的中文字段名，如果不存在则返回None
        """
        return cls.REVERSE_MAPPING.get(english_field)
    
    @classmethod
    def get_field_description(cls, field_name: str) -> str:
        """
        获取字段描述
        
        Args:
            field_name: 字段名（中文或英文）
            
        Returns:
            str: 字段描述
        """
        # 如果是英文字段，直接返回描述
        if field_name in cls.FIELD_DESCRIPTIONS:
            return cls.FIELD_DESCRIPTIONS[field_name]
        
        # 如果是中文字段，转换为英文后获取描述
        english_field = cls.chinese_to_english(field_name)
        if english_field and english_field in cls.FIELD_DESCRIPTIONS:
            return cls.FIELD_DESCRIPTIONS[english_field]
        
        # 如果都没有，返回字段名本身
        return field_name
    
    @classmethod
    def is_grid_field(cls, field_name: str) -> bool:
        """
        检查是否为网格字段
        
        Args:
            field_name: 字段名
            
        Returns:
            bool: 是否为网格字段
        """
        return (field_name in cls.FIELD_MAPPING or 
                field_name in cls.REVERSE_MAPPING)
    
    @classmethod
    def is_valid_chinese_field(cls, field_name: str) -> bool:
        """
        检查是否为有效的中文字段名
        
        Args:
            field_name: 字段名
            
        Returns:
            bool: 是否为有效的中文字段名
        """
        return field_name in cls.FIELD_MAPPING
    
    @classmethod
    def is_valid_english_field(cls, field_name: str) -> bool:
        """
        检查是否为有效的英文字段名
        
        Args:
            field_name: 字段名
            
        Returns:
            bool: 是否为有效的英文字段名
        """
        return field_name in cls.REVERSE_MAPPING
    
    @classmethod
    def get_all_chinese_fields(cls) -> List[str]:
        """
        获取所有中文字段名
        
        Returns:
            List[str]: 中文字段名列表
        """
        return list(cls.FIELD_MAPPING.keys())
    
    @classmethod
    def get_all_english_fields(cls) -> List[str]:
        """
        获取所有英文字段名
        
        Returns:
            List[str]: 英文字段名列表
        """
        return list(cls.REVERSE_MAPPING.keys())
    
    @classmethod
    def get_mapping_pairs(cls) -> List[tuple]:
        """
        获取所有映射对
        
        Returns:
            List[tuple]: (中文字段名, 英文字段名) 的元组列表
        """
        return list(cls.FIELD_MAPPING.items())
    
    @classmethod
    def convert_dict_keys(cls, data: Dict[str, any], to_english: bool = True) -> Dict[str, any]:
        """
        转换字典的键名（中文<->英文）
        
        Args:
            data: 原始数据字典
            to_english: True表示转换为英文键名，False表示转换为中文键名
            
        Returns:
            Dict[str, any]: 转换后的字典
        """
        if not data:
            return {}
        
        converted_data = {}
        
        for key, value in data.items():
            if to_english:
                # 转换为英文键名
                new_key = cls.chinese_to_english(key) or key
            else:
                # 转换为中文键名
                new_key = cls.english_to_chinese(key) or key
            
            converted_data[new_key] = value
        
        return converted_data
    
    @classmethod
    def get_preferred_field_name(cls, field_name: str, prefer_english: bool = True) -> str:
        """
        获取首选的字段名
        
        Args:
            field_name: 原字段名
            prefer_english: 是否优先使用英文字段名
            
        Returns:
            str: 首选的字段名
        """
        if prefer_english:
            # 优先使用英文字段名
            if field_name in cls.FIELD_MAPPING:
                return cls.FIELD_MAPPING[field_name]
            return field_name
        else:
            # 优先使用中文字段名
            if field_name in cls.REVERSE_MAPPING:
                return cls.REVERSE_MAPPING[field_name]
            return field_name
    
    @classmethod
    def validate_field_mapping(cls) -> Dict[str, bool]:
        """
        验证字段映射的完整性
        
        Returns:
            Dict[str, bool]: 验证结果
        """
        results = {
            'mapping_complete': True,
            'reverse_mapping_complete': True,
            'descriptions_complete': True,
            'no_conflicts': True
        }
        
        # 检查映射完整性
        for chinese_field, english_field in cls.FIELD_MAPPING.items():
            if english_field not in cls.REVERSE_MAPPING:
                results['mapping_complete'] = False
                break
        
        # 检查反向映射完整性
        for english_field, chinese_field in cls.REVERSE_MAPPING.items():
            if chinese_field not in cls.FIELD_MAPPING:
                results['reverse_mapping_complete'] = False
                break
        
        # 检查描述完整性
        for english_field in cls.REVERSE_MAPPING.keys():
            if english_field not in cls.FIELD_DESCRIPTIONS:
                results['descriptions_complete'] = False
                break
        
        # 检查冲突
        if len(cls.FIELD_MAPPING) != len(cls.REVERSE_MAPPING):
            results['no_conflicts'] = False
        
        return results
