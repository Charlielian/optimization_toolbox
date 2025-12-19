#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化的POLYGON裁剪工具
解决顶点重叠和边重叠导致的0.0重叠问题
"""

import logging
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point, LineString
from shapely.ops import unary_union
from shapely.wkt import loads as loads_wkt
try:
    from shapely.validation import make_valid
except ImportError:
    def make_valid(geom):
        if geom.is_valid:
            return geom
        return geom.buffer(0)


class OptimizedPolygonClipper:
    """优化的POLYGON裁剪工具类"""
    
    def __init__(self, tolerance=1e-10):
        """
        初始化裁剪工具
        
        Args:
            tolerance: 几何精度容差，用于处理浮点数精度问题
        """
        self.tolerance = tolerance
        self.logger = logging.getLogger(__name__)
    
    def clip_polygons(self, polygon1_wkt, polygon2_wkt, operation='difference'):
        """
        优化的POLYGON裁剪方法
        
        Args:
            polygon1_wkt: 第一个POLYGON的WKT字符串（裁剪边界）
            polygon2_wkt: 第二个POLYGON的WKT字符串（被裁剪对象）
            operation: 裁剪操作类型 ('difference', 'intersection', 'union')
            
        Returns:
            dict: 包含裁剪结果的字典
        """
        try:
            # 解析几何体
            geom1 = self._parse_and_validate_geometry(polygon1_wkt)
            geom2 = self._parse_and_validate_geometry(polygon2_wkt)
            
            if geom1 is None or geom2 is None:
                return {'success': False, 'error': '几何体解析失败'}
            
            # 预处理：优化几何体精度
            geom1_optimized = self._optimize_geometry_precision(geom1)
            geom2_optimized = self._optimize_geometry_precision(geom2)
            
            # 检测并处理特殊情况
            overlap_info = self._analyze_overlap(geom1_optimized, geom2_optimized)
            
            # 根据重叠情况选择最佳裁剪策略
            if overlap_info['has_vertex_overlap'] or overlap_info['has_edge_overlap']:
                result = self._handle_special_overlap(
                    geom1_optimized, geom2_optimized, operation, overlap_info
                )
            else:
                result = self._standard_clip(geom1_optimized, geom2_optimized, operation)
            
            return result
            
        except Exception as e:
            self.logger.error(f"裁剪失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _parse_and_validate_geometry(self, wkt_string):
        """解析并验证几何体"""
        try:
            # 清理WKT字符串
            cleaned_wkt = ' '.join(wkt_string.strip().split())
            geom = loads_wkt(cleaned_wkt)
            
            # 确保几何体有效
            if not geom.is_valid:
                geom = make_valid(geom)
            
            # 统一为单个Polygon
            if isinstance(geom, MultiPolygon):
                geom = unary_union(geom.geoms)
            
            return geom
            
        except Exception as e:
            self.logger.error(f"几何体解析失败: {e}")
            return None
    
    def _optimize_geometry_precision(self, geom):
        """优化几何体精度，减少浮点数精度问题"""
        try:
            # 获取坐标并进行精度优化
            coords = list(geom.exterior.coords)
            optimized_coords = []
            
            for x, y in coords:
                # 使用指定精度进行四舍五入
                precision = 12  # 保留12位小数
                opt_x = round(x, precision)
                opt_y = round(y, precision)
                optimized_coords.append((opt_x, opt_y))
            
            # 移除重复的连续点
            cleaned_coords = [optimized_coords[0]]
            for i in range(1, len(optimized_coords)):
                if (abs(optimized_coords[i][0] - cleaned_coords[-1][0]) > self.tolerance or
                    abs(optimized_coords[i][1] - cleaned_coords[-1][1]) > self.tolerance):
                    cleaned_coords.append(optimized_coords[i])
            
            # 确保多边形闭合
            if cleaned_coords[0] != cleaned_coords[-1]:
                cleaned_coords.append(cleaned_coords[0])
            
            # 创建优化后的多边形
            optimized_geom = Polygon(cleaned_coords)
            
            # 处理内部孔洞（如果有）
            if len(geom.interiors) > 0:
                holes = []
                for interior in geom.interiors:
                    hole_coords = list(interior.coords)
                    opt_hole_coords = [(round(x, precision), round(y, precision)) 
                                     for x, y in hole_coords]
                    holes.append(opt_hole_coords)
                optimized_geom = Polygon(cleaned_coords, holes)
            
            # 确保几何体有效
            if not optimized_geom.is_valid:
                optimized_geom = make_valid(optimized_geom)
            
            return optimized_geom
            
        except Exception as e:
            self.logger.warning(f"几何体精度优化失败，使用原始几何体: {e}")
            return geom
    
    def _analyze_overlap(self, geom1, geom2):
        """分析两个几何体的重叠情况"""
        overlap_info = {
            'has_intersection': False,
            'has_vertex_overlap': False,
            'has_edge_overlap': False,
            'intersection_area': 0.0,
            'vertex_overlaps': [],
            'edge_overlaps': []
        }
        
        try:
            # 基本相交检测
            if geom1.intersects(geom2):
                overlap_info['has_intersection'] = True
                intersection = geom1.intersection(geom2)
                overlap_info['intersection_area'] = intersection.area
                
                # 检测顶点重叠
                vertex_overlaps = self._detect_vertex_overlaps(geom1, geom2)
                if vertex_overlaps:
                    overlap_info['has_vertex_overlap'] = True
                    overlap_info['vertex_overlaps'] = vertex_overlaps
                
                # 检测边重叠
                edge_overlaps = self._detect_edge_overlaps(geom1, geom2)
                if edge_overlaps:
                    overlap_info['has_edge_overlap'] = True
                    overlap_info['edge_overlaps'] = edge_overlaps
            
            return overlap_info
            
        except Exception as e:
            self.logger.error(f"重叠分析失败: {e}")
            return overlap_info
    
    def _detect_vertex_overlaps(self, geom1, geom2):
        """检测顶点重叠"""
        vertex_overlaps = []
        
        try:
            coords1 = list(geom1.exterior.coords)[:-1]  # 排除重复的最后一个点
            coords2 = list(geom2.exterior.coords)[:-1]
            
            for i, (x1, y1) in enumerate(coords1):
                point1 = Point(x1, y1)
                for j, (x2, y2) in enumerate(coords2):
                    # 检查点是否重叠（在容差范围内）
                    if (abs(x1 - x2) <= self.tolerance and 
                        abs(y1 - y2) <= self.tolerance):
                        vertex_overlaps.append({
                            'geom1_vertex_index': i,
                            'geom2_vertex_index': j,
                            'coord': (x1, y1),
                            'distance': ((x1-x2)**2 + (y1-y2)**2)**0.5
                        })
                    
                    # 检查geom1的顶点是否在geom2的边界上
                    elif geom2.boundary.distance(point1) <= self.tolerance:
                        vertex_overlaps.append({
                            'type': 'vertex_on_boundary',
                            'geom1_vertex_index': i,
                            'coord': (x1, y1),
                            'distance_to_boundary': geom2.boundary.distance(point1)
                        })
            
            return vertex_overlaps
            
        except Exception as e:
            self.logger.error(f"顶点重叠检测失败: {e}")
            return []
    
    def _detect_edge_overlaps(self, geom1, geom2):
        """检测边重叠"""
        edge_overlaps = []
        
        try:
            coords1 = list(geom1.exterior.coords)
            coords2 = list(geom2.exterior.coords)
            
            # 检查geom1的每条边与geom2的边界的重叠
            for i in range(len(coords1) - 1):
                edge1 = LineString([coords1[i], coords1[i + 1]])
                
                # 检查这条边与geom2边界的交集
                intersection = edge1.intersection(geom2.boundary)
                
                if not intersection.is_empty:
                    # 如果交集是LineString且长度大于容差，说明有边重叠
                    if isinstance(intersection, LineString) and intersection.length > self.tolerance:
                        edge_overlaps.append({
                            'geom1_edge_index': i,
                            'edge_coords': [coords1[i], coords1[i + 1]],
                            'overlap_length': intersection.length,
                            'overlap_geometry': intersection
                        })
            
            return edge_overlaps
            
        except Exception as e:
            self.logger.error(f"边重叠检测失败: {e}")
            return []
    
    def _handle_special_overlap(self, geom1, geom2, operation, overlap_info):
        """处理特殊重叠情况"""
        try:
            # 对于有顶点或边重叠的情况，使用缓冲区方法
            buffer_distance = self.tolerance * 10  # 使用较小的缓冲区
            
            # 创建微小的负缓冲区来分离重叠的几何体
            geom1_buffered = geom1.buffer(-buffer_distance).buffer(buffer_distance)
            geom2_buffered = geom2.buffer(-buffer_distance).buffer(buffer_distance)
            
            # 确保缓冲后的几何体仍然有效
            if not geom1_buffered.is_valid:
                geom1_buffered = make_valid(geom1_buffered)
            if not geom2_buffered.is_valid:
                geom2_buffered = make_valid(geom2_buffered)
            
            # 如果缓冲后几何体变空，使用原始几何体
            if geom1_buffered.is_empty:
                geom1_buffered = geom1
            if geom2_buffered.is_empty:
                geom2_buffered = geom2
            
            # 执行裁剪操作
            result_geom = self._execute_operation(geom1_buffered, geom2_buffered, operation)
            
            # 后处理：清理结果
            if result_geom and not result_geom.is_empty:
                result_geom = self._post_process_result(result_geom)
            
            return {
                'success': True,
                'result_geometry': result_geom,
                'result_wkt': result_geom.wkt if result_geom and not result_geom.is_empty else None,
                'result_area': result_geom.area if result_geom and not result_geom.is_empty else 0.0,
                'overlap_info': overlap_info,
                'processing_method': 'special_overlap_handling'
            }
            
        except Exception as e:
            self.logger.error(f"特殊重叠处理失败: {e}")
            # 回退到标准方法
            return self._standard_clip(geom1, geom2, operation)
    
    def _standard_clip(self, geom1, geom2, operation):
        """标准裁剪方法"""
        try:
            result_geom = self._execute_operation(geom1, geom2, operation)
            
            if result_geom and not result_geom.is_empty:
                result_geom = self._post_process_result(result_geom)
            
            return {
                'success': True,
                'result_geometry': result_geom,
                'result_wkt': result_geom.wkt if result_geom and not result_geom.is_empty else None,
                'result_area': result_geom.area if result_geom and not result_geom.is_empty else 0.0,
                'processing_method': 'standard_clipping'
            }
            
        except Exception as e:
            self.logger.error(f"标准裁剪失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _execute_operation(self, geom1, geom2, operation):
        """执行几何操作"""
        if operation == 'difference':
            return geom2.difference(geom1)
        elif operation == 'intersection':
            return geom1.intersection(geom2)
        elif operation == 'union':
            return geom1.union(geom2)
        else:
            raise ValueError(f"不支持的操作类型: {operation}")
    
    def _post_process_result(self, result_geom):
        """后处理结果几何体"""
        try:
            # 确保几何体有效
            if not result_geom.is_valid:
                result_geom = make_valid(result_geom)
            
            # 如果是MultiPolygon，尝试合并为单个Polygon
            if isinstance(result_geom, MultiPolygon):
                # 如果只有一个组件，直接返回
                if len(result_geom.geoms) == 1:
                    result_geom = result_geom.geoms[0]
                else:
                    # 多个组件，使用unary_union合并
                    result_geom = unary_union(result_geom.geoms)
                    
                    # 如果合并后还是MultiPolygon，选择面积最大的
                    if isinstance(result_geom, MultiPolygon):
                        largest_geom = max(result_geom.geoms, key=lambda g: g.area)
                        result_geom = largest_geom
            
            # 最终精度优化
            result_geom = self._optimize_geometry_precision(result_geom)
            
            return result_geom
            
        except Exception as e:
            self.logger.error(f"结果后处理失败: {e}")
            return result_geom


def test_optimized_clipper():
    """测试优化的裁剪器"""
    # 你提供的测试数据
    polygon1_wkt = "POLYGON ((111.91148257205967 21.81428867475205, 111.9062586542288 21.814253848633175, 111.90636313258541 21.809413018109908, 111.9095323094028 21.80885580020795, 111.91148257205967 21.81428867475205))"
    polygon2_wkt = "POLYGON ((111.91228357279373 21.812512542689554, 111.91242287726922 21.809796105417504, 111.90998504894814 21.810109540487357, 111.90998515997721 21.810117312522372, 111.91085288741212 21.81253455323389, 111.91228357279373 21.812512542689554))"
    
    # 创建优化的裁剪器
    clipper = OptimizedPolygonClipper(tolerance=1e-12)
    
    # 执行裁剪
    result = clipper.clip_polygons(polygon1_wkt, polygon2_wkt, 'difference')
    
    print("=== 优化裁剪结果 ===")
    print(f"成功: {result['success']}")
    if result['success']:
        print(f"处理方法: {result['processing_method']}")
        print(f"结果面积: {result['result_area']:.12f}")
        if 'overlap_info' in result:
            overlap = result['overlap_info']
            print(f"有相交: {overlap['has_intersection']}")
            print(f"有顶点重叠: {overlap['has_vertex_overlap']}")
            print(f"有边重叠: {overlap['has_edge_overlap']}")
            print(f"相交面积: {overlap['intersection_area']:.12f}")
        
        if result['result_wkt']:
            print(f"结果WKT: {result['result_wkt']}")
    else:
        print(f"错误: {result['error']}")


if __name__ == "__main__":
    test_optimized_clipper()
