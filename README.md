# CaseForge

声明式接口用例执行引擎：用 YAML 描述用例，步骤之间传递变量，失败时自动归因。

```
$ caseforge run examples/cases --base-url http://127.0.0.1:8010
[PASS] 告警规则 创建-查询-删除 闭环  (142 ms)
  ok  创建规则  201  38ms
  ok  按 ID 查询，字段与创建时一致  200  2ms
  ok  列表包含该规则  200  2ms
  ok  删除规则  204  2ms
  ok  删除后再查应为 404  404  2ms
[PASS] 指标接口 参数校验与契约  (9 ms)
  ...
------------------------------------------------------------------------------
用例 2  通过 2  失败 0  耗时 0.15s
```

## 解决的问题

写接口自动化的方式大致两种：Postman 点出来，或者用代码写。前者不好进 CI、不好做断言复用、链路一长就乱；后者每条用例都要写重复的请求构造和断言，改一个字段要动十处。

CaseForge 走第三条：**用例是数据，执行是引擎**。

- 用例写在 YAML 里，改字段不用改代码，测试同学也能改；
- 步骤之间可以提取响应字段给下一步用（`${{ rule_id }}`），真实业务链路才串得起来；
- 失败时给出**归因**，而不只是「断言失败」。

## 核心特性

| 特性 | 说明 |
|---|---|
| 声明式用例 | YAML 描述请求、断言、变量提取，与执行代码分离 |
| 变量串联 | 上一步 `extract` 的字段可在后续步骤用 `${{ name }}` 引用 |
| 失败归因 | 区分 `ASSERT_FAIL` / `SCHEMA_DRIFT` / `SERVER_ERROR` / `TIMEOUT` / `CONNECTION_ERROR` / `CASE_ERROR` |
| 契约校验 | 内置 JSON Schema 断言，契约变了能被单独识别出来 |
| 并发执行 | `--workers N`，每个用例独立 session，互不污染 |
| 失败重试 | 步骤级 `retries`，只对超时和连接错误重试 |
| 报告 | 控制台 / JSON / **JUnit XML**（Jenkins、GitLab CI、GitHub Actions 都能直接读） |

## 快速开始

```powershell
pip install -e ".[dev]"

# 起演示服务
python examples/demo_server.py 8010

# 另开一个窗口执行
caseforge run examples/cases --base-url http://127.0.0.1:8010
```

跑测试：

```powershell
pytest -q
```

## 用例格式

```yaml
name: 告警规则 创建-查询-删除 闭环
tags: [smoke, alert]
vars:
  rule_name: "caseforge-${{ timestamp }}"

steps:
  - name: 创建规则
    request:
      method: POST
      path: /api/alert/rules
      json:
        name: "${{ rule_name }}"
        metric: cpu
        operator: ">"
        threshold: 90
    extract:
      rule_id: $.id          # 把响应里的 id 存成变量
    assert:
      - status: 201
      - json_path: { path: $.enabled, equals: true }
      - schema:
          type: object
          required: [id, name, threshold]

  - name: 按 ID 查询
    request:
      method: GET
      path: /api/alert/rules/${{ rule_id }}   # 引用上一步提取的变量
    assert:
      - status: 200
      - json_path: { path: $.name, equals: "${{ rule_name }}" }
      - max_time: { max_time_ms: 1000 }
```

步骤可选字段：`timeout`（秒）、`retries`、`continue_on_failure`（失败后是否继续后续步骤）。

## 断言语义

| 断言 | 写法 | 失败归因 |
|---|---|---|
| 状态码 | `- status: 200` 或 `- status: [200, 201]` | `ASSERT_FAIL`（5xx 时为 `SERVER_ERROR`） |
| JSON 字段 | `- json_path: { path: $.a.b, equals: 1 }` | `ASSERT_FAIL`；路径不存在时 `SCHEMA_DRIFT` |
| 包含 | `- json_path: { path: $.items[*].id, contains: "r-1" }` | `ASSERT_FAIL` |
| 数值区间 | `gt` / `lt` | `ASSERT_FAIL` |
| 存在性 | `exists: true` | `ASSERT_FAIL` |
| 结构 | `- schema: { type: object, required: [id] }` | `SCHEMA_DRIFT` |
| 响应头 | `- header: { header: Content-Type, contains: json }` | `ASSERT_FAIL` |
| 响应耗时 | `- max_time: { max_time_ms: 800 }` | `ASSERT_FAIL` |

## 失败归因

报告里每个失败都带类型，目的是一眼分清「谁的问题」：

| 类型 | 含义 | 通常该找谁 |
|---|---|---|
| `ASSERT_FAIL` | 断言不等 | 被测服务或用例预期 |
| `SCHEMA_DRIFT` | 响应结构/字段变了 | 后端接口变更，或契约文档过期 |
| `SERVER_ERROR` | 5xx | 后端 |
| `TIMEOUT` | 超时 | 服务性能或网络 |
| `CONNECTION_ERROR` | 连不上 | 环境、部署、端口 |
| `CASE_ERROR` | 用例自身写错（如引用了未定义变量） | 测试同学 |

## 结构

```
caseforge/
├─ caseforge/
│  ├─ models.py       # Case / Step / Assertion / 结果对象
│  ├─ loader.py       # YAML → 对象，只做结构校验
│  ├─ runner.py       # 执行、变量插值、失败归因
│  ├─ assertions.py   # 断言求值
│  ├─ jsonpath.py     # 极简 JSONPath（$.a.b、[0]、[*]）
│  ├─ report.py       # 控制台 / JSON / JUnit XML
│  └─ cli.py          # 命令行
├─ examples/          # 演示服务 + 示例用例
└─ tests/             # 引擎自身的测试（含真实 HTTP 集成测试）
```

两个刻意的设计：

1. **解析与替换分离**。`loader` 只校验结构，变量插值放到 `runner` 里做——因为变量依赖上一步的响应，加载阶段根本不知道值。
2. **执行器兜住所有异常**。单条用例失败不能带崩整轮，所以最终是 `except Exception` 并转成归因类型；否则跑 200 条时中途崩掉，排查成本极高。

## 和已有工具的关系

这一节是我在写之前想清楚的，也欢迎对照代码看：

- **借鉴的设计**：YAML 声明式用例（Tavern、Karate 都这么做）、变量提取与串联（Postman 的 environment 思路）、JUnit XML 报告（CI 通用标准，自己造格式没有意义）。
- **自己写的部分**：执行引擎、变量插值、极简 JSONPath、断言层、失败归因分类、报告生成。没有引用上述项目的代码。
- **为什么不用现成的**：Tavern 绑定在 pytest 生态里，用例和测试函数混在一起；Postman 的 CLI（newman）依赖 Collection 格式，版本管理和 diff 不友好。这个项目更接近「小而可控的执行内核」，方便嵌入到自己的流水线里。

如果只是要跑测试，用 pytest + requests 更快；这个项目想验证的是**引擎该怎么设计**。

## 已知限制

- JSONPath 只支持 `$.a.b`、`[n]`、`[*]`，不支持过滤表达式（`[?(@.x>1)]`）；
- 不支持 Cookie / OAuth 自动续期，需要的话在 `request.headers` 里手写；
- 并发是线程级，够用但不适合压测场景（压测请用 LoadLab / JMeter）；
- 报告没有 HTML 视图，JUnit XML 交给 CI 渲染。

## License

MIT
