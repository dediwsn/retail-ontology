"""
Pydantic schemas for the ontology demo data model (spec § 8).

These types serve as the single source of truth for JSON serialization,
LLM tool-use input schemas, and Neptune loading (Phase 3).
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Domain = Literal["grocery", "beauty"]
Sentiment = Literal["positive", "neutral", "negative"]
ConcernDomain = Literal["skin", "diet", "lifestyle"]
TrendType = Literal["seasonal", "kbeauty", "diet", "functional", "korea"]
Gender = Literal["F", "M", "Other"]
ChannelType = Literal["편의점", "마트", "드럭스토어", "온라인"]


class Manufacturer(BaseModel):
    mfr_id: str
    name_ko: str
    name_en: Optional[str] = None
    country: str = "KR"
    domains: List[Domain]


class Brand(BaseModel):
    brand_id: str
    name_ko: str
    name_en: Optional[str] = None
    manufacturer_id: str
    domain: Domain
    positioning_ko: Optional[str] = None


class Category(BaseModel):
    gs1_brick_code: str
    gs1_brick_name_en: str
    kfda_category_path: str
    retail_category_ko: str
    synonyms_ko: List[str] = Field(default_factory=list)
    domain: str


class Ingredient(BaseModel):
    ingredient_id: str
    name_en: str
    name_ko: str
    synonyms_ko: List[str] = Field(default_factory=list)
    function_ko: Optional[str] = None
    concerns_ko: List[str] = Field(default_factory=list)
    regulatory_class: Optional[str] = None
    standard: Literal["INCI", "FoodOn", "Custom"]


class Nutrient(BaseModel):
    nutrient_id: str
    name_ko: str
    name_en: str
    unit: str
    daily_value: Optional[float] = None


class Concern(BaseModel):
    concern_id: str
    name_ko: str
    name_en: str
    domain: ConcernDomain
    description_ko: Optional[str] = None
    prefers_ingredient_ids: List[str] = Field(default_factory=list)
    avoids_ingredient_ids: List[str] = Field(default_factory=list)


class Persona(BaseModel):
    persona_id: str
    label_ko: str
    age: int
    gender: Gender
    life_stage_ko: Optional[str] = None
    occupation_ko: Optional[str] = None
    concern_ids: List[str] = Field(default_factory=list)
    preferred_ingredient_ids: List[str] = Field(default_factory=list)
    avoided_ingredient_ids: List[str] = Field(default_factory=list)
    favorite_brick_codes: List[str] = Field(default_factory=list)
    narrative_ko: str
    is_wow: bool = False


class ProductIngredient(BaseModel):
    ingredient_id: str
    amount_note_ko: Optional[str] = None


class ProductNutrient(BaseModel):
    nutrient_id: str
    value: float
    per_100g_or_ml: bool = True


class Product(BaseModel):
    sku_id: str
    name_ko: str
    name_en: Optional[str] = None
    domain: Domain
    gs1_brick_code: str
    brand_id: str
    volume: Optional[float] = None
    unit: Optional[Literal["ml", "g", "ea"]] = None
    price_krw: int
    ingredients: List[ProductIngredient] = Field(default_factory=list)
    nutrients: List[ProductNutrient] = Field(default_factory=list)
    claims_ko: List[str] = Field(default_factory=list)
    target_concern_ids: List[str] = Field(default_factory=list)
    description_ko: str
    is_wow: bool = False


class Review(BaseModel):
    review_id: str
    sku_id: str
    persona_id: str
    sentiment: Sentiment
    rating: int = Field(ge=1, le=5)
    title_ko: Optional[str] = None
    body_ko: str
    helpful_count: int = 0
    review_date: date


class Trend(BaseModel):
    trend_id: str
    name_ko: str
    name_en: Optional[str] = None
    type: TrendType
    description_ko: str
    involves_ingredient_ids: List[str] = Field(default_factory=list)
    involves_brick_codes: List[str] = Field(default_factory=list)
    emerged_period: Optional[str] = None


class Promotion(BaseModel):
    promotion_id: str
    name_ko: str
    discount_pct: int
    period_start: date
    period_end: date
    applies_to_sku_ids: List[str] = Field(default_factory=list)
    applies_to_brick_codes: List[str] = Field(default_factory=list)
    channel_ids: List[str] = Field(default_factory=list)


class Channel(BaseModel):
    channel_id: str
    name_ko: str
    type: ChannelType


# ─── Membership / Marketing (Phase 2A) ─────────────────────────────────────
#
# Adds an individual-member layer beneath the existing 5 Persona archetypes.
# Powers churn-risk, acquisition-ROI, and tier-up scenarios. RFM (Recency /
# Frequency / Monetary) is the underlying model — consistent with marketing
# practice and lets the LLM explain "why this member is at risk."

CampaignType = Literal["acquisition", "retention", "winback"]
CampaignChannel = Literal["email", "push", "sms", "kakao"]
TouchpointType = Literal["email", "push", "sms", "kakao", "visit"]
TierName = Literal["Bronze", "Silver", "Gold", "VIP"]


class MembershipTier(BaseModel):
    tier_id: str
    name_ko: str
    name_en: TierName
    threshold_krw: int
    discount_rate: float


class Member(BaseModel):
    member_id: str
    name_ko: str
    age: int
    gender: Gender
    tier: TierName
    persona_id: Optional[str] = None
    joined_at: date
    last_purchase_at: Optional[date] = None
    recency_days: int
    frequency: int
    monetary_krw: int
    ltv_krw: int
    churn_risk: float = Field(ge=0.0, le=1.0)
    primary_channel_id: Optional[str] = None
    # KOSTAT 시도 코드 (Region.region_code). Phase 2A-G에서 추가 — 회원 위치를
    # 페르소나 편향 분포로 결정론적으로 부여해 시나리오 L(Coverage Map)과 시나리오
    # H(Logistics) 지도를 같은 페르소나 컨텍스트로 잇는다.
    region_id: Optional[str] = None


class Campaign(BaseModel):
    campaign_id: str
    name_ko: str
    type: CampaignType
    channel: CampaignChannel
    start: date
    end: date
    cost_krw: int
    target_persona_ids: List[str] = Field(default_factory=list)


class Transaction(BaseModel):
    transaction_id: str
    member_id: str
    sku_id: str
    amount_krw: int
    ts: date
    channel_id: Optional[str] = None


class Touchpoint(BaseModel):
    touchpoint_id: str
    member_id: str
    campaign_id: Optional[str] = None
    type: TouchpointType
    ts: date
    responded: bool = False
