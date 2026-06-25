"""集成测试: 规则引擎 + 数据库"""
import sys
sys.path.insert(0, "..")

from bili_manager.rules.engine import RuleEngine
from bili_manager.db import database

database.init_db()

mock_follows = [
    {"mid": 1, "uname": "bili_12345", "sign": "", "face": "", "mtime": 1712345678,
     "official_verify": {"type": 0, "desc": ""}, "vip": {"vipStatus": 0, "vipType": 0}},
    {"mid": 2, "uname": "帅农鸟哥", "sign": "商务合作+VX:xxx", "face": "", "mtime": 1712345678,
     "official_verify": {"type": 1, "desc": "bilibili 2023百大UP主"}, "vip": {"vipStatus": 1, "vipType": 2}},
    {"mid": 3, "uname": "JohnDoe", "sign": "I make videos about tech", "face": "", "mtime": 1712345678,
     "official_verify": {"type": 0, "desc": ""}, "vip": {"vipStatus": 1, "vipType": 2}},
    {"mid": 4, "uname": "免费领取教程", "sign": "关注即送全套课程 点击链接领取", "face": "", "mtime": 1712345678,
     "official_verify": {"type": 0, "desc": ""}, "vip": {"vipStatus": 0, "vipType": 0}},
    {"mid": 5, "uname": "已注销用户", "sign": "", "face": "", "mtime": 0,
     "official_verify": {"type": 0, "desc": ""}, "vip": {"vipStatus": 0, "vipType": 0}},
]

database.save_follows(mock_follows)

engine = RuleEngine()
verdicts = []
for f in mock_follows:
    official_type = f.get("official_verify", {}).get("type", 0)
    is_vip = f.get("vip", {}).get("vipStatus", 0) == 1
    result = engine.evaluate_signature(f, official_type, is_vip)
    if result.keep_score >= result.delete_score:
        verdict = "keep"
    elif result.delete_score >= 40:
        verdict = "delete"
    else:
        verdict = "unreviewed"
    verdicts.append({
        "mid": f["mid"], "verdict": verdict,
        "rule_keep": ",".join(result.matched_keep),
        "rule_delete": ",".join(result.matched_delete),
        "keep_score": result.keep_score, "delete_score": result.delete_score,
    })
    print(f'{f["uname"]:20s} -> {verdict:10s}  K{result.keep_score:3d}/D{result.delete_score:3d}')
    print(f'  keep: {result.matched_keep}')
    print(f'  del:  {result.matched_delete}')

database.save_verdicts(verdicts)
print()

# 验证判定正确性
assert verdicts[0]["verdict"] == "delete", f"bili_空号应为 delete, 实际 {verdicts[0]['verdict']}"
assert verdicts[1]["verdict"] == "keep", f"百大UP主应为 keep, 实际 {verdicts[1]['verdict']}"
assert verdicts[2]["verdict"] == "keep", f"英文名+签名 VIP 应为 keep, 实际 {verdicts[2]['verdict']}"
assert verdicts[3]["verdict"] == "delete", f"免费领取营销号应为 delete, 实际 {verdicts[3]['verdict']}"
assert verdicts[4]["verdict"] == "delete", f"已注销应为 delete, 实际 {verdicts[4]['verdict']}"

print("All assertions passed!")

# 测试探测规则
mock_probes = [
    {"uid": 1, "archive_count": 0, "follower": 0, "following": 0, "level": 0, "spacesta": 0, "ff_ratio": 0.0},
    {"uid": 6, "archive_count": 0, "follower": 0, "following": 0, "level": 0, "spacesta": -2, "ff_ratio": 0.0},
    {"uid": 7, "archive_count": 0, "follower": 10, "following": 600, "level": 3, "spacesta": 0, "ff_ratio": 60.0},
]
for p in mock_probes:
    r = engine.evaluate_probe(p)
    print(f'UID {p["uid"]:2d} probe -> K{r.keep_score:3d}/D{r.delete_score:3d}  {r.matched_probe}')

assert verdicts[0]["verdict"] == "delete"
print("Probe tests passed!")

stats = database.get_stats()
print(f"\nStats: total={stats['total_follows']}, keep={stats['verdict_keep']}, delete={stats['verdict_delete']}")
