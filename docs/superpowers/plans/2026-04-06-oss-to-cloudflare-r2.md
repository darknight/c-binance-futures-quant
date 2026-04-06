# OSS → Cloudflare R2 Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Aliyun OSS (`oss2`) with Cloudflare R2 (`boto3` S3-compatible API), keeping method names unchanged so all callers require zero changes.

**Architecture:** Add R2 config fields to `Settings`. Replace `import oss2` with `import boto3` in `infra_client.py`, rewrite the storage init and two methods (`oss_put_obj`/`oss_get_obj`). Update frontend URLs from OSS to R2 custom domain. Remove `oss2` dependency.

**Tech Stack:** boto3, pydantic-settings, pytest, Cloudflare R2

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `settings.py` | Modify | Add R2 config fields |
| `infra_client.py` | Modify | Replace oss2 with boto3 |
| `updateSymbol/updateTradeSymbol.py` | Modify | Delete dead `import oss2` |
| `pyproject.toml` | Modify | Remove `oss2`, add `boto3` |
| `.env.example` | Modify | Add R2 env vars |
| `react-front/src/work/constainers/Show.js` | Modify | Update 4 OSS URLs |
| `react-front/src/work/tradingview_extra_js/tv_api.js` | Modify | Update 2 OSS URLs |
| `react-front/src/work/components/OtherConfigModal.js` | Modify | Update 1 OSS URL |
| `react-front/src/index.ejs` | Modify | Update 1 OSS URL |
| `CLAUDE.md` | Modify | Update InfraClient description |
| `tests/test_settings.py` | Modify | Add R2 fields test |
| `tests/test_infra_client.py` | Modify | Add boto3/no-oss2 tests |

---

### Task 1: Add R2 Config to Settings

**Files:**
- Modify: `settings.py`
- Modify: `.env.example`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Add failing test for R2 settings fields**

Append to `tests/test_settings.py` (before `_make_settings` helper):

```python
def test_settings_has_r2_fields():
    """R2 storage fields exist with correct defaults."""
    s = _make_settings()
    assert s.r2_account_id == ""
    assert s.r2_access_key_id == ""
    assert s.r2_access_key_secret == ""
    assert s.r2_bucket_name == "zuibite-api"
    assert s.r2_public_domain == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::test_settings_has_r2_fields -v`
Expected: FAIL — `Settings` has no `r2_account_id` field.

- [ ] **Step 3: Add R2 fields to settings.py**

In `settings.py`, add after the `second_open_hosts` line (before `model_config`):

```python
    # Cloudflare R2 (S3-compatible object storage)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_access_key_secret: str = ""
    r2_bucket_name: str = "zuibite-api"
    r2_public_domain: str = ""  # e.g. "https://cdn.example.com"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Update .env.example**

Append to `.env.example`:

```
# Cloudflare R2 (S3-compatible object storage)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_ACCESS_KEY_SECRET=
R2_BUCKET_NAME=zuibite-api
R2_PUBLIC_DOMAIN=https://cdn.example.com
```

- [ ] **Step 6: Commit**

```bash
git add settings.py .env.example tests/test_settings.py
git commit -m "feat: add Cloudflare R2 config fields to settings"
```

---

### Task 2: Replace oss2 with boto3 in InfraClient

**Files:**
- Modify: `infra_client.py`
- Modify: `tests/test_infra_client.py`

- [ ] **Step 1: Add failing tests for boto3 migration**

Append to `tests/test_infra_client.py`:

```python
def test_infra_client_has_no_oss2_import():
    """infra_client.py should not import oss2."""
    import inspect
    import importlib
    import infra_client as mod
    importlib.reload(mod)
    source = inspect.getsource(mod)
    assert "import oss2" not in source


def test_infra_client_uses_boto3():
    """infra_client.py should import boto3."""
    import inspect
    import importlib
    import infra_client as mod
    importlib.reload(mod)
    source = inspect.getsource(mod)
    assert "import boto3" in source


def test_infra_client_has_s3_client_when_configured(monkeypatch):
    """InfraClient should init boto3 S3 client when R2 is configured."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("R2_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("R2_ACCESS_KEY_SECRET", "test-secret")
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    import infra_client as infra_mod
    importlib.reload(infra_mod)
    client = infra_mod.InfraClient(larkMsgSymbol="test")
    assert client.s3_client is not None
    assert client.r2_bucket == "zuibite-api"


def test_infra_client_no_s3_client_when_not_configured(monkeypatch):
    """InfraClient should set s3_client to None when R2 is not configured."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("R2_ACCOUNT_ID", "")
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    import infra_client as infra_mod
    importlib.reload(infra_mod)
    client = infra_mod.InfraClient(larkMsgSymbol="test")
    assert client.s3_client is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_infra_client.py -v`
Expected: 4 new tests FAIL — `oss2` still imported, no `boto3`, no `s3_client` attribute.

- [ ] **Step 3: Replace oss2 import with boto3**

In `infra_client.py`, change line 7:

```python
# OLD:
import oss2

# NEW:
import boto3
```

- [ ] **Step 4: Replace storage init in __init__**

In `infra_client.py`, replace lines 42-46:

```python
        # TODO(Phase 2): Re-enable OSS init after aliyun_api_key/aliyun_api_secret
        # are replaced with a new OSS-specific config approach.
        # oss_auth = oss2.Auth(settings.aliyun_api_key, settings.aliyun_api_secret)
        # self.oss_bucket = oss2.Bucket(oss_auth, 'http://oss-cn-hongkong.aliyuncs.com', 'zuibite-api')
        self.oss_bucket = None
```

With:

```python
        if settings.r2_account_id:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_access_key_secret,
            )
            self.r2_bucket = settings.r2_bucket_name
        else:
            self.s3_client = None
            self.r2_bucket = None
```

- [ ] **Step 5: Rewrite oss_put_obj method**

Replace the `oss_put_obj` method (lines 252-257):

```python
    def oss_put_obj(self, obj, name):
        try:
            inputData = json.dumps(obj, ensure_ascii=False)
            ossResult = self.oss_bucket.put_object(name, inputData)
        except Exception as e:
            print(e)
```

With:

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
```

- [ ] **Step 6: Rewrite oss_get_obj method**

Replace the `oss_get_obj` method (lines 259-266):

```python
    def oss_get_obj(self, name):
        try:
            object_stream = self.oss_bucket.get_object(name)
            readObj = object_stream.read()
            readObj = json.loads(str(readObj, 'utf-8'))
            return readObj
        except Exception as e:
            print(e)
```

With:

```python
    def oss_get_obj(self, name):
        try:
            resp = self.s3_client.get_object(Bucket=self.r2_bucket, Key=name)
            return json.loads(resp['Body'].read().decode('utf-8'))
        except Exception as e:
            print(e)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_client.py -v`
Expected: 7 tests PASS (3 existing + 4 new).

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add infra_client.py tests/test_infra_client.py
git commit -m "refactor: replace oss2 with boto3 for Cloudflare R2 storage"
```

---

### Task 3: Remove oss2 Dependency, Add boto3

**Files:**
- Modify: `pyproject.toml`
- Modify: `updateSymbol/updateTradeSymbol.py`

- [ ] **Step 1: Remove oss2 from pyproject.toml, add boto3**

In `pyproject.toml`, in the `dependencies` array:
- Remove the line `"oss2",`
- Add the line `"boto3",`

- [ ] **Step 2: Delete dead import in updateSymbol/updateTradeSymbol.py**

In `updateSymbol/updateTradeSymbol.py`, delete line 9:

```python
import oss2
```

- [ ] **Step 3: Run uv lock + uv sync**

Run: `uv lock && uv sync`
Expected: `oss2` removed, `boto3` installed.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Verify no oss2 references remain**

Run: `grep -r "import oss2" --include="*.py" . --exclude-dir=.venv --exclude-dir=.claude`
Expected: Only `webServer.py` (deprecated, Phase 3 cleanup).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock updateSymbol/updateTradeSymbol.py
git commit -m "chore: replace oss2 with boto3 dependency"
```

---

### Task 4: Update Frontend OSS URLs to R2 Domain

**Files:**
- Modify: `react-front/src/work/constainers/Show.js`
- Modify: `react-front/src/work/tradingview_extra_js/tv_api.js`
- Modify: `react-front/src/work/components/OtherConfigModal.js`
- Modify: `react-front/src/index.ejs`

All changes are the same string replacement:
`https://zuibite-api.oss-cn-hongkong.aliyuncs.com` → `https://cdn.example.com`

- [ ] **Step 1: Update Show.js (4 URLs)**

In `react-front/src/work/constainers/Show.js`, replace all occurrences of `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` with `https://cdn.example.com`.

The 4 locations are approximately:
- Line 231: investor data URL
- Line 251: main quant data URL
- Line 413: day income URL
- Line 445: position history URL

- [ ] **Step 2: Update tv_api.js (2 URLs)**

In `react-front/src/work/tradingview_extra_js/tv_api.js`, replace all occurrences of `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` with `https://cdn.example.com`.

The 2 locations are approximately:
- Line 385: kline test data
- Line 397: trade test data

- [ ] **Step 3: Update OtherConfigModal.js (1 URL)**

In `react-front/src/work/components/OtherConfigModal.js`, replace the occurrence of `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` with `https://cdn.example.com`.

- Line 37: audio file URL

- [ ] **Step 4: Update index.ejs (1 URL)**

In `react-front/src/index.ejs`, replace the occurrence of `https://zuibite-api.oss-cn-hongkong.aliyuncs.com` with `https://cdn.example.com`.

- Line 185: Dll.js script URL

- [ ] **Step 5: Verify no old URLs remain**

Run: `grep -r "zuibite-api.oss-cn-hongkong" react-front/`
Expected: No output.

- [ ] **Step 6: Commit**

```bash
git add react-front/src/work/constainers/Show.js react-front/src/work/tradingview_extra_js/tv_api.js react-front/src/work/components/OtherConfigModal.js react-front/src/index.ejs
git commit -m "refactor: update frontend URLs from Aliyun OSS to Cloudflare R2 domain"
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update InfraClient description**

In `CLAUDE.md`, in the Architecture section, change:

```
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Aliyun OSS, and Binance order routing
```

To:

```
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Cloudflare R2 object storage, and Binance order routing
```

- [ ] **Step 2: Update settings.py description**

In `CLAUDE.md`, after the `settings.py` description line, verify it still says:

```
- **settings.py** — pydantic-settings based configuration, reads from `.env` file. Template: `.env.example`
```

No change needed — the description is generic enough.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect Cloudflare R2 migration"
```

---

## Verification Checklist (end-to-end)

After all tasks are complete:

1. **No oss2 in active code:**
   ```bash
   grep -r "import oss2" --include="*.py" . --exclude-dir=.venv --exclude-dir=.claude
   ```
   Expected: Only `webServer.py` (deprecated).

2. **No old OSS URLs in frontend:**
   ```bash
   grep -r "zuibite-api.oss-cn-hongkong" react-front/
   ```
   Expected: No output.

3. **All tests pass:**
   ```bash
   uv run pytest tests/ -v
   ```

4. **Settings load R2 fields:**
   ```bash
   uv run python -c "from settings import settings; print(settings.r2_bucket_name, settings.r2_public_domain)"
   ```
   Expected: `zuibite-api` and empty string (or configured value).

5. **boto3 installed, oss2 not:**
   ```bash
   uv run pip list | grep -iE "boto3|oss2"
   ```
   Expected: Only `boto3` listed.
