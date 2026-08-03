"""Frozen stage-B data-center catalog and controlled source registry."""

from __future__ import annotations

from typing import Any


DATA_LAYERS: tuple[dict[str, str], ...] = (
    {"layer_id": "L1", "display_name": "行情层", "description": "股票、指数、板块行情与价格序列"},
    {"layer_id": "L2", "display_name": "证券基础层", "description": "证券目录、市场、上市状态与代码映射"},
    {"layer_id": "L3", "display_name": "公司与财务层", "description": "公司行动、分红送配与财务报表"},
    {"layer_id": "L4", "display_name": "行业与概念层", "description": "行业分类、行业板块与概念板块"},
    {"layer_id": "L5", "display_name": "资金面层", "description": "行业与概念资金流"},
    {"layer_id": "L6", "display_name": "公告、新闻与研报层", "description": "公告、新闻和研报目录"},
    {"layer_id": "L7", "display_name": "治理与参考事实层", "description": "交易日历、停复牌、质量与版本事实"},
)


def _controlled_source(
    source_id: str,
    display_name: str,
    provider_type: str,
    upstream_name: str,
    allowed_hosts: list[str],
    notes: str,
    *,
    requests_per_minute: int = 10,
    concurrency: int = 1,
    retry_count: int = 1,
    enabled: bool = False,
    verification_status: str = "candidate",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "display_name": display_name,
        "provider_type": provider_type,
        "upstream_name": upstream_name,
        "enabled": enabled,
        "verification_status": verification_status,
        "allowed_hosts": allowed_hosts,
        "secret_env_names": [],
        "requests_per_minute": requests_per_minute,
        "concurrency": concurrency,
        "retry_count": retry_count,
        "notes": notes,
    }


CONTROLLED_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "source_id": "akshare",
        "display_name": "AKShare 免费数据接口",
        "provider_type": "python_adapter",
        "upstream_name": "公开财经站点聚合",
        "enabled": True,
        "verification_status": "verified",
        "allowed_hosts": ["eastmoney.com", "sina.com.cn", "csindex.com.cn"],
        "secret_env_names": ["SCQ_AKSHARE_PROXY"],
        "requests_per_minute": 60,
        "concurrency": 4,
        "retry_count": 3,
        "notes": "已由现有 AkshareGovernanceProvider 实现；仅允许受控端点只读探测。",
    },
    {
        "source_id": "baostock",
        "display_name": "BaoStock 候选免费接口",
        "provider_type": "unimplemented_adapter",
        "upstream_name": "BaoStock",
        "enabled": False,
        "verification_status": "candidate",
        "allowed_hosts": ["baostock.com"],
        "secret_env_names": [],
        "requests_per_minute": 30,
        "concurrency": 1,
        "retry_count": 2,
        "notes": "仅登记候选，不存在运行适配器，不能启用或进入正式路由。",
    },
    _controlled_source(
        "mootdx", "mootdx 通达信候选接口", "optional_python_adapter",
        "通达信行情节点与本地数据文件", ["mootdx.com", "github.com"],
        "MIT 开源且声明仅供学习交流；当前未引入依赖、未实现适配器，不能启用。",
        requests_per_minute=30, retry_count=2,
    ),
    _controlled_source(
        "tencent_finance", "腾讯财经候选接口", "undocumented_http_candidate",
        "腾讯财经公开行情页面", ["gtimg.cn"],
        "未确认官方开放 API 合约、配额与授权边界；仅登记，不允许启用直连。",
    ),
    _controlled_source(
        "iwencai", "i问财候选接口", "undocumented_web_query_candidate",
        "同花顺 i问财", ["iwencai.com", "10jqka.com.cn"],
        "自然语言网页查询能力不等同于免费开放 API；鉴权、反自动化与授权边界待确认。",
        requests_per_minute=5,
    ),
    _controlled_source(
        "eastmoney_reportapi", "东方财富研报候选接口", "undocumented_http_candidate",
        "东方财富研报中心", ["eastmoney.com"],
        "公开研报页面已确认，但 reportapi 未确认官方开放接口合约；版权与下载边界需单独治理。",
    ),
    _controlled_source(
        "akshare_ths", "AKShare 同花顺免费接口", "bounded_python_adapter",
        "AKShare 封装的同花顺公开数据", ["10jqka.com.cn"],
        "2026-07-31 已验证：目录缓存与15秒请求上限已接入；20板块×3日对账全部通过，作为东财板块历史的受控失败回退。",
        requests_per_minute=15, concurrency=2, retry_count=2,
        enabled=True, verification_status="verified",
    ),
    _controlled_source(
        "cninfo", "巨潮资讯受控接口", "bounded_http_curl_adapter",
        "巨潮资讯网", ["cninfo.com.cn"],
        "2026-07-31 已批准受控启用：仅行业目录与行业变更两条 fill_missing 路由启用；公告和股本路由继续停用。此前 10 证券只读影子对账分类与本地 10/10 一致，目录首轮 403 后单次重试恢复。",
        requests_per_minute=10, concurrency=1, retry_count=2,
        enabled=True, verification_status="verified",
    ),
    _controlled_source(
        "a_stock_data", "a-stock-data 候选聚合方案", "third_party_reference_implementation",
        "simonlin1212/a-stock-data", ["github.com"],
        "第三方聚合 Skill，不是原始数据源；仅作接口研究参考，不进入正式路由。",
        requests_per_minute=1, concurrency=1, retry_count=0,
    ),
)


SOURCE_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"source_id": "baostock", "endpoint_id": "query_history_k_data_plus", "dataset_id": "a_share_daily"},
    {"source_id": "baostock", "endpoint_id": "query_stock_basic", "dataset_id": "a_share_catalog"},
    {"source_id": "baostock", "endpoint_id": "query_trade_dates", "dataset_id": "trade_calendar"},
    {"source_id": "baostock", "endpoint_id": "query_profit_data", "dataset_id": "financial_statements"},
    {"source_id": "mootdx", "endpoint_id": "Quotes.bars", "dataset_id": "a_share_daily"},
    {"source_id": "mootdx", "endpoint_id": "Quotes.index", "dataset_id": "index_daily"},
    {"source_id": "mootdx", "endpoint_id": "Reader.daily", "dataset_id": "a_share_daily"},
    {"source_id": "tencent_finance", "endpoint_id": "public_quote_page", "dataset_id": "a_share_daily"},
    {"source_id": "tencent_finance", "endpoint_id": "public_quote_page", "dataset_id": "index_daily"},
    {"source_id": "iwencai", "endpoint_id": "natural_language_query", "dataset_id": "a_share_catalog"},
    {"source_id": "iwencai", "endpoint_id": "natural_language_query", "dataset_id": "concept_catalog"},
    {"source_id": "eastmoney_reportapi", "endpoint_id": "report_center", "dataset_id": "research_reports"},
    {"source_id": "akshare_ths", "endpoint_id": "stock_board_industry_index_ths", "dataset_id": "industry_board", "enabled": True, "verification_status": "verified"},
    {"source_id": "akshare_ths", "endpoint_id": "stock_board_concept_index_ths", "dataset_id": "concept_board", "enabled": True, "verification_status": "verified"},
    {"source_id": "akshare_ths", "endpoint_id": "stock_board_industry_name_ths", "dataset_id": "industry_classification", "enabled": True, "verification_status": "verified"},
    {"source_id": "akshare_ths", "endpoint_id": "stock_board_concept_name_ths", "dataset_id": "concept_catalog", "enabled": True, "verification_status": "verified"},
    {"source_id": "cninfo", "endpoint_id": "announcement_search", "dataset_id": "events", "verification_status": "verified"},
    {"source_id": "cninfo", "endpoint_id": "stock_industry_category_cninfo", "dataset_id": "industry_classification", "enabled": True, "verification_status": "verified"},
    {"source_id": "cninfo", "endpoint_id": "stock_industry_change_cninfo", "dataset_id": "industry_classification", "enabled": True, "verification_status": "verified"},
    {"source_id": "cninfo", "endpoint_id": "stock_share_change_cninfo", "dataset_id": "corporate_actions", "verification_status": "verified"},
)


def _dataset(
    dataset_id: str,
    layer_id: str,
    display_name: str,
    description: str,
    *,
    availability_status: str,
    sync_enabled: bool = False,
    config_fields: tuple[str, ...] = ("target_trade_date",),
    producer_type: str = "external_source",
    producer_id: str = "",
    route_required: bool = True,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "layer_id": layer_id,
        "display_name": display_name,
        "description": description,
        "availability_status": availability_status,
        "sync_enabled": sync_enabled,
        "config_fields": list(config_fields),
        "schema_version": "v1",
        "producer_type": producer_type,
        "producer_id": producer_id,
        "route_required": route_required,
    }


DATASET_CATALOG: tuple[dict[str, Any], ...] = (
    _dataset("a_share_daily", "L1", "A股日线行情", "A股 raw/qfq/hfq 日线", availability_status="connected", sync_enabled=True, config_fields=("target_trade_date", "scope", "symbols", "adjustments")),
    _dataset("index_daily", "L1", "A股指数日线", "核心 A 股指数日线", availability_status="connected", sync_enabled=True),
    _dataset("industry_board", "L1", "行业板块历史", "行业板块日线序列", availability_status="connected", sync_enabled=True),
    _dataset("global_index_daily", "L1", "全球指数日线", "全球主要指数历史日线候选", availability_status="disabled"),
    _dataset("concept_board", "L1", "概念板块历史", "概念板块日线序列", availability_status="connected", sync_enabled=True),
    _dataset("a_share_catalog", "L2", "A股证券目录", "代码、名称、市场与上市状态", availability_status="connected"),
    _dataset("corporate_actions", "L3", "公司行动与分红送配", "除权除息和公司行动事实", availability_status="connected"),
    _dataset("financial_statements", "L3", "财务报表", "财务报表候选接口", availability_status="disabled"),
    _dataset("industry_classification", "L4", "行业分类", "股票行业点时区间", availability_status="connected"),
    _dataset("industry_classification_repair", "L4", "行业分类失败修复", "只重试行业分类失败证券", availability_status="connected", sync_enabled=True),
    _dataset("concept_catalog", "L4", "概念板块目录", "概念板块目录，不含点时成分", availability_status="connected"),
    _dataset("industry_flow", "L5", "行业历史资金流", "行业板块历史资金流", availability_status="connected", sync_enabled=True),
    _dataset("concept_flow", "L5", "概念历史资金流", "概念板块历史资金流", availability_status="connected", sync_enabled=True),
    _dataset("events", "L6", "个股公告与新闻", "按股票受控同步公告与新闻", availability_status="connected", sync_enabled=True, config_fields=("target_trade_date", "symbols")),
    _dataset("research_reports", "L6", "研报目录", "来源与授权尚未验证", availability_status="disabled", producer_type="disabled_candidate", route_required=False),
    _dataset("trade_calendar", "L7", "A股交易日历", "交易日与休市事实", availability_status="connected"),
    _dataset("index_components", "L7", "指数成分", "已接入指数成分事实", availability_status="connected"),
    _dataset("trading_status", "L7", "停复牌与交易状态", "逐日交易状态与停牌证据", availability_status="connected", producer_type="internal_pipeline", producer_id="a_share_sync_scheduler", route_required=False),
    _dataset("quality_issues", "L7", "质量问题", "质量规则、异常证据与处置历史", availability_status="connected", producer_type="internal_control_plane", producer_id="data_quality_engine", route_required=False),
    _dataset("data_versions", "L7", "数据版本", "不可变发布版本与默认研究指针", availability_status="connected", producer_type="internal_control_plane", producer_id="a_share_governance_store", route_required=False),
)


def source_by_id(source_id: str) -> dict[str, Any] | None:
    return next((dict(item) for item in CONTROLLED_SOURCES if item["source_id"] == source_id), None)


def dataset_by_id(dataset_id: str) -> dict[str, Any] | None:
    return next((dict(item) for item in DATASET_CATALOG if item["dataset_id"] == dataset_id), None)
