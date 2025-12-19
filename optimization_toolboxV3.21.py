#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimization_toolbox.py
=======================

一站式脚本，用于启动、检查和维护"优化百宝箱"工具集。

功能概览
--------
- web：启动 Streamlit Web 界面
- cli：进入交互式命令行菜单
- status / backup / cleanup / sql：常用维护命令
- tool：查看并尝试运行 tools/ 下的插件
- upgrade：若存在 upgrade_system.py，可执行数据库迁移
"""

import argparse
import glob
import importlib
import logging
import os
import sqlite3
import subprocess
import sys
import textwrap
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple, Any

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

# 确保可以导入项目内模块
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from database import DatabaseManager, db_manager  # noqa: E402

try:
    from upgrade_system import UpgradeSystem  # type: ignore
except ImportError:  # pragma: no cover - 可选模块
    UpgradeSystem = None


# ------------------------------------------------------------------ #
# 工具接口定义
# ------------------------------------------------------------------ #
class BaseTool(ABC):
    """工具插件基础接口"""
    
    @abstractmethod
    def run(self, db: DatabaseManager, **kwargs) -> Any:
        """运行工具的主要逻辑"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass


# ------------------------------------------------------------------ #
# 工具自动发现
# ------------------------------------------------------------------ #
def discover_tools() -> Dict[str, str]:
    """自动发现 tools/ 目录下的工具模块"""
    tools_dir = os.path.join(ROOT_DIR, "tools")
    tool_registry = {}
    
    if not os.path.exists(tools_dir):
        return tool_registry
    
    # 查找所有 Python 文件
    python_files = glob.glob(os.path.join(tools_dir, "*.py"))
    
    for file_path in python_files:
        file_name = os.path.basename(file_path)
        # 跳过 __init__.py 和以 _ 开头的文件
        if file_name == "__init__.py" or file_name.startswith("_"):
            continue
        
        module_name = file_name[:-3]  # 移除 .py 扩展名
        module_path = f"tools.{module_name}"
        tool_registry[module_name] = module_path
    
    return tool_registry


# ------------------------------------------------------------------ #
# 主控制器类
# ------------------------------------------------------------------ #
class OptimizationToolboxController:
    """统一入口控制器"""

    def __init__(self, db: DatabaseManager = db_manager):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)
        self.log_dir = os.path.join(ROOT_DIR, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.tool_registry = discover_tools()

    # ------------------------------------------------------------------ #
    # 环境与依赖
    # ------------------------------------------------------------------ #
    @staticmethod
    def setup_logging(level: int = logging.INFO) -> None:
        """设置日志，使用包含时间的文件名"""
        os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)
        log_file = os.path.join(
            ROOT_DIR, "logs", f"optimization_toolbox_{datetime.now():%Y%m%d_%H%M%S}.log"
        )
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
            force=True,
        )

    @staticmethod
    def check_dependencies(
        required: Optional[List[str]] = None, 
        optional: Optional[List[str]] = None
    ) -> Tuple[bool, List[str]]:
        """
        检查依赖包，支持版本检查
        
        Args:
            required: 必需包列表，格式为 ["package", "package>=version"]
            optional: 可选包列表
            
        Returns:
            (是否满足依赖, 缺失的包列表)
        """
        required = required or []
        optional = optional or []
        missing_packages = []
        
        # 基础包检查
        base_packages = ["streamlit", "pandas", "numpy", "openpyxl"]
        all_packages = base_packages + required + optional
        
        for pkg_spec in all_packages:
            try:
                # 解析包名和版本要求
                if ">=" in pkg_spec:
                    pkg_name, version_spec = pkg_spec.split(">=")
                    pkg_name = pkg_name.strip()
                    installed_version = version(pkg_name)
                    # 简单的版本比较（实际项目中可使用 packaging.version）
                    if installed_version < version_spec.strip():
                        missing_packages.append(pkg_spec)
                else:
                    pkg_name = pkg_spec
                    version(pkg_name)  # 只是检查是否存在
            except PackageNotFoundError:
                missing_packages.append(pkg_spec)
        
        # 只返回必需包的缺失情况
        required_missing = [
            pkg for pkg in missing_packages 
            if any(req in pkg for req in required + base_packages)
        ]
        
        if required_missing:
            install_cmd = "pip install " + " ".join(required_missing)
            print(f"缺少依赖: {', '.join(required_missing)}")
            print(f"请运行: {install_cmd}")
            return False, required_missing
        
        return True, []

    def initialize_system(self) -> bool:
        """初始化数据库并可选执行迁移"""
        try:
            self.db._init_database()  # type: ignore[attr-defined]
            if UpgradeSystem is not None:
                upgrade = UpgradeSystem(self.db)
                status = upgrade.get_upgrade_status()
                if not status.get("is_up_to_date", True):
                    print(
                        f"发现 {status.get('pending_migrations', 0)} 个待应用迁移，开始执行..."
                    )
                    if not upgrade.auto_upgrade():
                        print("自动迁移失败，请检查 upgrade_system 日志")
                        return False
            return True
        except Exception as exc:  # pragma: no cover
            print(f"系统初始化失败: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # 运行模式
    # ------------------------------------------------------------------ #
    def run_streamlit(self, port: int, host: str, headless: bool) -> None:
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            os.path.join(ROOT_DIR, "main_app.py"),
            "--server.port",
            str(port),
            "--server.address",
            host,
            "--server.headless",
            "true" if headless else "false",
        ]
        print(f"🚀 启动 Web 界面: http://{host}:{port}")
        subprocess.run(cmd, check=False)

    def run_interactive_cli(self) -> None:
        """动态生成 CLI 菜单"""
        menu_items = [
            ("1", "查看系统状态", self.show_system_status),
            ("2", "备份数据库", self.backup_database),
            ("3", "清理导入日志", lambda: self.cleanup_import_logs(30)),
            ("4", "执行 SQL", self._sql_interactive),
            ("5", "列出可用工具", lambda: self.list_tools(verbose=True)),
            ("6", "运行工具", self._tool_interactive),
            ("0", "退出", None),
        ]
        
        while True:
            print("\n" + "="*40)
            print("优化百宝箱 - 命令行界面")
            print("="*40)
            for key, desc, _ in menu_items:
                print(f"{key}. {desc}")
            print("="*40)
            
            choice = input("请选择操作: ").strip()
            
            if choice == "0":
                print("👋 已退出 CLI")
                break
                
            for key, desc, func in menu_items:
                if choice == key and func:
                    try:
                        func()
                    except Exception as e:
                        print(f"执行操作时出错: {e}")
                    break
            else:
                print("无效选项，请重新输入。")

    def _sql_interactive(self) -> None:
        """交互式 SQL 执行"""
        sql = input("请输入 SQL 语句: ").strip()
        if sql:
            self.execute_sql(sql)

    def _tool_interactive(self) -> None:
        """交互式工具运行"""
        self.list_tools(verbose=True)
        tool_name = input("\n请输入工具名称: ").strip()
        if tool_name:
            self.try_run_tool(tool_name)

    # ------------------------------------------------------------------ #
    # 系统状态与统计
    # ------------------------------------------------------------------ #
    def show_system_status(self) -> None:
        """显示完整的系统状态和数据库统计"""
        try:
            # 获取数据库统计
            stats = self.db.get_database_stats()
            
            print("\n" + "="*50)
            print("系统状态概览")
            print("="*50)
            
            # 数据库基本信息
            print(f"📊 数据库大小: {stats.get('db_size_mb', 0):.1f} MB")
            print(f"📋 表数量: {stats.get('table_count', 0)}")
            
            # 各表数据量统计
            table_stats = [
                ("小区映射", "cell_mapping_count"),
                ("干扰数据", "interference_data_count"),
                ("工程参数", "engineering_params"),
                ("性能数据", "performance_data"),
                ("导入日志", "import_logs"),
            ]
            
            print("\n📈 数据统计:")
            for display_name, stat_key in table_stats:
                if stat_key in stats:
                    count = stats[stat_key]
                else:
                    # 对于不在默认统计中的表，单独查询
                    try:
                        if stat_key in ["engineering_params", "performance_data", "import_logs"]:
                            result = self.db.execute_query(
                                f"SELECT COUNT(*) AS count FROM {stat_key}"
                            )
                            count = result[0]["count"] if result else 0
                        else:
                            count = 0
                    except Exception:
                        count = 0
                print(f"   - {display_name}: {count:,} 条")
            
            # 其他统计信息
            other_stats = [k for k in stats.keys() if k not in 
                          ['db_size_mb', 'table_count'] and 
                          not k.endswith('_count') and
                          k not in ['engineering_params', 'performance_data', 'import_logs']]
            
            if other_stats:
                print("\n🔧 其他统计:")
                for stat_key in other_stats:
                    print(f"   - {stat_key}: {stats[stat_key]}")
                    
        except Exception as exc:
            print(f"获取系统状态失败: {exc}")

    # ------------------------------------------------------------------ #
    # 数据库维护命令
    # ------------------------------------------------------------------ #
    def backup_database(self, output: Optional[str] = None) -> None:
        """备份数据库，捕获特定异常"""
        if output is None:
            output = os.path.join(
                ROOT_DIR, f"backup_{datetime.now():%Y%m%d_%H%M%S}.db"
            )
        try:
            if self.db.backup_database(output):
                print(f"✅ 数据库备份成功: {output}")
            else:
                print("❌ 数据库备份失败")
        except sqlite3.Error as e:
            print(f"❌ 数据库备份出错 (SQLite错误): {e}")
        except Exception as e:
            print(f"❌ 数据库备份出错: {e}")

    def cleanup_import_logs(self, days: int = 30) -> None:
        """清理导入日志，捕获特定异常"""
        try:
            # 使用参数化查询防止 SQL 注入
            sql = "DELETE FROM import_logs WHERE created_at < datetime('now', ?)"
            success = self.db.execute_update(sql, (f"-{days} days",))
            if success:
                print(f"✅ 已清理 {days} 天前的导入日志")
            else:
                print("❌ 清理导入日志失败")
        except sqlite3.Error as e:
            print(f"❌ 清理导入日志出错 (SQLite错误): {e}")
        except Exception as e:
            print(f"❌ 清理导入日志出错: {e}")

    def execute_sql(self, sql: str, params: Optional[tuple] = None) -> None:
        """执行 SQL 语句，使用参数化查询"""
        try:
            sql_lower = sql.strip().lower()
            
            # 安全检查：限制可执行的语句类型
            allowed_keywords = ['select', 'insert', 'update', 'delete', 'explain']
            if not any(sql_lower.startswith(keyword) for keyword in allowed_keywords):
                print("❌ 只允许执行 SELECT, INSERT, UPDATE, DELETE, EXPLAIN 语句")
                return
            
            if sql_lower.startswith('select') or sql_lower.startswith('explain'):
                # 使用参数化查询执行
                rows = self.db.execute_query(sql, params)
                for row in rows:
                    print(dict(row))  # 转换为字典以便更好显示
                print(f"📊 总计 {len(rows)} 行")
            else:
                success = self.db.execute_update(sql, params)
                print("✅ 执行成功" if success else "❌ 执行失败")
                
        except sqlite3.Error as e:
            print(f"❌ SQL 执行失败 (SQLite错误): {e}")
        except Exception as e:
            print(f"❌ SQL 执行失败: {e}")

    # ------------------------------------------------------------------ #
    # tool 插件相关
    # ------------------------------------------------------------------ #
    def list_tools(self, verbose: bool = False) -> None:
        """列出所有可用工具"""
        if not self.tool_registry:
            print("未发现任何工具")
            return
            
        print(f"发现 {len(self.tool_registry)} 个工具:")
        for name, module_path in self.tool_registry.items():
            description = ""
            if verbose:
                description = self._get_tool_description(module_path)
                if description:
                    # 只取第一行描述
                    first_line = description.strip().split('\n')[0]
                    description = f" - {first_line}"
            print(f"  🔧 {name}{description}")

    def _get_tool_description(self, module_path: str) -> str:
        """获取工具描述"""
        try:
            module = importlib.import_module(module_path)
            
            # 尝试获取 BaseTool 实例的描述
            tool_instance = self._get_tool_instance(module_path)
            if tool_instance:
                return tool_instance.description
            
            # 回退到模块文档字符串
            return module.__doc__ or ""
        except Exception:
            return ""

    def _get_tool_instance(self, module_path: str) -> Optional[BaseTool]:
        """获取工具实例"""
        try:
            module = importlib.import_module(module_path)
            
            # 查找继承自 BaseTool 的类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseTool) and 
                    attr != BaseTool):
                    return attr()
            
            return None
        except Exception:
            return None

    def try_run_tool(self, tool_name: str, **kwargs) -> None:
        """尝试运行指定工具"""
        module_path = self.tool_registry.get(tool_name)
        if not module_path:
            print(f"❌ 未找到工具: {tool_name}")
            self.list_tools()
            return
        
        try:
            tool_instance = self._get_tool_instance(module_path)
            if tool_instance:
                print(f"🚀 执行 {tool_name}...")
                tool_instance.run(self.db, **kwargs)
                return
            
            # 回退到旧版接口
            module = importlib.import_module(module_path)
            if hasattr(module, "main"):
                print(f"🚀 执行 {tool_name}.main()...")
                module.main()  # type: ignore[attr-defined]
            elif hasattr(module, "run_cli"):
                print(f"🚀 执行 {tool_name}.run_cli()...")
                module.run_cli(self.db)  # type: ignore[attr-defined]
            else:
                print("ℹ️  该工具没有标准接口，请在 Streamlit UI 中使用。")
                
        except Exception as exc:
            print(f"❌ 运行工具失败: {exc}")
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # 升级/迁移
    # ------------------------------------------------------------------ #
    def run_upgrade(self) -> None:
        if UpgradeSystem is None:
            print("未找到 upgrade_system.py，无法执行升级。")
            return
        try:
            upgrade = UpgradeSystem(self.db)
            if upgrade.auto_upgrade():
                print("✅ 升级完成")
            else:
                print("❌ 升级失败，请检查日志")
        except Exception as exc:
            print(f"升级失败: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimization_toolbox.py",
        description="优化百宝箱工具集 - 单文件控制脚本",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # web
    parser_web = subparsers.add_parser("web", help="启动 Streamlit 界面")
    parser_web.add_argument("--port", type=int, default=8501)
    parser_web.add_argument("--host", default="localhost")
    parser_web.add_argument("--headless", action="store_true")

    # cli
    subparsers.add_parser("cli", help="进入交互式 CLI 菜单")

    # status / backup / cleanup / sql
    subparsers.add_parser("status", help="打印系统状态")
    parser_backup = subparsers.add_parser("backup", help="备份数据库")
    parser_backup.add_argument("--output", help="备份文件路径")

    parser_cleanup = subparsers.add_parser("cleanup", help="清理导入日志")
    parser_cleanup.add_argument("--days", type=int, default=30)

    parser_sql = subparsers.add_parser("sql", help="执行 SQL 语句")
    parser_sql.add_argument("statement", help="SQL 语句")
    parser_sql.add_argument("--params", nargs="*", help="SQL 参数")

    # tool - 使用子命令
    parser_tool = subparsers.add_parser("tool", help="工具管理")
    tool_subparsers = parser_tool.add_subparsers(dest="tool_action", required=True)
    
    tool_subparsers.add_parser("list", help="列出所有工具")
    
    parser_tool_run = tool_subparsers.add_parser("run", help="运行工具")
    parser_tool_run.add_argument("name", help="工具名称")
    
    parser_tool_describe = tool_subparsers.add_parser("describe", help="查看工具描述")
    parser_tool_describe.add_argument("name", help="工具名称")

    # upgrade
    subparsers.add_parser("upgrade", help="执行数据库升级（若可用）")

    # init/check
    subparsers.add_parser("init", help="初始化数据库并检查依赖")
    subparsers.add_parser("status-lite", help="快速检查数据库关键指标")

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    controller = OptimizationToolboxController()
    controller.setup_logging()

    if args.command == "init":
        deps_ok, missing = controller.check_dependencies()
        if deps_ok and controller.initialize_system():
            print("✅ 系统初始化完成")
        else:
            parser.exit(1)
        return

    if args.command == "status-lite":
        controller.show_system_status()
        return

    if args.command == "web":
        deps_ok, missing = controller.check_dependencies()
        if not deps_ok or not controller.initialize_system():
            parser.exit(1)
        controller.run_streamlit(args.port, args.host, args.headless)
        return

    if args.command == "cli":
        controller.run_interactive_cli()
        return

    if args.command == "status":
        controller.show_system_status()
        return

    if args.command == "backup":
        controller.backup_database(args.output)
        return

    if args.command == "cleanup":
        controller.cleanup_import_logs(args.days)
        return

    if args.command == "sql":
        params = tuple(args.params) if args.params else None
        controller.execute_sql(args.statement, params)
        return

    if args.command == "tool":
        if args.tool_action == "list":
            controller.list_tools(verbose=True)
        elif args.tool_action == "describe":
            description = controller._get_tool_description(
                controller.tool_registry.get(args.name, "")
            )
            if description:
                print(description.strip())
            else:
                print("未找到描述或模块。")
        elif args.tool_action == "run":
            controller.try_run_tool(args.name)
        return

    if args.command == "upgrade":
        controller.run_upgrade()
        return

    parser.print_help()


if __name__ == "__main__":
    main()