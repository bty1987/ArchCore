# Customer OS Research & PRD

这是一套基于 2026 年公开资料整理的中小企业 Customer OS / Conversational CRM 产品研究资料。

## 文档

1. `01_竞品拆解与商业模式.md`
   - 尘锋
   - 微盛
   - 销售易
   - Manychat
   - WATI
   - respond.io
   - Intercom
   - 获客、客户群、定价、SaaS、服务、AI、可复刻能力

2. `02_产品定位与商业模式.md`
   - 产品定位
   - 目标客户
   - Freemium
   - SaaS 定价
   - AI 收费
   - 服务收费
   - Partner 模式
   - 获客策略

3. `03_PRD_MVP_v0.1.md`
   - MVP 产品需求
   - 用户角色
   - 信息架构
   - 数据对象
   - Inbox
   - Customer 360
   - Workflow
   - AI
   - API
   - MVP 验收标准

4. `04_技术架构与开发路线.md`
   - 多租户
   - Channel Adapter
   - AI Gateway
   - Workflow Engine
   - Event Model
   - Java 技术栈
   - Repository
   - 开发 Sprint

5. `05_复刻清单与90天路线图.md`
   - 可复刻功能优先级
   - 30/60/90 天路线
   - 商业验证
   - 定价实验
   - 壁垒设计

## 推荐阅读顺序

```text
竞品拆解
   ↓
产品定位
   ↓
MVP PRD
   ↓
技术架构
   ↓
90天路线图
```

## 重要原则

个人微信第三方 API 不应该成为产品核心依赖。

推荐：

`官方企业微信/WhatsApp/Meta/WebChat API > 第三方 Connector > UI Automation > 协议逆向`

产品核心资产应该是：

`Customer Data + Conversation + Workflow + AI + Templates`
