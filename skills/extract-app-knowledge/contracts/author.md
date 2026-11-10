# 知识写作

正文语言遵守项目 `content_language`（缺省 `zh-CN`，可选 `en`）；业务与研发文件可显式记录同名字段，英文文件必须填写 `en`。交互语言、知识输出语言与源码编程语言分别处理。固定文件名、表头、枚举和 ID 不翻译；人读指南、AI 指令与协议标识不写入业务正文。

业务版按可回答主题组织，保持问题、适用条件、结论、失败与未知在同一可检索段落；不写源码路径、内部事实 ID 或未经确认的动机。研发版复用相同业务结论，补入口、接口、方法、数据副作用与证据定位。

默认 `full` 保留原文件结构。采用 `compact` 时，在项目根 `Code2KB工程配置.json` 声明；至少写概览、规则、问答，必要流程与范围合并到这些文件，不省略事实证据或四类问答自测。只有技术实现能完整定位规格方法时才可省略独立方法文件。详见 [知识写作与复核](../references/知识写作与复核.md)。

For English output, declare `content_language: en` in each business and engineering knowledge file. Use English for prose, question cases, topic metadata and unknowns. Use `Q:` for questions and `Applicability`, `Answer boundaries` and `Unverified outcomes` where those sections are needed.
