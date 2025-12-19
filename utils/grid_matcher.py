# -*- coding: utf-8 -*-
"""
网格匹配工具模块
根据小区经纬度匹配网格数据（不缓冲和缓冲500米）
"""

import os
import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import transform
from functools import partial
import pyproj
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class GridMatcher:
    """网格匹配器"""
    
    def __init__(self, grid_file_path: str = None):
        """
        初始化网格匹配器
        
        Args:
            grid_file_path: 网格gpkg文件路径，默认为项目根目录下的网格/网格_yj.gpkg
        """
        if grid_file_path is None:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            grid_file_path = os.path.join(current_dir, '网格', '网格_yj.gpkg')
        
        self.grid_file_path = grid_file_path
        self.grid_gdf = None
        self.grid_gdf_buffered = None  # 缓冲500米后的网格数据
        
        # 网格字段映射（根据实际gpkg文件字段调整）
        # 如果字段名不对，需要根据实际文件调整
        self.grid_id_field = '序号'  # 网格ID字段
        self.grid_name_field = '中文名'  # 网格名称字段
        self.grid_label_field = 'ABC网格'  # 网格标签字段（不再使用，改为从标签匹配文件读取）
        
        # 标签匹配字典：{网格ID: 网格标签}
        self.label_mapping = {}
        
        # 加载网格数据
        self._load_grid_data()
        # 加载标签匹配数据
        self._load_label_mapping()
    
    def _load_grid_data(self):
        """加载网格数据"""
        try:
            if not os.path.exists(self.grid_file_path):
                logger.warning(f"网格文件不存在: {self.grid_file_path}")
                return
            
            # 读取网格数据
            self.grid_gdf = gpd.read_file(self.grid_file_path)
            logger.info(f"成功加载网格数据: {len(self.grid_gdf)} 个网格")
            
            # 检查必要的字段
            required_fields = [self.grid_id_field, self.grid_name_field, self.grid_label_field]
            missing_fields = [f for f in required_fields if f not in self.grid_gdf.columns]
            if missing_fields:
                logger.warning(f"网格文件缺少字段: {missing_fields}")
                logger.info(f"可用字段: {list(self.grid_gdf.columns)}")
                # 尝试使用备用字段
                if '场景' in self.grid_gdf.columns and self.grid_label_field not in self.grid_gdf.columns:
                    self.grid_label_field = '场景'
            
            # 确保坐标系是WGS84（EPSG:4326）或可以转换
            if self.grid_gdf.crs is None:
                logger.warning("网格数据没有坐标系信息，假设为WGS84")
                self.grid_gdf.set_crs('EPSG:4326', inplace=True)
            
            # 创建缓冲500米的网格数据
            self._create_buffered_grids()
            
        except Exception as e:
            logger.error(f"加载网格数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _create_buffered_grids(self):
        """创建缓冲500米的网格数据"""
        try:
            if self.grid_gdf is None or len(self.grid_gdf) == 0:
                return
            
            # 复制网格数据
            self.grid_gdf_buffered = self.grid_gdf.copy()
            
            # 获取当前坐标系
            crs = self.grid_gdf.crs
            
            # 如果是地理坐标系（如WGS84），需要转换为投影坐标系进行缓冲
            if crs and crs.is_geographic:
                # 使用UTM投影（中国地区常用EPSG:32650，但这里使用适合阳江的投影）
                # 阳江大约在112°E，22°N，使用UTM Zone 49N (EPSG:32649)
                target_crs = 'EPSG:32649'  # UTM Zone 49N
                
                # 转换到投影坐标系
                grid_projected = self.grid_gdf.to_crs(target_crs)
                
                # 缓冲500米
                grid_buffered = grid_projected.copy()
                grid_buffered['geometry'] = grid_projected.geometry.buffer(500)  # 500米
                
                # 转换回WGS84
                self.grid_gdf_buffered['geometry'] = grid_buffered.to_crs('EPSG:4326').geometry
            else:
                # 如果已经是投影坐标系，直接缓冲
                # 假设单位是米
                self.grid_gdf_buffered['geometry'] = self.grid_gdf.geometry.buffer(500)
            
            logger.info("成功创建缓冲500米的网格数据")
            
        except Exception as e:
            logger.error(f"创建缓冲网格数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 如果失败，使用原始网格数据
            self.grid_gdf_buffered = self.grid_gdf.copy()
    
    def _load_label_mapping(self):
        """加载标签匹配文件"""
        try:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            label_file_path = os.path.join(current_dir, '标签匹配', '标签匹配.xlsx')
            
            if not os.path.exists(label_file_path):
                logger.warning(f"标签匹配文件不存在: {label_file_path}")
                return
            
            # 读取Excel文件
            df = pd.read_excel(label_file_path)
            logger.info(f"成功加载标签匹配文件: {len(df)} 条记录")
            
            # 使用确切的列名
            grid_id_col = '微网格id'  # 网格ID列
            label_col = '类型'  # 标签列
            
            # 检查列是否存在
            if grid_id_col not in df.columns:
                logger.warning(f"标签匹配文件缺少列 '{grid_id_col}'，可用列: {list(df.columns)}")
                return
            if label_col not in df.columns:
                logger.warning(f"标签匹配文件缺少列 '{label_col}'，可用列: {list(df.columns)}")
                return
            
            # 构建标签映射字典
            self.label_mapping = {}
            for idx, row in df.iterrows():
                grid_id = str(row.get(grid_id_col, '')).strip()
                label = str(row.get(label_col, '')).strip()
                
                if grid_id and label:
                    # 支持一个网格ID对应多个标签（用逗号分隔）
                    if grid_id in self.label_mapping:
                        # 如果已存在，用逗号连接
                        existing_labels = self.label_mapping[grid_id].split(',')
                        if label not in existing_labels:
                            self.label_mapping[grid_id] = ','.join(existing_labels + [label])
                    else:
                        self.label_mapping[grid_id] = label
            
            logger.info(f"成功加载标签映射: {len(self.label_mapping)} 个网格ID")
            
        except Exception as e:
            logger.error(f"加载标签匹配文件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def match_point(self, lon: float, lat: float) -> Dict[str, Optional[str]]:
        """
        匹配单个点的网格信息
        
        Args:
            lon: 经度
            lat: 纬度
            
        Returns:
            包含网格信息的字典:
            {
                'grid_id_no_buffer': '网格ID1,网格ID2',  # 不缓冲的网格ID（逗号分隔）
                'grid_name_no_buffer': '网格名1,网格名2',  # 不缓冲的网格名
                'grid_label_no_buffer': '标签1,标签2',  # 不缓冲的网格标签
                'grid_id_buffer_500m': '网格ID1,网格ID2',  # 缓冲500米的网格ID
                'grid_name_buffer_500m': '网格名1,网格名2',  # 缓冲500米的网格名
                'grid_label_buffer_500m': '标签1,标签2'  # 缓冲500米的网格标签
            }
        """
        result = {
            'grid_id_no_buffer': None,
            'grid_name_no_buffer': None,
            'grid_label_no_buffer': None,
            'grid_id_buffer_500m': None,
            'grid_name_buffer_500m': None,
            'grid_label_buffer_500m': None
        }
        
        try:
            # 检查经纬度有效性
            if lon is None or lat is None:
                return result
            
            try:
                lon = float(lon)
                lat = float(lat)
            except (ValueError, TypeError):
                return result
            
            # 检查经纬度范围（中国大致范围）
            if not (70 <= lon <= 140 and 15 <= lat <= 55):
                logger.warning(f"经纬度超出合理范围: ({lon}, {lat})")
                return result
            
            # 创建点
            point = Point(lon, lat)
            
            # 确保点使用正确的坐标系
            if self.grid_gdf is None or len(self.grid_gdf) == 0:
                return result
            
            # 不缓冲匹配
            if self.grid_gdf is not None and len(self.grid_gdf) > 0:
                matched_grids = self.grid_gdf[self.grid_gdf.geometry.contains(point)]
                if len(matched_grids) > 0:
                    grid_ids = []
                    grid_names = []
                    
                    for idx, row in matched_grids.iterrows():
                        grid_id = str(row.get(self.grid_id_field, ''))
                        grid_name = str(row.get(self.grid_name_field, ''))
                        
                        if grid_id:
                            grid_ids.append(grid_id)
                        if grid_name:
                            grid_names.append(grid_name)
                    
                    if grid_ids:
                        result['grid_id_no_buffer'] = ','.join(grid_ids)
                    if grid_names:
                        result['grid_name_no_buffer'] = ','.join(grid_names)
                    
                    # 根据网格ID匹配标签（不缓冲）
                    labels = []
                    for grid_id in grid_ids:
                        if grid_id in self.label_mapping:
                            label = self.label_mapping[grid_id]
                            if label and label not in labels:
                                labels.append(label)
                    if labels:
                        result['grid_label_no_buffer'] = ','.join(labels)
                    else:
                        result['grid_label_no_buffer'] = None
            
            # 缓冲500米匹配（排除不缓冲已匹配的网格）
            if self.grid_gdf_buffered is not None and len(self.grid_gdf_buffered) > 0:
                matched_grids_buffered = self.grid_gdf_buffered[
                    self.grid_gdf_buffered.geometry.contains(point)
                ]
                if len(matched_grids_buffered) > 0:
                    # 获取不缓冲已匹配的网格ID集合
                    no_buffer_grid_ids = set()
                    if result['grid_id_no_buffer']:
                        no_buffer_grid_ids = set(result['grid_id_no_buffer'].split(','))
                    
                    grid_ids = []
                    grid_names = []
                    
                    for idx, row in matched_grids_buffered.iterrows():
                        grid_id = str(row.get(self.grid_id_field, ''))
                        grid_name = str(row.get(self.grid_name_field, ''))
                        
                        # 只包含缓冲500米匹配到但不缓冲未匹配到的网格
                        if grid_id and grid_id not in no_buffer_grid_ids:
                            grid_ids.append(grid_id)
                            if grid_name:
                                grid_names.append(grid_name)
                    
                    if grid_ids:
                        result['grid_id_buffer_500m'] = ','.join(grid_ids)
                    if grid_names:
                        result['grid_name_buffer_500m'] = ','.join(grid_names)
                    
                    # 根据网格ID匹配标签（缓冲500米，排除不缓冲已匹配的）
                    labels = []
                    for grid_id in grid_ids:
                        if grid_id in self.label_mapping:
                            label = self.label_mapping[grid_id]
                            if label and label not in labels:
                                labels.append(label)
                    if labels:
                        result['grid_label_buffer_500m'] = ','.join(labels)
                    else:
                        result['grid_label_buffer_500m'] = None
            
        except Exception as e:
            logger.error(f"匹配点失败 ({lon}, {lat}): {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return result
    
    def match_batch(self, points: List[Tuple[float, float]]) -> List[Dict[str, Optional[str]]]:
        """
        批量匹配多个点
        
        Args:
            points: 点列表，每个点为(lon, lat)元组
            
        Returns:
            匹配结果列表
        """
        results = []
        for lon, lat in points:
            result = self.match_point(lon, lat)
            results.append(result)
        return results
    
    def is_loaded(self) -> bool:
        """检查网格数据是否已加载"""
        return self.grid_gdf is not None and len(self.grid_gdf) > 0

