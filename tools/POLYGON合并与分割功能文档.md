# POLYGON合并与链式分割功能文档

## 📋 功能概述

本文档提供了POLYGON图层合并和链式分割功能的完整实现，包括：
1. **POLYGON合并**：合并多个相交的POLYGON为一个POLYGON
2. **单POLYGON转换**：将单个POLYGON或单组件MULTIPOLYGON转换为单部件POLYGON
3. **POLYGON裁剪**：使用第一个POLYGON裁剪第二个POLYGON，输出不相交部分
4. **批量链式裁剪**：多个POLYGON按顺序链式裁剪

## 📦 依赖库

```python
import logging
import re
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.wkt import loads as loads_wkt

# shapely >= 2.0.0 支持 make_valid
try:
    from shapely.validation import make_valid
except ImportError:
    # 对于旧版本的shapely，使用buffer(0)方法修复无效几何体
    def make_valid(geom):
        if geom.is_valid:
            return geom
        return geom.buffer(0)
```

## 🔧 核心功能实现

### 1. 解析POLYGON数据

```python
def parse_polygons(input_text):
    """
    解析POLYGON和MULTIPOLYGON数据
    
    参数:
        input_text: 字符串，每行一个POLYGON或MULTIPOLYGON（WKT格式）
    
    返回:
        list: Polygon对象列表
    """
    polygons = []
    lines = input_text.strip().split('\n')
    
    # 先尝试整体解析（处理跨行的MULTIPOLYGON）
    try:
        cleaned_text = ' '.join(input_text.split())
        if cleaned_text:
            geom = loads_wkt(cleaned_text)
            if isinstance(geom, MultiPolygon):
                for poly in geom.geoms:
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    polygons.append(poly)
                return polygons
            elif isinstance(geom, Polygon):
                if not geom.is_valid:
                    geom = make_valid(geom)
                polygons.append(geom)
                return polygons
    except Exception:
        pass
    
    # 按行解析
    processed_lines = set()
    
    for line_num, line in enumerate(lines, 1):
        if line_num in processed_lines:
            continue
        
        line = line.strip()
        if not line:
            continue
        
        try:
            geom = loads_wkt(line)
            
            if isinstance(geom, Polygon):
                if not geom.is_valid:
                    geom = make_valid(geom)
                polygons.append(geom)
            
            elif isinstance(geom, MultiPolygon):
                for poly in geom.geoms:
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    polygons.append(poly)
        
        except Exception as e:
            # 尝试提取POLYGON或MULTIPOLYGON字符串
            multipolygon_match = re.search(
                r'MULTIPOLYGON\s*\([^)]+\)', 
                line, 
                re.IGNORECASE | re.DOTALL
            )
            
            if multipolygon_match:
                try:
                    multipolygon_str = multipolygon_match.group(0)
                    geom = loads_wkt(multipolygon_str)
                    if isinstance(geom, MultiPolygon):
                        for poly in geom.geoms:
                            if not poly.is_valid:
                                poly = make_valid(poly)
                            polygons.append(poly)
                except Exception:
                    pass
            else:
                polygon_match = re.search(
                    r'POLYGON\s*\([^)]+\)', 
                    line, 
                    re.IGNORECASE
                )
                if polygon_match:
                    try:
                        polygon_str = polygon_match.group(0)
                        geom = loads_wkt(polygon_str)
                        if isinstance(geom, Polygon):
                            if not geom.is_valid:
                                geom = make_valid(geom)
                            polygons.append(geom)
                    except Exception:
                        pass
    
    return polygons
```

### 2. 检测POLYGON相交

```python
def check_intersections(polygons):
    """
    检测POLYGON之间的相交关系
    
    参数:
        polygons: Polygon对象列表
    
    返回:
        dict: {
            'has_intersection': bool,  # 是否有相交
            'details': list,           # 相交详情列表
            'intersection_pairs': list # 相交的POLYGON对
        }
    """
    has_intersection = False
    details = []
    intersection_pairs = []
    
    if len(polygons) < 2:
        return {
            'has_intersection': False,
            'details': ["至少需要2个POLYGON才能检测相交"]
        }
    
    for i in range(len(polygons)):
        for j in range(i + 1, len(polygons)):
            poly1 = polygons[i]
            poly2 = polygons[j]
            
            if poly1.intersects(poly2):
                has_intersection = True
                intersection_pairs.append((i + 1, j + 1))
                intersection_area = poly1.intersection(poly2).area
                details.append(
                    f"POLYGON {i+1} 与 POLYGON {j+1} 相交（相交面积：{intersection_area:.6f}）"
                )
    
    if not has_intersection:
        details.append(
            f"共检测 {len(polygons)} 个POLYGON，但它们之间没有相交关系"
        )
    
    return {
        'has_intersection': has_intersection,
        'details': details,
        'intersection_pairs': intersection_pairs
    }
```

### 3. 合并POLYGON

```python
def merge_polygons(polygons):
    """
    合并多个POLYGON
    
    参数:
        polygons: Polygon对象列表
    
    返回:
        Polygon: 合并后的POLYGON（单部件）
    """
    if len(polygons) == 0:
        return None
    
    if len(polygons) == 1:
        result = polygons[0]
        if not isinstance(result, Polygon):
            result = result.convex_hull
        return result
    
    # 使用unary_union合并所有POLYGON
    merged = unary_union(polygons)
    
    # 如果结果是MultiPolygon，转换为单个Polygon
    if isinstance(merged, MultiPolygon):
        if len(merged.geoms) > 1:
            # 返回外包络线
            return merged.convex_hull
        else:
            merged = merged.geoms[0]
    
    # 修复无效的几何体
    if not merged.is_valid:
        merged = make_valid(merged)
    
    return merged
```

### 4. 单POLYGON转换为单部件

```python
def convert_to_single_polygon(geom):
    """
    将几何体转换为单部件POLYGON
    
    参数:
        geom: Polygon或MultiPolygon对象
    
    返回:
        Polygon: 单部件POLYGON
    """
    if isinstance(geom, Polygon):
        # 确保有效
        if not geom.is_valid:
            geom = make_valid(geom)
            # 如果修复后变成了MultiPolygon，提取第一个组件
            if isinstance(geom, MultiPolygon):
                if len(geom.geoms) > 0:
                    geom = max(geom.geoms, key=lambda p: p.area)
                else:
                    geom = geom.geoms[0]
        return geom
    
    elif isinstance(geom, MultiPolygon):
        if len(geom.geoms) == 1:
            # 只有一个组件，直接提取
            result = geom.geoms[0]
            if not result.is_valid:
                result = make_valid(result)
            # 确保修复后还是单部件
            if isinstance(result, MultiPolygon):
                result = result.convex_hull
            return result
        else:
            # 多个组件，使用凸包转换为单部件
            return geom.convex_hull
    
    else:
        # 其他类型，使用凸包
        return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
```

### 5. POLYGON裁剪（difference操作）

```python
def clip_polygon(polygon1, polygon2):
    """
    使用第一个POLYGON裁剪第二个POLYGON
    输出：第二个POLYGON中与第一个POLYGON不相交的部分（单部件）
    
    参数:
        polygon1: Polygon对象（裁剪边界）
        polygon2: Polygon对象（被裁剪对象）
    
    返回:
        Polygon: 裁剪后的单部件POLYGON
    """
    # 统一几何体（如果是MULTIPOLYGON，合并为单个几何体）
    geom1 = unify_geometry(polygon1)
    geom2 = unify_geometry(polygon2)
    
    # 检查相交
    if not geom1.intersects(geom2):
        # 不相交，返回原始polygon2
        return convert_to_single_polygon(geom2)
    
    # 执行裁剪：geom2 - geom1
    clipped_result = geom2.difference(geom1)
    
    # 确保结果有效
    if not clipped_result.is_valid:
        clipped_result = make_valid(clipped_result)
    
    # 如果结果为空，返回原始polygon2
    if clipped_result.is_empty:
        return convert_to_single_polygon(geom2)
    
    # 转换为单部件POLYGON
    return convert_to_single_polygon(clipped_result)


def unify_geometry(geom):
    """
    统一几何体：如果是MULTIPOLYGON，合并为单个几何体
    
    参数:
        geom: Polygon或MultiPolygon对象
    
    返回:
        Polygon: 统一的几何体
    """
    if isinstance(geom, MultiPolygon):
        if len(geom.geoms) > 1:
            return unary_union(geom.geoms)
        else:
            return geom.geoms[0]
    elif isinstance(geom, Polygon):
        return geom
    else:
        return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
```

### 6. 批量链式裁剪

```python
def batch_chain_clip(polygon_list):
    """
    批量链式裁剪多个POLYGON
    
    链式裁剪逻辑：
    - 第1个POLYGON：保持不变
    - 第2个POLYGON：裁剪掉与第1个相交的部分
    - 第3个POLYGON：裁剪掉与裁剪后的第2个相交的部分
    - 以此类推...
    
    参数:
        polygon_list: Polygon对象列表
    
    返回:
        list: 裁剪后的POLYGON列表（每个都是单部件POLYGON）
    """
    if len(polygon_list) == 0:
        return []
    
    if len(polygon_list) == 1:
        return [convert_to_single_polygon(polygon_list[0])]
    
    result_polygons = []
    
    # 第一个POLYGON保持不变，但确保是单部件格式
    first_polygon = convert_to_single_polygon(polygon_list[0])
    result_polygons.append(first_polygon)
    
    # 从第二个开始，依次裁剪
    previous_clipped = first_polygon
    
    for i in range(1, len(polygon_list)):
        current_polygon = polygon_list[i]
        
        # 检查是否相交
        if not previous_clipped.intersects(current_polygon):
            # 不相交，保持原样
            clipped_result = convert_to_single_polygon(current_polygon)
        else:
            # 相交，执行裁剪：current - previous_clipped
            clipped_result = current_polygon.difference(previous_clipped)
            
            # 确保结果有效
            if not clipped_result.is_valid:
                clipped_result = make_valid(clipped_result)
            
            # 如果结果为空，使用原始POLYGON（保持数量一致）
            if clipped_result.is_empty:
                clipped_result = convert_to_single_polygon(current_polygon)
            else:
                # 转换为单部件POLYGON
                clipped_result = convert_to_single_polygon(clipped_result)
        
        result_polygons.append(clipped_result)
        
        # 更新previous_clipped为当前裁剪结果
        previous_clipped = clipped_result
    
    return result_polygons
```

## 📝 完整代码示例

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYGON合并与链式分割功能
独立实现版本，不依赖Streamlit
"""

import logging
import re
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.wkt import loads as loads_wkt

try:
    from shapely.validation import make_valid
except ImportError:
    def make_valid(geom):
        if geom.is_valid:
            return geom
        return geom.buffer(0)


class PolygonProcessor:
    """POLYGON处理工具类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_polygons(self, input_text):
        """解析POLYGON数据"""
        polygons = []
        lines = input_text.strip().split('\n')
        processed_lines = set()
        
        for line_num, line in enumerate(lines, 1):
            if line_num in processed_lines:
                continue
            
            line = line.strip()
            if not line:
                continue
            
            try:
                geom = loads_wkt(line)
                if isinstance(geom, Polygon):
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    polygons.append(geom)
                elif isinstance(geom, MultiPolygon):
                    for poly in geom.geoms:
                        if not poly.is_valid:
                            poly = make_valid(poly)
                        polygons.append(poly)
            except Exception:
                # 尝试正则匹配
                multipolygon_match = re.search(
                    r'MULTIPOLYGON\s*\([^)]+\)', 
                    line, 
                    re.IGNORECASE | re.DOTALL
                )
                if multipolygon_match:
                    try:
                        geom = loads_wkt(multipolygon_match.group(0))
                        if isinstance(geom, MultiPolygon):
                            for poly in geom.geoms:
                                if not poly.is_valid:
                                    poly = make_valid(poly)
                                polygons.append(poly)
                    except Exception:
                        pass
                else:
                    polygon_match = re.search(
                        r'POLYGON\s*\([^)]+\)', 
                        line, 
                        re.IGNORECASE
                    )
                    if polygon_match:
                        try:
                            geom = loads_wkt(polygon_match.group(0))
                            if isinstance(geom, Polygon):
                                if not geom.is_valid:
                                    geom = make_valid(geom)
                                polygons.append(geom)
                        except Exception:
                            pass
        
        return polygons
    
    def check_intersections(self, polygons):
        """检测POLYGON相交"""
        has_intersection = False
        details = []
        intersection_pairs = []
        
        if len(polygons) < 2:
            return {
                'has_intersection': False,
                'details': ["至少需要2个POLYGON才能检测相交"]
            }
        
        for i in range(len(polygons)):
            for j in range(i + 1, len(polygons)):
                if polygons[i].intersects(polygons[j]):
                    has_intersection = True
                    intersection_pairs.append((i + 1, j + 1))
                    intersection_area = polygons[i].intersection(polygons[j]).area
                    details.append(
                        f"POLYGON {i+1} 与 POLYGON {j+1} 相交（相交面积：{intersection_area:.6f}）"
                    )
        
        if not has_intersection:
            details.append(
                f"共检测 {len(polygons)} 个POLYGON，但它们之间没有相交关系"
            )
        
        return {
            'has_intersection': has_intersection,
            'details': details,
            'intersection_pairs': intersection_pairs
        }
    
    def merge_polygons(self, polygons):
        """合并POLYGON"""
        if len(polygons) == 0:
            return None
        
        if len(polygons) == 1:
            return self._convert_to_single_polygon(polygons[0])
        
        merged = unary_union(polygons)
        
        if isinstance(merged, MultiPolygon):
            if len(merged.geoms) > 1:
                return merged.convex_hull
            else:
                merged = merged.geoms[0]
        
        if not merged.is_valid:
            merged = make_valid(merged)
        
        return merged
    
    def _convert_to_single_polygon(self, geom):
        """转换为单部件POLYGON"""
        if isinstance(geom, Polygon):
            if not geom.is_valid:
                geom = make_valid(geom)
                if isinstance(geom, MultiPolygon):
                    if len(geom.geoms) > 0:
                        geom = max(geom.geoms, key=lambda p: p.area)
                    else:
                        geom = geom.geoms[0]
            return geom
        elif isinstance(geom, MultiPolygon):
            if len(geom.geoms) == 1:
                result = geom.geoms[0]
                if not result.is_valid:
                    result = make_valid(result)
                if isinstance(result, MultiPolygon):
                    result = result.convex_hull
                return result
            else:
                return geom.convex_hull
        else:
            return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
    
    def _unify_geometry(self, geom):
        """统一几何体"""
        if isinstance(geom, MultiPolygon):
            if len(geom.geoms) > 1:
                return unary_union(geom.geoms)
            else:
                return geom.geoms[0]
        elif isinstance(geom, Polygon):
            return geom
        else:
            return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
    
    def clip_polygon(self, polygon1, polygon2):
        """
        使用第一个POLYGON裁剪第二个POLYGON
        返回：第二个POLYGON中与第一个POLYGON不相交的部分（单部件）
        """
        geom1 = self._unify_geometry(polygon1)
        geom2 = self._unify_geometry(polygon2)
        
        if not geom1.intersects(geom2):
            return self._convert_to_single_polygon(geom2)
        
        clipped_result = geom2.difference(geom1)
        
        if not clipped_result.is_valid:
            clipped_result = make_valid(clipped_result)
        
        if clipped_result.is_empty:
            return self._convert_to_single_polygon(geom2)
        
        return self._convert_to_single_polygon(clipped_result)
    
    def batch_chain_clip(self, polygon_list):
        """
        批量链式裁剪
        
        参数:
            polygon_list: Polygon对象列表
        
        返回:
            list: 裁剪后的POLYGON列表（每个都是单部件POLYGON）
        """
        if len(polygon_list) == 0:
            return []
        
        if len(polygon_list) == 1:
            return [self._convert_to_single_polygon(polygon_list[0])]
        
        result_polygons = []
        
        # 第一个POLYGON保持不变
        first_polygon = self._convert_to_single_polygon(polygon_list[0])
        result_polygons.append(first_polygon)
        
        previous_clipped = first_polygon
        
        for i in range(1, len(polygon_list)):
            current_polygon = polygon_list[i]
            
            if not previous_clipped.intersects(current_polygon):
                # 不相交，保持原样
                clipped_result = self._convert_to_single_polygon(current_polygon)
            else:
                # 相交，执行裁剪
                clipped_result = current_polygon.difference(previous_clipped)
                
                if not clipped_result.is_valid:
                    clipped_result = make_valid(clipped_result)
                
                if clipped_result.is_empty:
                    # 完全被裁剪，使用原始POLYGON（保持数量一致）
                    clipped_result = self._convert_to_single_polygon(current_polygon)
                else:
                    clipped_result = self._convert_to_single_polygon(clipped_result)
            
            result_polygons.append(clipped_result)
            previous_clipped = clipped_result
        
        return result_polygons
```

## 🚀 使用示例

### 示例1：合并多个POLYGON

```python
processor = PolygonProcessor()

# 输入多个POLYGON（WKT格式）
input_text = """
POLYGON ((111.64234313364233 22.09642875544313, 111.6474929749504 22.092571662500227, ...))
POLYGON ((111.6375370620976 22.09216435331299, 111.6395540832718 22.086875575368065, ...))
"""

# 解析
polygons = processor.parse_polygons(input_text)

# 检测相交
intersection_info = processor.check_intersections(polygons)

if intersection_info['has_intersection']:
    # 合并
    merged = processor.merge_polygons(polygons)
    print(f"合并后的POLYGON: {merged.wkt}")
else:
    print("POLYGON不相交，无法合并")
```

### 示例2：单POLYGON转换

```python
# 输入单个MULTIPOLYGON
input_text = "MULTIPOLYGON (((111.618137 21.75955, ...)))"

# 解析
polygons = processor.parse_polygons(input_text)

if len(polygons) == 1:
    # 转换为单部件
    single_polygon = processor._convert_to_single_polygon(polygons[0])
    print(f"单部件POLYGON: {single_polygon.wkt}")
```

### 示例3：POLYGON裁剪

```python
# 输入两个POLYGON
polygon1_text = "POLYGON ((...))"
polygon2_text = "POLYGON ((...))"

# 解析
polygons1 = processor.parse_polygons(polygon1_text)
polygons2 = processor.parse_polygons(polygon2_text)

if len(polygons1) > 0 and len(polygons2) > 0:
    # 裁剪
    clipped = processor.clip_polygon(polygons1[0], polygons2[0])
    print(f"裁剪后的POLYGON: {clipped.wkt}")
```

### 示例4：批量链式裁剪

```python
# 从文件读取多个POLYGON
with open('polygons.txt', 'r', encoding='utf-8') as f:
    input_text = f.read()

# 解析
polygons = processor.parse_polygons(input_text)

# 链式裁剪
clipped_polygons = processor.batch_chain_clip(polygons)

# 输出结果（每行一个POLYGON）
output_lines = [poly.wkt for poly in clipped_polygons]
output_text = '\n'.join(output_lines)

# 保存到文件
with open('clipped_polygons.txt', 'w', encoding='utf-8') as f:
    f.write(output_text)

print(f"处理完成：输入 {len(polygons)} 个，输出 {len(clipped_polygons)} 个")
```

## 📊 功能说明

### 1. POLYGON合并
- **功能**：合并多个相交的POLYGON为一个POLYGON
- **要求**：输入的POLYGON必须相交
- **输出**：单个POLYGON（如果合并后是多部件，使用凸包转换为单部件）

### 2. 单POLYGON转换
- **功能**：将单个POLYGON或单组件MULTIPOLYGON转换为单部件POLYGON
- **输入**：单个POLYGON或MULTIPOLYGON（只有一个组件）
- **输出**：单部件POLYGON

### 3. POLYGON裁剪
- **功能**：使用第一个POLYGON裁剪第二个POLYGON
- **操作**：difference（差集）
- **输出**：第二个POLYGON中与第一个POLYGON不相交的部分（单部件）

### 4. 批量链式裁剪
- **功能**：按顺序链式裁剪多个POLYGON
- **逻辑**：
  - 第1个：保持不变
  - 第2个：裁剪掉与第1个相交的部分
  - 第3个：裁剪掉与裁剪后的第2个相交的部分
  - 以此类推...
- **输出**：每个POLYGON裁剪后的结果列表（单部件POLYGON格式）
- **保证**：输出数量 = 输入数量

## ⚠️ 注意事项

1. **几何体有效性**：所有几何体都会自动修复无效的部分
2. **多部件处理**：如果结果是多部件MULTIPOLYGON，会自动转换为单部件（使用convex_hull）
3. **相交检测**：合并和裁剪功能需要POLYGON相交才能工作
4. **链式裁剪**：每个POLYGON都参照前一个裁剪结果进行裁剪
5. **输出格式**：所有输出都是单部件POLYGON格式（WKT）

## 📄 文件格式

### 输入文件格式
- 文本文件（.txt），每行一个POLYGON或MULTIPOLYGON（WKT格式）
- 支持跨行的MULTIPOLYGON
- 支持混合POLYGON和MULTIPOLYGON

### 输出文件格式
- 文本文件（.txt），每行一个POLYGON（WKT格式）
- 所有输出都是单部件POLYGON格式
- 输出行数 = 输入行数（对于链式裁剪）

## 🔍 错误处理

1. **解析失败**：跳过无法解析的行，继续处理其他行
2. **无效几何体**：自动使用`make_valid`修复
3. **多部件结果**：自动转换为单部件（使用convex_hull）
4. **空结果**：链式裁剪中，如果被完全裁剪，输出原始POLYGON（保持数量一致）

## 📝 完整独立实现

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYGON合并与链式分割功能 - 独立实现
可直接用于其他应用
"""

import logging
import re
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.wkt import loads as loads_wkt

try:
    from shapely.validation import make_valid
except ImportError:
    def make_valid(geom):
        if geom.is_valid:
            return geom
        return geom.buffer(0)


class PolygonProcessor:
    """POLYGON处理工具类 - 独立实现版本"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_polygons(self, input_text):
        """解析POLYGON数据"""
        polygons = []
        
        # 先尝试整体解析
        try:
            cleaned_text = ' '.join(input_text.strip().split())
            if cleaned_text:
                geom = loads_wkt(cleaned_text)
                if isinstance(geom, MultiPolygon):
                    for poly in geom.geoms:
                        if not poly.is_valid:
                            poly = make_valid(poly)
                        polygons.append(poly)
                    return polygons
                elif isinstance(geom, Polygon):
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    polygons.append(geom)
                    return polygons
        except Exception:
            pass
        
        # 按行解析
        lines = input_text.strip().split('\n')
        processed_lines = set()
        
        for line_num, line in enumerate(lines, 1):
            if line_num in processed_lines:
                continue
            
            line = line.strip()
            if not line:
                continue
            
            try:
                geom = loads_wkt(line)
                if isinstance(geom, Polygon):
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    polygons.append(geom)
                elif isinstance(geom, MultiPolygon):
                    for poly in geom.geoms:
                        if not poly.is_valid:
                            poly = make_valid(poly)
                        polygons.append(poly)
            except Exception:
                # 正则匹配MULTIPOLYGON
                multipolygon_match = re.search(
                    r'MULTIPOLYGON\s*\([^)]+\)', 
                    line, 
                    re.IGNORECASE | re.DOTALL
                )
                if multipolygon_match:
                    try:
                        geom = loads_wkt(multipolygon_match.group(0))
                        if isinstance(geom, MultiPolygon):
                            for poly in geom.geoms:
                                if not poly.is_valid:
                                    poly = make_valid(poly)
                                polygons.append(poly)
                    except Exception:
                        pass
                else:
                    # 正则匹配POLYGON
                    polygon_match = re.search(
                        r'POLYGON\s*\([^)]+\)', 
                        line, 
                        re.IGNORECASE
                    )
                    if polygon_match:
                        try:
                            geom = loads_wkt(polygon_match.group(0))
                            if isinstance(geom, Polygon):
                                if not geom.is_valid:
                                    geom = make_valid(geom)
                                polygons.append(geom)
                        except Exception:
                            pass
        
        return polygons
    
    def check_intersections(self, polygons):
        """检测POLYGON相交"""
        has_intersection = False
        details = []
        intersection_pairs = []
        
        if len(polygons) < 2:
            return {
                'has_intersection': False,
                'details': ["至少需要2个POLYGON才能检测相交"]
            }
        
        for i in range(len(polygons)):
            for j in range(i + 1, len(polygons)):
                if polygons[i].intersects(polygons[j]):
                    has_intersection = True
                    intersection_pairs.append((i + 1, j + 1))
                    intersection_area = polygons[i].intersection(polygons[j]).area
                    details.append(
                        f"POLYGON {i+1} 与 POLYGON {j+1} 相交（相交面积：{intersection_area:.6f}）"
                    )
        
        if not has_intersection:
            details.append(
                f"共检测 {len(polygons)} 个POLYGON，但它们之间没有相交关系"
            )
        
        return {
            'has_intersection': has_intersection,
            'details': details,
            'intersection_pairs': intersection_pairs
        }
    
    def merge_polygons(self, polygons):
        """合并POLYGON"""
        if len(polygons) == 0:
            return None
        
        if len(polygons) == 1:
            return self._convert_to_single_polygon(polygons[0])
        
        merged = unary_union(polygons)
        
        if isinstance(merged, MultiPolygon):
            if len(merged.geoms) > 1:
                return merged.convex_hull
            else:
                merged = merged.geoms[0]
        
        if not merged.is_valid:
            merged = make_valid(merged)
        
        return merged
    
    def _convert_to_single_polygon(self, geom):
        """转换为单部件POLYGON"""
        if isinstance(geom, Polygon):
            if not geom.is_valid:
                geom = make_valid(geom)
                if isinstance(geom, MultiPolygon):
                    if len(geom.geoms) > 0:
                        geom = max(geom.geoms, key=lambda p: p.area)
                    else:
                        geom = geom.geoms[0]
            return geom
        elif isinstance(geom, MultiPolygon):
            if len(geom.geoms) == 1:
                result = geom.geoms[0]
                if not result.is_valid:
                    result = make_valid(result)
                if isinstance(result, MultiPolygon):
                    result = result.convex_hull
                return result
            else:
                return geom.convex_hull
        else:
            return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
    
    def _unify_geometry(self, geom):
        """统一几何体"""
        if isinstance(geom, MultiPolygon):
            if len(geom.geoms) > 1:
                return unary_union(geom.geoms)
            else:
                return geom.geoms[0]
        elif isinstance(geom, Polygon):
            return geom
        else:
            return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
    
    def clip_polygon(self, polygon1, polygon2):
        """
        使用第一个POLYGON裁剪第二个POLYGON
        返回：第二个POLYGON中与第一个POLYGON不相交的部分（单部件）
        """
        geom1 = self._unify_geometry(polygon1)
        geom2 = self._unify_geometry(polygon2)
        
        if not geom1.intersects(geom2):
            return self._convert_to_single_polygon(geom2)
        
        clipped_result = geom2.difference(geom1)
        
        if not clipped_result.is_valid:
            clipped_result = make_valid(clipped_result)
        
        if clipped_result.is_empty:
            return self._convert_to_single_polygon(geom2)
        
        return self._convert_to_single_polygon(clipped_result)
    
    def batch_chain_clip(self, polygon_list):
        """
        批量链式裁剪
        
        参数:
            polygon_list: Polygon对象列表
        
        返回:
            list: 裁剪后的POLYGON列表（每个都是单部件POLYGON）
                 输出数量 = 输入数量
        """
        if len(polygon_list) == 0:
            return []
        
        if len(polygon_list) == 1:
            return [self._convert_to_single_polygon(polygon_list[0])]
        
        result_polygons = []
        
        # 第一个POLYGON保持不变
        first_polygon = self._convert_to_single_polygon(polygon_list[0])
        result_polygons.append(first_polygon)
        
        previous_clipped = first_polygon
        
        for i in range(1, len(polygon_list)):
            current_polygon = polygon_list[i]
            
            if not previous_clipped.intersects(current_polygon):
                # 不相交，保持原样
                clipped_result = self._convert_to_single_polygon(current_polygon)
            else:
                # 相交，执行裁剪
                clipped_result = current_polygon.difference(previous_clipped)
                
                if not clipped_result.is_valid:
                    clipped_result = make_valid(clipped_result)
                
                if clipped_result.is_empty:
                    # 完全被裁剪，使用原始POLYGON（保持数量一致）
                    clipped_result = self._convert_to_single_polygon(current_polygon)
                else:
                    clipped_result = self._convert_to_single_polygon(clipped_result)
            
            result_polygons.append(clipped_result)
            previous_clipped = clipped_result
        
        return result_polygons


# 使用示例
if __name__ == "__main__":
    processor = PolygonProcessor()
    
    # 示例：从文件读取并处理
    with open('input_polygons.txt', 'r', encoding='utf-8') as f:
        input_text = f.read()
    
    # 解析
    polygons = processor.parse_polygons(input_text)
    print(f"解析到 {len(polygons)} 个POLYGON")
    
    # 链式裁剪
    clipped_polygons = processor.batch_chain_clip(polygons)
    
    # 输出
    output_lines = [poly.wkt for poly in clipped_polygons]
    output_text = '\n'.join(output_lines)
    
    with open('output_polygons.txt', 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    print(f"处理完成：输出 {len(clipped_polygons)} 个POLYGON")
```

## 📚 API参考

### PolygonProcessor类

#### 方法列表

| 方法名 | 说明 | 参数 | 返回值 |
|--------|------|------|--------|
| `parse_polygons(input_text)` | 解析POLYGON数据 | `input_text: str` | `list[Polygon]` |
| `check_intersections(polygons)` | 检测相交关系 | `polygons: list[Polygon]` | `dict` |
| `merge_polygons(polygons)` | 合并POLYGON | `polygons: list[Polygon]` | `Polygon` |
| `clip_polygon(polygon1, polygon2)` | 裁剪POLYGON | `polygon1, polygon2: Polygon` | `Polygon` |
| `batch_chain_clip(polygon_list)` | 批量链式裁剪 | `polygon_list: list[Polygon]` | `list[Polygon]` |

## 🔗 相关资源

- Shapely文档：https://shapely.readthedocs.io/
- WKT格式说明：https://en.wikipedia.org/wiki/Well-known_text_representation_of_geometry

---

**文档版本**：1.0  
**最后更新**：2025-01-XX  
**作者**：优化百宝箱工具集

