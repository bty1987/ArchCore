# Customer OS MVP PRD v0.1

> 产品代号：Customer OS  
> 版本：MVP 0.1  
> 目标：建立“渠道 → 会话 → 客户 → 自动化 → AI”的最小闭环。

---

# 1. 产品目标

让一个 5～20 人的小企业在 30 分钟内完成：

1. 注册企业
2. 创建员工
3. 连接一个客户渠道
4. 获得客户
5. 在统一 Inbox 中看到会话
6. 自动建立客户档案
7. 给客户打标签
8. 创建自动化 Workflow
9. 使用 AI 总结/回复
10. 分配给员工并完成跟进

---

# 2. MVP 用户角色

## Owner

- 企业设置
- 账单
- 成员
- 渠道
- 数据
- Workflow
- AI

## Manager

- 查看全部客户
- 分配客户
- 查看统计
- 管理 Workflow

## Agent

- 查看分配客户
- 回复客户
- 添加标签
- 创建跟进
- 使用 AI 助手

---

# 3. 信息架构

```text
Dashboard
├── Inbox
├── Contacts
├── Leads
├── Deals
├── Workflows
├── Campaigns
├── AI
├── Reports
└── Settings
    ├── Workspace
    ├── Members
    ├── Channels
    ├── Fields
    ├── Tags
    ├── API
    └── Billing
```

---

# 4. 核心对象

## Workspace

```text
id
name
plan
timezone
created_at
```

## User

```text
id
workspace_id
name
email
role
status
```

## Contact

```text
id
workspace_id
name
avatar
phone
email
source
owner_id
stage
last_contact_at
next_followup_at
created_at
```

## ContactField

```text
id
contact_id
field_key
value
```

## Tag

```text
id
workspace_id
name
color
```

## Conversation

```text
id
workspace_id
contact_id
channel_id
status
assigned_user_id
last_message_at
```

## Message

```text
id
conversation_id
sender_type
sender_id
content
content_type
metadata
created_at
```

## Channel

```text
id
workspace_id
type
name
status
credentials
```

## Workflow

```text
id
workspace_id
name
status
trigger
definition_json
```

## WorkflowExecution

```text
id
workflow_id
contact_id
status
started_at
finished_at
error
```

## AIConversation

```text
id
conversation_id
model
input_tokens
output_tokens
action
result
created_at
```

---

# 5. P0 功能

## 5.1 登录/注册

### 用户故事

> 作为老板，我希望快速注册企业并开始使用。

### 验收

- 邮箱/手机号注册
- 创建 Workspace
- 自动成为 Owner
- 默认创建基础字段
- 默认创建一个 Welcome Workflow

---

# 6. Inbox

## 页面

```text
┌────────────┬──────────────────────┬──────────────────┐
│ 会话列表    │ 当前聊天              │ 客户资料          │
│             │                      │                  │
│ 张三        │ 张三：你好           │ 张三             │
│ 李四        │ AI：您好...          │ 标签             │
│ 王五        │                      │ 商机阶段          │
│             │                      │ 历史跟进          │
│             │ [输入框]             │ AI总结            │
└────────────┴──────────────────────┴──────────────────┘
```

### 必须支持

- 未读
- 分配
- 标签
- 内部备注
- 回复
- AI 回复建议
- AI 总结
- Follow-up
- 搜索

---

# 7. Contacts

### 列表字段

- Name
- Channel
- Owner
- Tags
- Stage
- Last Contact
- Next Follow-up

### 筛选

- 标签
- Owner
- 来源
- 最近联系
- 阶段
- 自定义字段

---

# 8. Customer 360

客户详情：

```text
基本信息
标签
来源
负责人
会话
Timeline
Notes
Deals
Orders
AI Summary
Next Action
```

AI Summary 示例：

> 客户预算约 20,000 元，主要关注价格与交付周期。最近一次咨询发生在 3 天前，目前处于高意向阶段。建议今天进行二次跟进。

---

# 9. Workflow

## 触发器

MVP：

- Contact Created
- Message Received
- Tag Added
- Tag Removed
- Field Changed
- Conversation Closed
- Time Delay

## 条件

- Tag
- Field
- Channel
- Owner
- Stage

## Action

- Add Tag
- Remove Tag
- Assign User
- Send Message
- Add Note
- Create Task
- Wait
- AI Generate
- Webhook

---

# 10. Workflow 示例

## 新客户自动分配

```text
Message Received
       ↓
是否新客户？
       ↓
Yes
       ↓
添加 New Lead
       ↓
根据来源分配销售
       ↓
发送欢迎消息
       ↓
等待 1 天
       ↓
没有回复？
       ↓
创建 Follow-up Task
```

---

# 11. AI MVP

第一阶段不要做通用 AI Agent。

只做 5 件事：

### AI Summary

总结当前会话。

### Customer Summary

总结客户画像。

### Reply Suggestion

生成 3 个回复建议。

### Extract Fields

从聊天中提取：

- 预算
- 地区
- 产品
- 时间
- 需求
- 意向

### Next Action

给销售建议下一步。

---

# 12. AI Agent P1

允许企业配置：

```text
Agent Name
Knowledge Base
Tone
Business Rules
Tools
Handoff Rules
```

Agent 可以：

- 查客户
- 查订单
- 查询知识库
- 创建任务
- 修改客户字段
- 转人工

---

# 13. Channel Adapter

核心原则：

> 业务系统不直接依赖某个渠道。

统一接口：

```java
interface ChannelAdapter {

    ChannelType type();

    void connect();

    void disconnect();

    void sendText(String conversationId, String text);

    void sendImage(String conversationId, String url);

    void sendFile(String conversationId, String url);

    void handleWebhook(Object payload);
}
```

第一批：

```text
WebChatAdapter
WeComAdapter
WhatsAppAdapter
TelegramAdapter
EmailAdapter
```

个人微信：

```text
PersonalWeChatAdapter
```

作为实验性 Connector。

---

# 14. API

## Contacts

```http
GET /api/v1/contacts
POST /api/v1/contacts
GET /api/v1/contacts/{id}
PATCH /api/v1/contacts/{id}
```

## Conversations

```http
GET /api/v1/conversations
GET /api/v1/conversations/{id}
POST /api/v1/conversations/{id}/messages
```

## Workflow

```http
GET /api/v1/workflows
POST /api/v1/workflows
POST /api/v1/workflows/{id}/test
```

## Webhook

```http
POST /api/v1/webhooks/{channel}
```

---

# 15. 数据架构

```text
Channel
   ↓
Webhook/Event
   ↓
Message
   ↓
Conversation
   ↓
Contact
   ↓
Timeline
   ↓
Workflow
   ↓
AI
   ↓
Task / Deal
```

推荐：

- PostgreSQL
- Redis
- Object Storage
- Kafka/RabbitMQ（规模扩大后）
- OpenSearch（规模扩大后）
- LLM Gateway
- Vector DB（知识库阶段）

---

# 16. MVP 非目标

不做：

- 财务
- ERP
- 库存
- OA
- 完整营销自动化
- 私有化
- 大模型训练
- 自研个人微信协议
- 复杂 BI
- 多级代理体系

---

# 17. MVP 成功标准

上线 30 天：

- 100 个注册 Workspace
- 30 个 Activated Workspace
- 10 个付费 Workspace
- 50,000 条客户消息
- 10,000 个 Contact
- Workflow 执行成功率 > 99%
- AI Summary 成功率 > 98%
- 首次价值时间 < 30 分钟

---

# 18. 产品原则

### Principle 1

**Conversation first**

### Principle 2

**Automation before AI Agent**

### Principle 3

**AI must create an observable business result**

### Principle 4

**Channel independent**

### Principle 5

**Small business first**

### Principle 6

**Template before configuration**

### Principle 7

**Human handoff always exists**
