# 离线“平台注意力—公开制度化诉求”指数输入格式

本目录只提供字段模板和人工生成的合成测试数据，不包含微博或人民网的
真实记录，也不包含任何联网抓取代码。

## 标准 CSV

`synthetic_hotspot_demand_fixture.csv` 使用脚本要求的完整字段：

| 字段 | 含义 |
|---|---|
| `source` | `weibo_hot`、`leader_board` 或可选的 `government_daily` |
| `observed_at` | 带时区的 ISO-8601 观测时间 |
| `region` | 可比较的共同地域范围 |
| `topic` | 已映射到共同分类体系的主题 |
| `rank` | 热榜名次；按名次加权时微博记录必须填写 |
| `heat` | 官方授权数据若提供稳定热度值可填写，否则留空 |
| `count` | 聚合记录数量；单条记录可填 `1` 或留空 |
| `record_id` | 数据源内部的匿名、稳定记录标识 |
| `access_route` | 授权接口、公开聚合报告或合成数据的来源路径说明 |
| `license_note` | 使用和再分发条件说明 |
| `data_scope` | 数据证据范围，例如 `synthetic`、`official_aggregate` 或 `authorized_export` |

脚本实行严格字段校验，拒绝额外字段，以防留言正文、用户名、电话或精确
地址被误带入分析结果。每一行都必须明确填写 `data_scope`、`access_route`
和 `license_note`；脚本不会把缺少来源说明的数据自动解释为真实观测。

## 运行

从仓库根目录运行：

```powershell
python 08_version3_response_dashboard/02_experiment_code/build_hotspot_demand_index.py `
  --input 08_version3_response_dashboard/03_data/external_index_template/synthetic_hotspot_demand_fixture.csv `
  --output-dir 08_version3_response_dashboard/05_outputs/external_index_smoke `
  --window-days 7 `
  --top-k 2
```

默认对微博榜单使用 `1/log2(rank+1)` 权重。也可显式选择
`--weibo-weight heat` 或 `--weibo-weight count`，但不同权重版本应分别报告，
不得混合成一组结果。只有完整的七个日历日窗口才会进入输出。

主要输出为滚动主题分布、指数时间序列、逐主题可见性差距和包含公式、
输入 SHA-256、证据范围的元数据 JSON。合成 fixture 只能用于代码验证，不能
作为外部效度证据。
