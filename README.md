# 保证金笼

> 遵守 `ops/底座生成前必读_效率与技术栈.md`（≥2000 行像产品）。  
> FastAPI + Vue 3 + SQLite；`docker compose up -d --build` 一键起。  
> **禁止同构换皮**：主链路不是「占位→确认入册」也不是「入轨→裁定赔付」也不是「业务窗裁切物化」。

## 骨架一句话

保证金先入笼冻结，履约核验通过才解笼拨付，违约进罚没册，笼代与拨付罚没对账。

## 基本信息

| 项 | 值 |
|----|-----|
| 产品名 | 保证金笼 |
| 目录 | `11-bondcage` |
| 接口 | http://127.0.0.1:11322 |
| 库 | `data/app.db` |
| 账号 | admin / clerk / viewer ，密码均为 123456（viewer 只读） |

## 厚度

| 项 | 内容 |
|----|------|
| 业务 LOC | **≥2900**（py+前端，不含 vue.global / Docker / README；自检约 2984） |
| 后端模块 | db / auth / locks / bonds_svc / cages_svc / attest_svc / release_svc / forfeit_svc / reconcile_svc / audit_svc / recheck_policy / recheck_svc / topup_svc / split_svc |
| 前端视图 | 保证金户 / 入笼冻结 / 履约核验 / 解笼拨付 / 罚没册 / 对账互证 / 审计争用 / 增补重核 + 拆笼空桩（8 页） |
| 空桩 | split（拆笼分拨）——前后端均有；topup 已落甲路径，不再是空桩 |

## 增补重核（当日锁死）

增补抬额后禁止旧核验结论直出金。唯一口径为 **甲路径**：增补提交、扩额、作废旧核验、笼改「待重核」、写审计同事务完成，失败则增补与作废同滚；重核前解笼与罚没口一律关闭。乙路径（影子复检单）不采用，偏离纪要记 `recheck_deviation` 并拒写。规则正文见 `docs/增补重核纪要.md`，摘要锁死在其 `.sha256` 邻文件。

五页（增补 / 核验 / 解笼 / 罚没 / 审计）账实同源读取 `/api/recheck/board`。

## 主链路

开户入金 → 按合约入笼冻结（笼代）→ 履约核验通过 → 解笼拨付到收款方 / 违约罚没 → 笼代余额与拨付+罚没对账

## 互斥切口候选

- 解笼失败整笔回滚 vs 影子拨付后晋升
- 罚没立即入册 vs 影子罚没待复核晋升
- 增补同笼扩代（甲，已采用） vs 新笼桥接双写（拒写并记偏航）
- 拆笼整笔事务切分 vs 影子子笼后晋升

## 启动

```powershell
cd projects/11-bondcage
docker compose up -d --build
```

浏览器：http://127.0.0.1:11322/

本机开发：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 10608
python -m pytest -q
python -I scripts/live_fixture.py   # 本机文件库实跑增补重核事故夹具
```

## 新增/变更接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/topup` | 甲路径增补抬额；`/api/topup-stub` 为兼容别名 |
| GET | `/api/recheck/board` | 五页同源看板：待重核、作废痕、偏航、闸门 |
| GET | `/api/recheck/{cage_id}` | 单笼重核状态 |

## 测试锚点

`tests/test_topup_recheck.py` 先以两条红测锁定事故（增补后旧结论直出金、双人同出金争用），再验证甲路径闭环、偏航拒写、纪要锁死与事务回滚。禁止跳过失败测直接改文案。
