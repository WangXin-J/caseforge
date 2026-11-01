"""CaseForge —— 声明式接口用例执行引擎。

设计目标：
1. 用例用 YAML 描述，和执行代码分离；
2. 步骤之间可以提取变量并向下传递（真实业务链路的必要条件）；
3. 失败要能归因，而不是只抛一个 AssertionError；
4. 报告可被 CI 消费（JUnit XML）。
"""
from .models import Case, Step, Assertion
from .loader import load_cases, load_case
from .runner import run_case, run_suite
from .report import to_console, to_json, to_junit

__version__ = "0.1.0"

__all__ = [
    "Case", "Step", "Assertion",
    "load_cases", "load_case",
    "run_case", "run_suite",
    "to_console", "to_json", "to_junit",
    "__version__",
]
