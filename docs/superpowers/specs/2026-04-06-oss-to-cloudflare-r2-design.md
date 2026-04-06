# OSS → Cloudflare R2 Migration Design

## Context

项目使用阿里云 OSS（bucket: `zuibite-api`，endpoint: `oss-cn-hongkong.aliyuncs.com`）存储前端仪表盘数据。`afterTrade/webOssUpdate.py` 每分钟上传 ~9 个 JSON 文件，前端通过 OSS 公开 URL 轮询读取。

Phase 1 已移除阿里云 ECS 依赖。Phase 2 将 OSS 迁移到 Cloudflare R2，彻底去除 `oss2` SDK。

## 目标

- 用 `boto3`（S3 兼容）替代 `oss2`
- R2 bucket 绑定自定义域名 `cdn.example.com`
- 前端 URL 从 `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` 切换到 `https://cdn.example.com`
- 保持 `oss_put_obj`/`oss_get_obj` 方法名不变，调用方零改动

## 数据流

```
afterTrade/webOssUpdate.py
  → FUNCTION_CLIENT.oss_put_obj(obj, "cQuant/{time}.json")
    → boto3 S3 client → R2 bucket (zuibite-api)
      → https://cdn.example.com/cQuant/{time}.json
        → 前端 3s/15min 轮询读取
```

## 后端改动

### settings.py — 新增 R2 配置

```python
# Cloudflare R2 (S3-compatible object storage)
r2_account_id: str = ""
r2_access_key_id: str = ""
r2_access_key_secret: str = ""
r2_bucket_name: str = "zuibite-api"
r2_public_domain: str = ""  # e.g. "https://cdn.example.com"
```

### infra_client.py — 替换存储实现

**导入替换：**
- 删除 `import oss2`
- 新增 `import boto3`

**`__init__` 存储初始化：**
```python
self.s3_client = boto3.client(
    's3',
    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_access_key_secret,
)
self.r2_bucket = settings.r2_bucket_name
```

当 `r2_account_id` 为空时，不初始化（设为 None），避免无 R2 配置时启动失败。

**方法实现（方法名不变）：**
```python
def oss_put_obj(self, obj, name):
    try:
        body = json.dumps(obj, ensure_ascii=False)
        self.s3_client.put_object(
            Bucket=self.r2_bucket, Key=name, Body=body,
            ContentType='application/json'
        )
    except Exception as e:
        print(e)

def oss_get_obj(self, name):
    try:
        resp = self.s3_client.get_object(Bucket=self.r2_bucket, Key=name)
        return json.loads(resp['Body'].read().decode('utf-8'))
    except Exception as e:
        print(e)
```

### updateSymbol/updateTradeSymbol.py

删除无用的 `import oss2`（死代码）。

## 依赖变更

`pyproject.toml`:
- 移除 `oss2`
- 新增 `boto3`

## 前端改动

全局替换 `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` → `https://cdn.example.com`

涉及文件：
- `react-front/src/work/constainers/Show.js` — 4 处数据 URL
- `react-front/src/work/tradingview_extra_js/tv_api.js` — 2 处测试数据 URL
- `react-front/src/work/components/OtherConfigModal.js` — 1 处音频 URL
- `react-front/src/index.ejs` — 1 处 Dll.js URL

注：前端将在独立任务中用 React 19 + TypeScript 重写。这里做最小字符串替换。

## 文档改动

CLAUDE.md：`infra_client.py` 描述中 "Aliyun OSS" → "Cloudflare R2 object storage"

## Cloudflare R2 配置（手动，非代码）

部署前需在 Cloudflare Dashboard 中：
1. 创建 R2 bucket（名称 `zuibite-api`）
2. 创建 API token（Object Read & Write 权限）
3. 绑定自定义域名 `cdn.example.com`（需要域名已在 Cloudflare DNS 管理）
4. 将 API token 信息填入 `.env`

## .env.example 新增

```
# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_ACCESS_KEY_SECRET=
R2_BUCKET_NAME=zuibite-api
R2_PUBLIC_DOMAIN=https://cdn.example.com
```

## 验证

1. 本地设置 R2 credentials，运行 `oss_put_obj({"test": 1}, "test.json")` 确认写入成功
2. 访问 `https://cdn.example.com/test.json` 确认公开读取
3. 前端访问新 URL 确认数据加载
4. `grep -r "oss2" --include="*.py" .` 返回空（除废弃的 webServer.py）
5. 所有测试通过
