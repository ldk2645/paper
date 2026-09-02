# Version 2 案例数据说明

## 文件

- `case_700024_parameters.json`：请愿700024的真实事件时间、日级模型映射、制度门槛和参数证据边界。
- `uk_petition_response_delays_222.csv`：222条已获政府回应请愿的两列最小处理表，仅保留请愿编号和“达到10,000签名至政府回应”的天数。

## 来源与许可

数据来源是英国议会官方电子请愿API：

- 帮助页：<https://petition.parliament.uk/help>
- 已有回应查询：<https://petition.parliament.uk/petitions.json?state=with_response>
- 请愿700024：<https://petition.parliament.uk/petitions/700024.json>
- Open Government Licence v3.0：<https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>

项目工作目录中原15列处理表的SHA-256为
`69FB38F6CB2593A6B1AB7602D5D1C68009B08C170C5D59AD21BF908CA724B75B`。
本目录两列最小发布表的SHA-256为
`F88BE53E79989B755106C406C5311E41559930AEB58BBFC8A2A56BCB319692BC`。

## 样本口径

API查询得到357条带政府回应记录；固定窗口要求达到10,000签名的时间位于
2024-07-01（含）至2026-01-01（不含），并且门槛与回应时间均完整，最终为222条。
因此，它是“条件于已观察到政府回应”的时延样本，不能用来估计所有请愿获得回应的概率。

时延定义为：

`response_delay_days = (government_response_at - threshold_reached_at) / 24小时`

复核统计为：最小6.21天、P5 11.07天、中位数21.65天、均值24.41天、P95
56.52天、最大128.01天。700024为21.793天。

## 模型中的用法

固定时延情景取3、11、22和57天；经验重抽样情景从222个时延中按随机种子抽取
一个值并四舍五入为至少1个完整日。同一随机种子的全部21个α共用同一抽样值，
抽样随机流与模型随机流分离。

10,000和100,000是真实制度门槛。默认`observed_calendar`模式只按真实里程碑日触发，
不会把10,000换算为300名智能体中的某个比例。`synthetic_unique_support`模式使用独立的
模拟支持比例门槛，仅用于反事实实验。
