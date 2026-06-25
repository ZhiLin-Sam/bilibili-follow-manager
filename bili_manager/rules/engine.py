"""规则引擎 — TOML 配置加载与匹配"""

import re
import tomllib
from pathlib import Path
from dataclasses import dataclass, field

from ..utils.helpers import logger, get_config_dir

DEFAULT_RULES_PATH = get_config_dir() / "default_rules.toml"


@dataclass
class Rule:
    name: str
    priority: int
    description: str
    rule_type: str  # "keep" or "delete" or "probe"
    # probe 规则字段
    dimension: str = ""
    operator: str = ""
    value: float = 0.0


@dataclass
class RuleMatchResult:
    matched_keep: list[str] = field(default_factory=list)
    matched_delete: list[str] = field(default_factory=list)
    matched_probe: list[str] = field(default_factory=list)
    keep_score: int = 0
    delete_score: int = 0


class RuleEngine:
    """规则引擎: 加载 TOML 规则, 对账号数据打分"""

    def __init__(self, custom_rules_path: str | None = None):
        self.keep_rules: list[Rule] = []
        self.delete_rules: list[Rule] = []
        self.probe_rules: list[Rule] = []
        self.unfollow_config: dict = {}

        self._load_rules(DEFAULT_RULES_PATH)
        if custom_rules_path:
            self._load_rules(Path(custom_rules_path))

        # 预编译匹配模式
        self._compile_matchers()

    def _load_rules(self, path: Path) -> None:
        if not path.exists():
            logger.warning(f"规则文件不存在: {path}")
            return

        data = tomllib.loads(path.read_text(encoding="utf-8"))

        for r in data.get("keep_rules", []):
            self.keep_rules.append(Rule(
                name=r["name"], priority=r["priority"],
                description=r.get("description", ""), rule_type="keep"
            ))

        for r in data.get("delete_rules", []):
            self.delete_rules.append(Rule(
                name=r["name"], priority=r["priority"],
                description=r.get("description", ""), rule_type="delete"
            ))

        for r in data.get("probe_rules", []):
            self.probe_rules.append(Rule(
                name=r["name"], priority=r["priority"],
                description=r.get("description", ""), rule_type="probe",
                dimension=r.get("dimension", ""),
                operator=r.get("operator", "eq"),
                value=float(r.get("value", 0)),
            ))

        self.unfollow_config = data.get("unfollow", {})
        logger.info(
            f"规则已加载: {len(self.keep_rules)} keep, "
            f"{len(self.delete_rules)} delete, "
            f"{len(self.probe_rules)} probe"
        )

    def _compile_matchers(self) -> None:
        """预编译基础文本匹配模式, 用于签名/用户名分析"""
        self.marketing_patterns = [
            (re.compile(r"关注即送|免费领取|点击.*链接|免费.*福利"), 30),
            (re.compile(r"代理|兼职|赚钱|刷量|买粉|增粉"), 25),
            (re.compile(r"广告位.*招租|报价.*私|商务.*私"), 20),
            (re.compile(r"贷款|网贷|下款|套现|理财.*导师|股票.*涨停"), 25),
            (re.compile(r"小说|网文|全文|追书|笔趣阁|番茄小说|免费读|漫画免费|短剧"), 15),
            (re.compile(r"关注.*送|关注.*领|关注.*福利|关注.*抽奖"), 10),
        ]
        self.creator_patterns = [
            re.compile(r"创作|制作|分享|原创|拍摄|摄影|画师|音乐|配音"),
            re.compile(r"VLOG|vlog|记录|日常|生活"),
            re.compile(r"UP主|up主|投稿|频道"),
        ]
        self.contact_pattern = re.compile(r"vx|wx|VX|WX|微信|QQ|qq|邮箱|合作|商务", re.IGNORECASE)
        self.english_name_pattern = re.compile(r"^[A-Za-z0-9_\-\.]+$")
        self.bili_prefix_pattern = re.compile(r"^bili_\d+")
        self.default_name_pattern = re.compile(r"^用户\d{6,}$|^\d{8,}$")
        self.deleted_pattern = re.compile(r"已注销|账号已注销")

    def _analyze_text(self, text: str) -> tuple[int, int, list[str], list[str]]:
        """分析签名文本, 返回 (营销得分, 创作者得分, 营销标签, 创作者标签)"""
        if not text:
            return 0, 0, [], []

        marketing_score = 0
        creator_score = 0
        m_tags = []
        c_tags = []

        # 降权: 商务合作类关键词降低营销权重
        has_contact = bool(self.contact_pattern.search(text))

        for pattern, score in self.marketing_patterns:
            if pattern.search(text):
                if has_contact:
                    score = max(score - 10, 5)  # 降权
                marketing_score += score

        for pattern in self.creator_patterns:
            if pattern.search(text):
                creator_score += 15

        return marketing_score, creator_score, m_tags, c_tags

    def evaluate_signature(
        self, user: dict, official_verify: int = 0, is_vip: bool = False
    ) -> RuleMatchResult:
        """基于签名/用户名/认证等元数据的规则匹配 (无需 API 探测)"""
        result = RuleMatchResult()
        uname = user.get("uname", "")
        sign = user.get("sign", "")

        # --- KEEP 信号评估 ---

        # K1: 知名/百大/官方认证
        if official_verify > 0 or user.get("official_verify", {}).get("type", 0) > 0:
            result.matched_keep.append("知名/百大/官方认证")
            result.keep_score += 100

        # K2: VIP+有签名+无营销
        m_score, _, _, _ = self._analyze_text(sign)
        if is_vip and len(sign) >= 4 and m_score < 15:
            result.matched_keep.append("VIP用户+活跃")
            result.keep_score += 60

        # K8: 英文用户名+有签名
        if self.english_name_pattern.match(uname) and len(sign) >= 6:
            result.matched_keep.append("英文用户名+有签名=真人")
            result.keep_score += 70

        # 创作信号
        _, c_score, _, _ = self._analyze_text(sign)
        if c_score >= 15:
            result.matched_keep.append("创作/分享/制作类签名")
            result.keep_score += 40

        # 品牌/组织号
        if re.search(r"官方|频道|_Official|_CN$|频道$", uname):
            result.matched_keep.append("品牌/组织官方号")
            result.keep_score += 50

        # 小说/连载+有认证
        if re.search(r"小说|连载|网文|漫画", sign) and official_verify > 0:
            result.matched_keep.append("小说/连载+有认证")
            result.keep_score += 50

        # 中文名+有签名≥8字+无营销
        is_chinese = bool(re.search(r"[\u4e00-\u9fff]", uname))
        if is_chinese and len(sign) >= 8 and m_score < 20:
            result.matched_keep.append("中文名+有签名≥8字+无营销")
            result.keep_score += 30

        # bili_前缀但有签名
        if self.bili_prefix_pattern.match(uname) and len(sign) >= 6:
            result.matched_keep.append("bili_前缀+有签名≥6字")
            result.keep_score += 25

        # K10: 有认证
        if official_verify > 0:
            result.matched_keep.append("有认证")
            result.keep_score += 50

        # K11: VIP
        if is_vip:
            result.matched_keep.append("VIP")
            result.keep_score += 25

        # --- DELETE 信号评估 ---

        # D1: 已注销
        if self.deleted_pattern.search(uname) or user.get("mtime", 0) == 0:
            result.matched_delete.append("账号已注销")
            result.delete_score += 200

        # D2: bili_数字+空签名+无认证
        if self.bili_prefix_pattern.match(uname) and len(sign) == 0 and official_verify == 0:
            result.matched_delete.append("bili_数字+空签名+无认证")
            result.delete_score += 80

        # D4/D5/D6/D7/D8/D9: 签名营销信号
        if m_score >= 40:
            result.matched_delete.append(f"强营销信号(得分{m_score})")
            result.delete_score += m_score

        # D10: 英文名+空签名+默认头像
        if self.english_name_pattern.match(uname) and len(sign) == 0:
            result.matched_delete.append("英文名+空签名+默认头像")
            result.delete_score += 40

        # 空签名降权
        if len(sign) == 0:
            result.delete_score += 10

        return result

    def evaluate_probe(self, probe_data: dict) -> RuleMatchResult:
        """基于 API 探测数据的规则匹配"""
        result = RuleMatchResult()

        for rule in self.probe_rules:
            if rule.dimension == "spacesta" and probe_data.get("spacesta", 0) == -2:
                result.matched_probe.append(rule.name)
                result.delete_score += 150

            elif rule.dimension == "empty":
                ac = probe_data.get("archive_count", -1)
                fl = probe_data.get("follower", -1)
                lv = probe_data.get("level", -1)
                if ac == 0 and fl == 0 and lv == 0:
                    result.matched_probe.append(rule.name)
                    result.delete_score += 60

            elif rule.dimension == "ff_ratio":
                ff = probe_data.get("ff_ratio", 0)
                following = probe_data.get("following", 0)
                if ff >= 5.0 and following >= 500:
                    result.matched_probe.append(rule.name)
                    result.delete_score += 50

            elif rule.dimension == "dead":
                ac = probe_data.get("archive_count", -1)
                fl = probe_data.get("follower", -1)
                fg = probe_data.get("following", -1)
                if ac == 0 and fl == 0 and fg > 50:
                    result.matched_probe.append(rule.name)
                    result.delete_score += 40

        # 活跃信号
        level = probe_data.get("level", -1)
        archive = probe_data.get("archive_count", -1)
        follower = probe_data.get("follower", -1)
        total_view = probe_data.get("total_view", -1)

        if level >= 4 and archive > 0:
            result.keep_score += 30
            result.matched_keep.append(f"活跃用户: LV{level} 投稿{archive}")
        if follower >= 100:
            result.keep_score += 20
        if total_view > 10000:
            result.keep_score += 15

        return result
