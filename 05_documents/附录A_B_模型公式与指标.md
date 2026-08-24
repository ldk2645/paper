# 附录A：模型公式、参数设定与逐步执行顺序

## A.1 版本边界与符号

本附录描述正式消融实验实际调用的全局信息池模型。所有公众面对同一个当步信息池，但推荐分数根据各自的议题偏好分别计算。

主要符号如下：

| 符号 | 含义 |
|---|---|
| \(i=1,\ldots,N\) | 公众智能体编号 |
| \(j\in\mathcal I_t\) | 时间步 \(t\) 信息池中的信息 |
| \(q=0,\ldots,M-1\) | 议题编号 |
| \(\mathbf P_{i,t}\) | 公众 \(i\) 的议题偏好向量 |
| \(q_j\) | 信息 \(j\) 所属议题 |
| \(h_{j,t}\) | 信息 \(j\) 当前热度 |
| \(a_j\) | 信息 \(j\) 的情绪强度 |
| \(e_i\) | 公众 \(i\) 的情绪易感性 |
| \(L_i\) | 公众 \(i\) 的数字素养 |
| \(C_{i,t}\) | 公众 \(i\) 的学习成本 |
| \(T_{i,t}\) | 公众 \(i\) 的政府信任 |
| \(O_{i,t}\) | 本步官方信息暴露比例 |
| \(A^{\mathrm{off}}_{i,t}\) | 本步议程外信息暴露比例 |
| \(E_{i,t}\) | 本步平均情绪暴露 |
| \(R_t\) | 本步政府回应效果 |
| \(\sigma(x)\) | Logistic 函数 \(1/(1+e^{-x})\) |
| \(\operatorname{clip}(x,0,1)\) | 将数值限制在 \([0,1]\) |

代码为防止指数溢出，先将 Logistic 函数的输入限制在 \([-35,35]\)，再计算 \(\sigma(x)\)。

## A.2 公众初始化

### A.2.1 议题偏好

模型包含四个议题：

\[
(\text{经济},\text{法治},\text{公共服务},\text{娱乐热点}).
\]

前三个议题属于政府议程，第四个属于议程外议题。每名公众的初始偏好从对称 Dirichlet 分布抽取：

\[
\mathbf P_{i,0}\sim
\operatorname{Dirichlet}(1,1,1,1),
\]

因此

\[
p_{iq,0}\geq 0,\qquad \sum_{q=0}^{3}p_{iq,0}=1.
\]

该设定用于产生异质但不预设群体类别的初始偏好，不是从调查数据估计得到的人群分类。

### A.2.2 情绪易感性

\[
e_i=
\operatorname{clip}
\left(
X_i,0,1
\right),
\qquad
X_i\sim \mathcal N(0.30,0.10^2).
\]

### A.2.3 数字素养

\[
L_i=
\operatorname{clip}
\left(
X_i,0,1
\right),
\qquad
X_i\sim \mathcal N(0.69,0.18^2).
\]

均值 0.69 数值上接近参考论文数字素养五点量表均值 \(3.46/5=0.692\)，但这只是启发式缩放，不是严格的最小—最大归一化或重新估计。

### A.2.4 初始政府信任

\[
T_{i,0}=
\operatorname{clip}
\left(
X_i,0,1
\right),
\qquad
X_i\sim \mathcal N(0.69,0.12^2).
\]

均值 0.69 来自参考论文政府信任均值 \(3.45/5=0.69\) 的简单缩放。标准差 0.12 是模型异质性设定，并非论文标准差 0.938 的直接换算。

### A.2.5 初始学习成本

定义居中化变量：

\[
z_G=2G-1,\qquad z_{L_i}=2L_i-1,
\]

其中数字政府水平 \(G=0.60\)，平台复杂度 \(X=0.50\)。初始学习成本为：

\[
\eta^C_{i,0}
=
0.10
+\beta_{G\rightarrow C}z_G
+\beta_{L\rightarrow C}z_{L_i}
+\beta_{G\times L\rightarrow C}z_Gz_{L_i}
+0.35X,
\]

\[
C_{i,0}=\sigma(\eta^C_{i,0}).
\]

具体系数为：

\[
\beta_{G\rightarrow C}=0.036,
\qquad
\beta_{L\rightarrow C}=-0.855,
\qquad
\beta_{G\times L\rightarrow C}=-0.125.
\]

其中前两个数值来自参考论文回归表；\(-0.125\) 是将论文表3高、低数字素养组斜率差 \(-0.1247\) 四舍五入后，用作交互项的模型化近似。它不应被表述为本项目重新估计的交互系数。

## A.3 信息生成

模型初始化时生成24条自发信息，之后每个时间步再生成4条自发信息。议题从四个议题中等概率抽取：

\[
q_j\sim \operatorname{DiscreteUniform}\{0,1,2,3\}.
\]

完整模型中，自发信息的情绪强度为：

\[
a_j\sim
\begin{cases}
\operatorname{Beta}(2,3), & q_j\in\{0,1,2\},\\[2mm]
\operatorname{Beta}(4,2), & q_j=3.
\end{cases}
\]

两类分布的期望分别为 \(0.40\) 和 \(2/3\)，由此形成议程外内容的情绪优势。所有新信息初始热度均为0。

政府每10步发布一条官方信息，发布条件为：

\[
t\bmod 10=0.
\]

官方议题按经济、法治、公共服务循环，官方信息情绪强度固定为0.15，初始热度同样为0。

构造函数在正式循环开始前生成24条初始自发信息；因此在 \(t=0\) 时，政府还会发布1条官方信息，并新增4条自发信息，然后平台才开始本步推荐。

## A.4 平台推荐公式

### A.4.1 热度压缩与归一化

先对每条信息的原始热度进行对数压缩：

\[
H_{j,t}=\ln(1+h_{j,t}).
\]

随后在当步整个信息池上计算最大值：

\[
H_t^{\max}=\max_{k\in\mathcal I_t}H_{k,t}.
\]

归一化热度为：

\[
\widehat H_{j,t}=
\begin{cases}
\dfrac{H_{j,t}}{H_t^{\max}}, & H_t^{\max}>0,\\[3mm]
0, & H_t^{\max}=0.
\end{cases}
\]

这里的运算顺序必须写成“先对每条信息计算 \(\ln(1+h)\)，再取这些对数值的最大值作为分母”。不能写成 \(\ln[(1+h)/h_{\max}]\)，也不能先对原始热度归一化再取对数。

正式模型采用统一共享的信息池，因此同一个时间步内，热度归一化分母 \(H_t^{\max}\) 对所有公众相同。

### A.4.2 偏好相似度

令 \(\mathbf e_{q_j}\) 为信息议题 \(q_j\) 的独热向量，则：

\[
S_{ij,t}
=
\frac{\mathbf P_{i,t}^{\mathsf T}\mathbf e_{q_j}}
{\|\mathbf P_{i,t}\|_2\|\mathbf e_{q_j}\|_2}
=
\frac{p_{i,q_j,t}}
{\|\mathbf P_{i,t}\|_2}.
\]

代码将偏好向量的二范数下限设为 \(10^{-12}\)，即实际分母为：

\[
\max\left(\|\mathbf P_{i,t}\|_2,10^{-12}\right).
\]

应区分两种归一化：

1. 偏好更新后使用一范数归一化，使各议题偏好之和为1；
2. 计算相似度时使用二范数作为余弦相似度分母。

二者不是同一个归一化步骤。

### A.4.3 推荐得分 \(F_{ij}\)

正式代码对应的完整括号层级为：

\[
\boxed{
F_{ij,t}
=
\left[
\alpha\,\widehat H_{j,t}
\right]
+
\left[
(1-\alpha)\,S_{ij,t}
\right]
}
\]

即：

\[
F_{ij,t}
=
\alpha
\left[
\frac{\ln(1+h_{j,t})}
{\max_{k\in\mathcal I_t}\ln(1+h_{k,t})}
\right]
+
(1-\alpha)
\left[
\frac{p_{i,q_j,t}}
{\|\mathbf P_{i,t}\|_2}
\right],
\]

其中第一项在最大热度信号为0时定义为0。

必须注意：

- \(\alpha\) 只乘归一化热度项；
- \(1-\alpha\) 只乘偏好相似度项；
- 两项相加后不再做第二次归一化；
- 不对 \(F_{ij}\) 在用户间、信息间或议题间再次标准化；
- 情绪强度不直接进入 \(F_{ij}\)，而是通过“情绪强度→互动概率→热度积累→后续推荐”间接影响排序。

代码额外加入

\[
\varepsilon_{ij}\sim U(0,10^{-10})
\]

作为数值并列时的随机破同分量。它只用于稳定地打破完全相同的分数，不构成理论推荐机制。

平台按 \(F_{ij,t}+\varepsilon_{ij}\) 从高到低推荐：

\[
K_t=\min(5,|\mathcal I_t|)
\]

条信息。进入推荐列表即视为发生一次注意力消费；互动不是“消费”的前提。

## A.5 互动概率与信任反馈

将政府来源记为 \(g_j=1\)，自发来源记为 \(g_j=0\)。信任居中值为：

\[
z_{T_i,t}=2T_{i,t}-1.
\]

来源反馈因子为：

\[
\phi_{ij,t}=
\begin{cases}
1+s z_{T_i,t}, & g_j=1,\\[1mm]
1-s z_{T_i,t}, & g_j=0,
\end{cases}
\]

其中 \(s=0.25\)。

公众 \(i\) 对推荐信息 \(j\) 的互动概率为：

\[
\pi_{ij,t}
=
\operatorname{clip}
\left(
e_i\,a_j\,\phi_{ij,t},
0,1
\right).
\]

互动结果服从：

\[
B_{ij,t}\sim\operatorname{Bernoulli}(\pi_{ij,t}).
\]

当 \(s=0.25\) 且 \(T_i\in[0,1]\) 时，来源反馈因子处于 \([0.75,1.25]\)。高信任提高对政府信息的互动倾向并降低对自发信息的互动倾向；低信任产生相反作用。

`No trust` 消融只令：

\[
s=0,
\]

因此 \(\phi_{ij,t}=1\)。信任状态仍正常更新和记录，并没有被固定为常数或从信任方程中删除。

## A.6 互动后的热度沉积

令 \(\mathcal R_{i,t}\) 为公众 \(i\) 的推荐列表，则互动后信息热度增加：

\[
h^{+}_{j,t}
=
h_{j,t}
+
\sum_{i=1}^{N}
B_{ij,t}\,
\mathbf 1(j\in\mathcal R_{i,t}).
\]

每次成功互动使对应信息热度增加1。注意力份额按推荐消费次数计算，而不是按互动次数或热度值计算。

## A.7 偏好漂移

对公众 \(i\)，统计本步推荐列表中各议题的消费次数：

\[
n_{iq,t}
=
\sum_{j\in\mathcal R_{i,t}}
\mathbf 1(q_j=q).
\]

主导议题为：

\[
d_{i,t}=\arg\max_q n_{iq,t}.
\]

代码采用 `argmax`，如果多个议题并列，选择编号最小的议题。

若同一议题连续至少4步成为主导议题，则公众偏好按下式更新：

\[
\widetilde{\mathbf P}_{i,t+1}
=
(1-\gamma)\mathbf P_{i,t}
+
\gamma\mathbf e_{d_{i,t}},
\qquad \gamma=0.03,
\]

随后归一化：

\[
\mathbf P_{i,t+1}
=
\frac{\widetilde{\mathbf P}_{i,t+1}}
{\sum_q\widetilde p_{iq,t+1}}.
\]

由于原偏好之和为1，上式理论上仍然和为1；代码再次归一化是数值安全措施。达到连续4步后，只要相同议题继续主导，此更新会在之后每一步继续发生。

`No drift` 消融令 \(\gamma=0\)。

## A.8 政府监测、回应排期与回应执行

### A.8.1 监测指标

令 \(A_{q,t}^{\mathrm{sp}}\) 表示本步来自自发信息且议题为 \(q\) 的消费次数，\(A_t\) 表示本步全部信息消费次数。代码使用：

\[
u_{q,t}=
\frac{A_{q,t}^{\mathrm{sp}}}{A_t}.
\]

分母是全部消费次数，而不是仅自发信息的消费次数。

代码实际遍历所有议题，并非只检查议程外议题。默认 `hard` 策略下，只要：

\[
u_{q,t}>0.15
\]

就为该议题安排回应。判断符号是严格大于，不包括等于0.15。

同一议题已有待执行回应时，不重复排期。默认延迟 \(\delta=3\)，故：

\[
t_{\mathrm{due}}=t+3.
\]

代码一般形式为 \(t+\max(1,\delta)\)，所以即使将延迟设为0，回应也最早在下一步执行。

三种代码支持的策略为：

- `hard`：任何超过阈值的议题均排期，正式实验采用；
- `selective`：只有政府议程内议题超过阈值才排期；
- `wait`：同一议题连续超过阈值达到3步后才排期。

### A.8.2 回应执行

回应在到期时间步的开始执行。对相同议题的全部自发信息：

\[
h_{j,t}\leftarrow \rho h_{j,t},
\qquad \rho=0.70.
\]

因此 `response_strength=0.70` 是“回应后保留70%的热度”，对应降低30%，不是降低70%。

若本步到期回应作用前后的总热度分别为 \(H_t^{\mathrm{before}}\) 和 \(H_t^{\mathrm{after}}\)，则：

\[
R_t=
\begin{cases}
\dfrac{H_t^{\mathrm{before}}-H_t^{\mathrm{after}}}
{H_t^{\mathrm{before}}},
& H_t^{\mathrm{before}}>0,\\[3mm]
0,&H_t^{\mathrm{before}}=0.
\end{cases}
\]

在默认 \(\rho=0.70\) 且存在正热度的情况下，\(R_t=0.30\)。

`No response` 消融令：

\[
\rho=1.
\]

排期和“已执行回应”计数仍然存在，但热度不再下降，且 \(R_t=0\)。因此该消融删除的是回应的实际热度压制和由有效回应带来的信任增益，不是删除政府监测程序。

## A.9 学习成本动态

本步公众的平均情绪暴露为：

\[
E_{i,t}
=
\frac{1}{K_t}
\sum_{j\in\mathcal R_{i,t}}a_j.
\]

学习成本潜在分数为：

\[
\eta^C_{i,t}
=
0.10
+0.036z_G
-0.855z_{L_i}
-0.125z_Gz_{L_i}
+0.35X
+0.20E_{i,t}.
\]

学习成本目标值为：

\[
C^*_{i,t}=\sigma(\eta^C_{i,t}).
\]

实际学习成本以速率 \(\tau_C=0.08\) 渐进逼近目标：

\[
\boxed{
C_{i,t+1}
=
\operatorname{clip}
\left[
C_{i,t}
+
0.08(C^*_{i,t}-C_{i,t}),
0,1
\right]
}
\]

等价地：

\[
C_{i,t+1}
=
\operatorname{clip}
\left[
0.92C_{i,t}+0.08C^*_{i,t},
0,1
\right].
\]

不能将更新式误写成 \(C_{i,t+1}=0.08(C^*_{i,t}-C_{i,t})\)，因为那会漏掉当前状态 \(C_{i,t}\)。

## A.10 政府信任动态

定义：

\[
z_{C_i,t+1}=2C_{i,t+1}-1.
\]

官方信息暴露比例为：

\[
O_{i,t}
=
\frac{1}{K_t}
\sum_{j\in\mathcal R_{i,t}}\mathbf 1(g_j=1),
\]

议程外信息暴露比例为：

\[
A^{\mathrm{off}}_{i,t}
=
\frac{1}{K_t}
\sum_{j\in\mathcal R_{i,t}}
\mathbf 1(q_j\notin\{0,1,2\}).
\]

信任潜在分数为：

\[
\eta^T_{i,t}
=
0.80
-0.086z_G
-0.766z_{C_i,t+1}
+0.45(O_{i,t}-0.25)
+0.75R_t
-0.60A^{\mathrm{off}}_{i,t}.
\]

信任目标值为：

\[
T^*_{i,t}=\sigma(\eta^T_{i,t}).
\]

信任以速率 \(\tau_T=0.06\) 更新：

\[
\boxed{
T_{i,t+1}
=
\operatorname{clip}
\left[
T_{i,t}
+
0.06(T^*_{i,t}-T_{i,t}),
0,1
\right]
}
\]

等价地：

\[
T_{i,t+1}
=
\operatorname{clip}
\left[
0.94T_{i,t}+0.06T^*_{i,t},
0,1
\right].
\]

代码在同一时间步先更新学习成本，再使用已经更新的 \(C_{i,t+1}\) 计算信任目标。这一层级不应写成用旧学习成本 \(C_{i,t}\) 更新信任。

参考论文移植的信任相关系数为：

\[
\beta_{G\rightarrow T}=-0.086,
\qquad
\beta_{C\rightarrow T}=-0.766.
\]

截距0.80、官方暴露系数0.45、官方暴露中心0.25、回应效果系数0.75和议程外暴露系数 \(-0.60\) 均为模型实现系数，不是参考论文回归结果。

## A.11 热度衰减与清理

每步记录指标后，信息热度按下式衰减：

\[
h_{j,t+1}=0.95h^+_{j,t}.
\]

衰减后保留信息的条件为：

\[
h_{j,t+1}\geq 0.01
\quad\text{或}\quad
t-\operatorname{created\_at}_j<1.
\]

因此新建信息在出生当步即使热度仍为0也不会被删除；到下一时间步结束时，如果仍未积累足够热度，则会被清理。

## A.12 单个时间步的精确执行顺序

正式代码每一步严格按以下顺序运行：

1. 政府检查是否到达定期发布时间，并发布官方信息；
2. 执行所有已到期的政府回应，计算本步回应效果 \(R_t\)；
3. 生成4条新的自发信息；
4. 从当前统一信息池提取议题、情绪和来源数组；
5. 计算归一化热度、偏好相似度和 \(F_{ij}\)，生成推荐列表；
6. 统计所有推荐消费形成的议题注意力；
7. 按互动概率抽样，给成功互动的信息累加热度；
8. 根据本步主导消费议题更新偏好漂移；
9. 计算议程份额、议程偏离度和风暴状态；
10. 政府根据本步自发信息注意力安排未来回应；
11. 先更新学习成本，再更新政府信任；
12. 记录本步全部指标；
13. 执行热度衰减并清理低热度信息；
14. 最后一步结束后关闭仍处于持续状态的风暴事件，并生成汇总结果。

特别需要指出：代码是“先监测并排期回应，再更新学习成本和信任”；本步新排期的回应不会在本步立即执行。

## A.13 参数表与设定性质

| 参数 | 正式默认值 | 含义 | 设定性质或依据 |
|---|---:|---|---|
| `alpha` | 基准0.50；正式扫描0.00–1.00，步长0.05 | 热度项权重 | 核心实验变量 |
| `steps` | 300 | 每次模拟步数 | 正式实验协议 |
| `population_size` | 300 | 公众数量 | 研究设计情景值 |
| `topic_names` | 经济、法治、公共服务、娱乐热点 | 四个议题 | 研究设计分类 |
| `agenda_topic_indices` | 0、1、2 | 政府议程集合 | 研究设计分类 |
| `attention_budget` | 5 | 每人每步最多消费数 | 注意力稀缺的实现假设 |
| `initial_information` | 24 | 初始自发信息数 | 研究设计情景值 |
| `spontaneous_posts_per_step` | 4 | 每步新增自发信息数 | 研究设计情景值 |
| `preference_concentration` | 1.0 | Dirichlet各维浓度 | 对称异质性假设 |
| `emotionality_mean` | 0.30 | 情绪易感性均值 | 实现假设 |
| `emotionality_sd` | 0.10 | 情绪易感性标准差 | 实现假设 |
| `preference_drift_after` | 4 | 触发漂移的连续步数 | 机制情景值 |
| `preference_drift_rate` | 0.03 | 偏好漂移速率 | 机制情景值；消融为0 |
| `heat_decay` | 0.95 | 每步热度保留率 | PRD/研究设计值，不是经验估计 |
| `minimum_heat` | 0.01 | 清理阈值 | 数值与生命周期设定 |
| `official_emotional_intensity` | 0.15 | 官方信息情绪强度 | 低情绪官方内容假设 |
| `publish_interval` | 10 | 政府发布间隔 | 研究设计情景值 |
| `response_threshold` | 0.15 | 回应排期阈值 | 研究设计情景值 |
| `response_strength` | 0.70 | 回应后热度保留比例 | 研究设计值；消融为1.0 |
| `response_delay` | 3 | 回应延迟步数 | PRD/研究设计值 |
| `response_strategy` | `hard` | 默认回应策略 | 正式实验策略 |
| `wait_observation_steps` | 3 | 观望策略所需连续步数 | 仅 `wait` 策略使用 |
| `agenda_target_share` | 0.70 | 议程目标份额 | 指标基准设定 |
| `storm_threshold` | 0.30 | 风暴判定阈值 | 结果分类设定 |
| `digital_government_level` | 0.60 | 数字政府环境水平 | 接近论文均值 \(2.97/5\) 的启发式锚点 |
| `digital_platform_complexity` | 0.50 | 平台复杂度 | 中性情景假设 |
| `digital_literacy_mean` | 0.69 | 数字素养均值 | 接近论文 \(3.46/5\) |
| `digital_literacy_sd` | 0.18 | 数字素养异质性 | 实现假设，不是论文SD直接换算 |
| `initial_trust_mean` | 0.69 | 初始信任均值 | 论文 \(3.45/5\) 的简单缩放 |
| `initial_trust_sd` | 0.12 | 初始信任异质性 | 实现假设，不是论文SD直接换算 |
| `learning_update_rate` | 0.08 | 学习成本逼近速度 | 动态惯性设定 |
| `trust_update_rate` | 0.06 | 信任逼近速度 | 动态惯性设定 |
| `trust_feedback_strength` | 0.25 | 信任对互动的反馈强度 | 模型反馈设定；消融为0 |
| `seed` | 类默认42；正式73000–73049 | 随机种子 | 可复现性控制 |
| \(\beta_{G\rightarrow T}\) | −0.086 | 数字政府→信任 | 参考论文表2 |
| \(\beta_{C\rightarrow T}\) | −0.766 | 学习成本→信任 | 参考论文表2 |
| \(\beta_{G\rightarrow C}\) | 0.036 | 数字政府→学习成本 | 参考论文表2 |
| \(\beta_{L\rightarrow C}\) | −0.855 | 数字素养→学习成本 | 参考论文表2 |
| \(\beta_{G\times L\rightarrow C}\) | −0.125 | 调节项近似 | 论文表3斜率差−0.1247的操作化近似 |

下列常数写在更新公式中，不是独立配置项：

| 常数 | 数值 | 作用 | 性质 |
|---|---:|---|---|
| 学习成本截距 | 0.10 | 学习成本潜在分数基线 | 实现系数 |
| 平台复杂度系数 | 0.35 | 复杂度对学习成本的作用 | 实现系数 |
| 情绪暴露系数 | 0.20 | 情绪暴露对学习成本的作用 | 实现系数 |
| 信任截距 | 0.80 | 信任潜在分数基线 | 实现系数 |
| 官方暴露系数 | 0.45 | 官方暴露对信任的作用 | 实现系数 |
| 官方暴露中心 | 0.25 | \(O_i-0.25\) 的参照点 | 实现基准 |
| 回应效果系数 | 0.75 | 有效回应对信任的作用 | 实现系数 |
| 议程外暴露系数 | −0.60 | 议程外暴露对信任的作用 | 实现系数 |
| Logistic输入边界 | ±35 | 防止指数溢出 | 数值安全措施 |
| 偏好范数下限 | \(10^{-12}\) | 防止除零 | 数值安全措施 |
| 推荐破同分噪声 | \(U(0,10^{-10})\) | 打破完全并列 | 数值安全措施 |

只有参考论文的五个关系系数和三个描述性均值锚点具有文献依据。其他截距、暴露系数、更新率、阈值、分布标准差及过程参数属于研究设计或实现先验，不能称为经验估计或因果效应复现。

## A.14 正式消融条件

| 条件 | 代码操作 | 保持不变的部分 |
|---|---|---|
| `full` | 情绪优势开启，\(\gamma=0.03,\rho=0.70,s=0.25\) | 完整模型 |
| `no_emotion` | 所有自发信息均改用 \(\operatorname{Beta}(2,3)\) | 公众情绪易感性、互动公式仍保留 |
| `no_drift` | `preference_drift_rate=0` | 主导议题和连续步数仍可计算 |
| `no_response` | `response_strength=1.0` | 监测、排期和执行计数仍保留 |
| `no_trust` | `trust_feedback_strength=0` | 信任目标、信任更新和信任结果仍保留 |

正式设计包含21个 \(\alpha\) 水平和50个共同随机种子。原四条件运行数为：

\[
4\times21\times50=4200.
\]

`No trust` 后续新增：

\[
1\times21\times50=1050.
\]

五条件合并后总计：

\[
5\times21\times50=5250.
\]

同一随机种子在所有 \(\alpha\) 和所有条件中配对使用。

---

# 附录B：指标定义、记录时点与正式统计

## B.1 注意力计数

令：

\[
A_{q,t}
=
\sum_{i=1}^{N}
\sum_{j\in\mathcal R_{i,t}}
\mathbf 1(q_j=q)
\]

为议题 \(q\) 的消费次数，总注意力为：

\[
A_t=\sum_q A_{q,t}.
\]

所有份额均以“被推荐并消费的次数”为基础，不以信息条数、热度或成功互动次数为基础。

## B.2 逐时间步记录指标

| 字段 | 精确定义 | 记录时点 |
|---|---|---|
| `step` | 当前时间步 \(t\) | 每步 |
| `alpha` | 本次运行的推荐热度权重 | 每步 |
| `agenda_share` | \(\sum_{q\in\{0,1,2\}}A_{q,t}/A_t\) | 消费与互动后 |
| `agenda_divergence` | \(\operatorname{clip}[1-\text{agenda\_share}/0.70,0,1]\) | 消费与互动后 |
| `official_attention_share` | \(\frac1N\sum_i O_{i,t}\) | 消费后 |
| `off_agenda_peak_share` | \(\max_{q\notin\{0,1,2\}}A_{q,t}/A_t\) | 消费后 |
| `storm` | \(\mathbf1(\text{off\_agenda\_peak\_share}>0.30)\) | 消费后 |
| `mean_trust` | \(\frac1N\sum_iT_{i,t+1}\) | 本步信任更新后 |
| `trust_p10` | 本步更新后个体信任的10%分位数 | 信任更新后 |
| `trust_p90` | 本步更新后个体信任的90%分位数 | 信任更新后 |
| `mean_learning_cost` | \(\frac1N\sum_iC_{i,t+1}\) | 学习成本更新后 |
| `total_interactions` | \(\sum_{ij}B_{ij,t}\) | 互动抽样后 |
| `pool_size` | 当前信息池对象数量 | 本步衰减与清理前 |
| `responses_scheduled` | 本步新安排的回应数 | 监测后 |
| `responses_executed` | 本步开始时执行的到期回应数 | 政府行动后 |
| `response_effect` | 本步到期回应造成的相对热度下降 \(R_t\) | 回应执行后 |
| `topic_share_q_name` | \(A_{q,t}/A_t\) | 消费后 |

若总注意力 \(A_t=0\)，议程份额、官方注意力份额、议程外峰值份额和各议题份额均记为0。

需要区分：

- `agenda_share` 按议题归属统计；自发信息只要属于经济、法治或公共服务，也计入政府议程；
- `official_attention_share` 按信息来源统计；
- 两者不是同一个指标。

## B.3 议程偏离度

\[
D_t=
\operatorname{clip}
\left(
1-\frac{G_t}{0.70},
0,1
\right),
\]

其中 \(G_t\) 为 `agenda_share`。

当 \(G_t\geq0.70\) 时，\(D_t=0\)。因此该指标只衡量“低于目标的相对缺口”，不能反映政府议程份额超过70%的程度。

## B.4 风暴事件记录

设：

\[
S_t=\mathbf1(P_t^{\mathrm{off}}>0.30),
\]

其中 \(P_t^{\mathrm{off}}\) 为 `off_agenda_peak_share`。

一个风暴事件是 \(S_t=1\) 的最大连续时间段。每个事件记录：

| 字段 | 定义 |
|---|---|
| `start_step` | 连续风暴开始步 |
| `end_step` | 连续风暴最后一步 |
| `duration` | 风暴步数，即 `end_step-start_step+1` |
| `peak_share` | 该完整事件期间最大的议程外峰值份额 |

模拟最后一步仍处于风暴状态时，代码会在运行结束后主动关闭并保存该事件。

## B.5 稳态汇总窗口

正式运行300步，汇总窗口为最后100步。一般形式为：

\[
W=\min(100,\text{实际运行步数}).
\]

若运行300步，则稳态窗口为 \(t=200,\ldots,299\)。

## B.6 单次运行汇总指标

| 汇总字段 | 精确定义 |
|---|---|
| `alpha` | 本次运行的 \(\alpha\) |
| `seed` | 本次运行随机种子 |
| `steps` | 实际运行步数 |
| `population_size` | 公众数量 |
| `mean_agenda_divergence` | 最后 \(W\) 步 \(D_t\) 的算术平均 |
| `system_stability` | 最后 \(W\) 步 \(D_t\) 的总体方差，`ddof=0` |
| `mean_agenda_share` | 最后 \(W\) 步 `agenda_share` 均值 |
| `mean_official_attention_share` | 最后 \(W\) 步官方注意力份额均值 |
| `mean_trust` | 最后 \(W\) 步逐步公众平均信任的时间均值 |
| `mean_learning_cost` | 最后 \(W\) 步逐步公众平均学习成本的时间均值 |
| `storm_count` | 与最后 \(W\) 步有任何重叠的完整风暴事件数 |
| `storm_frequency_per_100_steps` | `storm_count/W×100` |
| `storm_time_share` | 最后 \(W\) 步 `storm` 指示量均值 |
| `storm_mean_peak` | 与窗口重叠的风暴事件完整 `peak_share` 均值 |
| `storm_max_peak` | 与窗口重叠的风暴事件完整峰值最大值 |
| `storm_mean_duration` | 与窗口重叠的风暴事件完整持续时间均值 |
| `full_run_storm_count` | 全部运行期间的风暴事件数 |
| `full_run_storm_frequency_per_100_steps` | 全程事件数/总步数×100 |
| `full_run_storm_time_share` | 全程处于风暴状态的时间比例 |
| `responses_scheduled` | 全程累计安排回应数 |
| `responses_executed` | 全程累计执行回应数 |
| `total_interactions` | 全程成功互动总数 |
| `final_pool_size` | 最后一次衰减和清理后的信息池大小 |

`system_stability` 在代码中实际是议程偏离度方差。数值越大表示后期波动越强，不能将较大的值解释为“更稳定”。即使方差很小，系统也可能稳定地停留在高偏离状态，因此必须与 `mean_agenda_divergence` 联合解释。

另一个需要披露的实现细节是：只要风暴事件与最后100步发生重叠，`storm_mean_peak` 和 `storm_mean_duration` 使用该事件的完整峰值和完整持续时间；如果事件在窗口前开始，其窗口外部分也包含在事件级峰值和持续时间中。

## B.7 正式原始运行表的识别字段

除上述单次运行汇总指标外，正式原始 CSV 还记录：

| 字段 | 含义 |
|---|---|
| `analysis_status` | 正式分析版本标识 |
| `condition_id` | 条件编号 |
| `condition_order` | 条件排序 |
| `condition_label` | 条件名称 |
| `removed_mechanism` | 被移除机制 |
| `emotion_advantage_enabled` | 情绪优势开关 |
| `preference_drift_rate` | 该条件漂移速率 |
| `response_strength` | 该条件回应热度保留率 |
| `trust_feedback_strength` | 该条件信任反馈强度 |
| `replicate` | 重复序号0–49 |
| `seed` | 随机种子73000–73049 |
| `alpha` | 当前扫描水平 |
| `elapsed_seconds` | 单次模拟耗时 |

原四条件运行器还保存 `run_signature` 和 `configuration_sha256`；`No trust` 独立运行器保存完整配置 JSON 和单独的清单文件。五条件合并表保留两套结果共同拥有的字段，代码及清单文件哈希应与合并结果一起归档。

## B.8 跨随机种子的条件汇总

对每个“条件×\(\alpha\)×指标”单元的50次运行，计算：

\[
\bar Y=\frac1{50}\sum_{r=1}^{50}Y_r,
\]

\[
s_Y=
\sqrt{
\frac{1}{49}
\sum_{r=1}^{50}(Y_r-\bar Y)^2
},
\qquad
SE=\frac{s_Y}{\sqrt{50}}.
\]

均值的95% \(t\) 区间为：

\[
\bar Y\pm t_{0.975,49}SE.
\]

正式分析的四项主要指标为：

1. `mean_agenda_divergence`；
2. `system_stability`；
3. `storm_time_share`；
4. `mean_trust`。

## B.9 临界点识别

对每个条件，先在每个 \(\alpha\) 上计算50个种子的平均议程偏离度曲线 \(\bar D(\alpha)\)，再进行三点居中移动平均。内部点可写为：

\[
\widetilde D(\alpha_\ell)
=
\frac{
\bar D(\alpha_{\ell-1})
+\bar D(\alpha_\ell)
+\bar D(\alpha_{\ell+1})
}{3}.
\]

在等间隔网格上计算数值梯度：

\[
g_\ell
=
\frac{
\widetilde D(\alpha_{\ell+1})
-\widetilde D(\alpha_{\ell-1})
}{
2\Delta\alpha
},
\qquad \Delta\alpha=0.05.
\]

候选临界点为内部网格点中最大正梯度对应的 \(\alpha\)：

\[
\alpha_c
=
\arg\max_{\alpha_\ell,\;1\leq\ell\leq19}
g_\ell.
\]

若整条曲线的范围小于0.015，或最大内部梯度不为正，则不识别临界点。

临界点95%区间使用5000次“种子整条曲线”区组 Bootstrap：每次以种子为单位有放回抽样，同时保留该种子在全部21个 \(\alpha\) 水平的完整轨迹，再重新识别临界点。区间端点采用 Bootstrap 临界点分布的2.5%和97.5%分位数，并落在实际扫描网格上。

正式代码是5000次临界点 Bootstrap，不是1000次。

## B.10 配对消融效应

对同一 \(\alpha\)、同一随机种子 \(r\)，消融效应定义为：

\[
d_r
=
Y_{r,\mathrm{ablation}}
-
Y_{r,\mathrm{full}}.
\]

因此：

- \(d_r>0\)：消融条件指标高于完整模型；
- \(d_r<0\)：消融条件指标低于完整模型。

平均差为：

\[
\bar d=\frac1n\sum_{r=1}^{n}d_r,
\qquad n=50.
\]

配对标准化效应量为：

\[
d_z=\frac{\bar d}{s_d}.
\]

Hedges校正效应量为：

\[
g_z=
\left(
1-\frac{3}{4n-5}
\right)d_z.
\]

每项比较同时输出：

- 平均差与中位数差；
- 差值标准差和标准误；
- 配对 \(t\) 检验及其区间；
- Wilcoxon符号秩检验；
- 秩二列相关；
- Cohen \(d_z\)；
- Hedges \(g_z\) 及其 Bootstrap 区间；
- 10000次配对种子 Bootstrap 均值差95%区间。

在完整模型临界 \(\alpha\) 处，另进行99999次双侧符号翻转检验。Monte Carlo \(P\) 值计算为：

\[
p=
\frac{
\#\{|\bar d^{(b)}|\geq|\bar d|\}+1
}{
B+1
},
\qquad B=99999.
\]

临界点处各消融×四项指标的 \(P\) 值执行全局 Holm 校正。全 \(\alpha\) 的配对检验还在每个指标内部进行 Holm 校正。

## B.11 跨 \(\alpha\) 曲线面积

对每个种子和每项指标，使用21个 \(\alpha\) 水平进行梯形积分：

\[
\operatorname{AUC}_r
=
\sum_{\ell=0}^{19}
\frac{
Y_r(\alpha_\ell)+Y_r(\alpha_{\ell+1})
}{2}
(\alpha_{\ell+1}-\alpha_\ell).
\]

AUC消融差仍定义为：

\[
d_r^{\mathrm{AUC}}
=
\operatorname{AUC}_{r,\mathrm{ablation}}
-
\operatorname{AUC}_{r,\mathrm{full}}.
\]

AUC比较使用与临界点主要比较相同的配对统计、10000次 Bootstrap、99999次符号翻转检验和全局 Holm 校正。

## B.12 解释边界

上述指标和统计量用于识别模型内部动态及机制依赖。它们不是现实世界的因果效应估计，也不能直接换算成现实调查问卷的百分点。参考论文系数在本模型中进入 Logistic 潜在分数和动态逼近方程，其作用是保留关系方向和相对强度，而不是复现原论文的静态回归模型。

---

## 代码核对位置与审计留痕

当前发布包中可直接核对的冻结模型为：

- `../01_model_core/model.py`

该文件与正式运行所用原始冻结模型逐字节一致，SHA-256 为：

`AB78E6C64AFB6FD487E40A48FBBCD1B09A84EE3FBC9085530F8833DE3543D7EC`

在该冻结模型中，关键函数及原始行号如下：

- 模型默认参数：第33–75行；
- 参数边界检查：第77–116行；
- 公众偏好、情绪易感性、数字素养、初始信任初始化：第182–231行；
- 初始学习成本：第233–246行；
- 信息生成和情绪分布：第248–288行；
- 政府发布、到期回应与回应效果：第290–339行；
- 热度压缩、归一化、相似度和 \(F_{ij}\)：第357–390行；
- 注意力、互动概率、热度沉积与偏好漂移：第392–488行；
- 学习成本和政府信任更新：第490–532行；
- 政府监测和回应排期：第534–581行；
- 风暴事件：第583–621行；
- 热度衰减和清理：第623–631行；
- 完整时间步顺序和逐步记录字段：第653–745行；
- 稳态汇总指标：第761–821行。

正式运行与统计分析脚本按原相对结构冻结在发布包中：

- `../02_experiment_code/formal_ablation_frozen/原始版本/formal_ablation_n50_nonspatial/run_formal_ablation.py`
  - 正式 \(\alpha\) 与种子：第44–45行；
  - 原四条件：第46–83行；
  - 正式情绪开关：第86–104行；
  - 条件配置覆盖：第158–168行；
  - 结果写入：第171–198行；
  - 共同种子任务生成：第259–268行。
- `../02_experiment_code/formal_ablation_frozen/model_validation_round3/src/run_no_trust.py`
  - `No trust` 操作定义：第68–94行。
- `../02_experiment_code/formal_ablation_frozen/原始版本/formal_ablation_n50_nonspatial/analyze_formal_ablation.py`
  - 四项主要指标：第21–37行；
  - 临界点算法：第63–85行、第239–301行；
  - 配对统计、效应量与 Bootstrap：第88–236行；
  - 条件汇总：第304–335行；
  - 全 \(\alpha\) 配对效应与 Holm 校正：第338–411行；
  - AUC 效应：第414–468行。
- `../02_experiment_code/formal_ablation_frozen/model_validation_round3/src/analyze_five_conditions.py`
  - 五条件合并与重新分析：第75–110行。

另外两份正式运行脚本的 SHA-256 为：

- `run_formal_ablation.py`：`623E4F37C93A2CAED89EE9A4E358012BB449B6FB1423A709BCBF2442B2037BBC`
- `run_no_trust.py`：`50D2AEC51A3A1F6781357C2BE63700A8B92A8649343B89499BE7F2455368B032`

## 正文同步解释时必须保持一致的事项

1. 正式代码的监测对象是所有议题的自发信息注意力，不是只监测议程外议题。
2. `response_strength=0.70` 表示保留70%、降低30%。
3. 信任目标使用本步已更新的学习成本。
4. 实际顺序是先监测排期，再更新学习成本和信任。
5. 逐步指标在衰减清理前记录；`final_pool_size` 才是最终衰减清理后的大小。
6. 正式临界点 Bootstrap 为5000次；消融区间为10000次；符号翻转为99999次。
7. `system_stability` 实际是偏离度方差，数值越大代表波动越大。
8. `No response` 和 `No trust` 都只删除指定反馈箭头，其他状态和记录仍保留。
9. 论文均值是简单除以5形成的启发式锚点，不应称作严格归一化或现实校准。
