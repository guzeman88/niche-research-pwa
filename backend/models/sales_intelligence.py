"""Explicit units, time bases and provenance for private reference research."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc(value):
    if value.tzinfo is None:
        raise ValueError('Dates require an explicit timezone')
    return value.astimezone(timezone.utc)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator('*', mode='before')
    @classmethod
    def reject_boolean(cls, value, info):
        if isinstance(value, bool) and info.field_name in ('value', 'actual', 'price', 'favorites', 'views', 'reviews', 'stock'):
            raise ValueError('Counts must be numbers, not booleans')
        return value


class Metadata(Input):
    listing_id: str = Field(pattern=r'^\d{1,30}$')
    title: str = Field(default='', max_length=300)
    shop: str = Field(default='', max_length=120)
    shop_id: str | None = Field(default=None, pattern=r'^\d{1,30}$')
    category: str = Field(default='', max_length=100)
    product_type: Literal['digital', 'physical', 'unknown'] = 'unknown'
    created_at: datetime | None = None
    captured_at: datetime
    available_at: datetime
    price: float | None = Field(default=None, ge=0, le=1e9)
    currency: str = Field(default='', pattern=r'^([A-Z]{3})?$')
    favorites: float | None = Field(default=None, ge=0, le=1e12)
    views: float | None = Field(default=None, ge=0, le=1e12)
    reviews: float | None = Field(default=None, ge=0, le=1e12)
    stock: float | None = Field(default=None, ge=0, le=1e12)
    source_ref: str = Field(min_length=3, max_length=500)

    @field_validator('captured_at', 'available_at', 'created_at')
    @classmethod
    def timestamps(cls, value):
        return utc(value) if value else value

    @model_validator(mode='after')
    def dates(self):
        if self.captured_at > self.available_at or self.available_at > datetime.now(timezone.utc):
            raise ValueError('Metadata cannot be available before capture or in the future')
        if self.created_at and self.created_at > self.captured_at:
            raise ValueError('Creation cannot follow capture')
        return self


class Reference(Input):
    source_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,40}$')
    listing_id: str = Field(pattern=r'^\d{1,30}$')
    metric: Literal['estimated_sales', 'estimated_revenue', 'views', 'favorites', 'reviews', 'price', 'stock'] = 'estimated_sales'
    value: float | None = Field(default=None, ge=0, le=1e12)
    unit: Literal['units', 'purchases', 'buyers', 'unknown', 'currency', 'count'] = 'unknown'
    basis: Literal['period', 'lifetime', 'lifetime_average', 'provider_monthly', 'point_in_time']
    period_start: datetime | None = None
    period_end: datetime | None = None
    captured_at: datetime
    available_at: datetime
    provider_updated_at: datetime | None = None
    precision: Literal['point', 'lower_bound', 'upper_bound'] = 'point'
    status: Literal['observed', 'missing', 'unsupported', 'not_found'] = 'observed'
    currency: str = Field(default='', pattern=r'^([A-Z]{3})?$')
    source_ref: str = Field(min_length=3, max_length=500)
    original_label: str = Field(default='', max_length=100)
    note: str = Field(default='', max_length=1000)
    supersedes: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    metadata: Metadata | None = None

    @field_validator('period_start', 'period_end', 'captured_at', 'available_at', 'provider_updated_at')
    @classmethod
    def timestamps(cls, value):
        return utc(value) if value else value

    @model_validator(mode='after')
    def semantic_contract(self):
        if self.available_at < self.captured_at or self.available_at > datetime.now(timezone.utc):
            raise ValueError('Availability must follow capture and cannot be future')
        if self.provider_updated_at and self.provider_updated_at > self.captured_at:
            raise ValueError('Provider update cannot follow capture')
        if (self.value is None) != (self.status != 'observed'):
            raise ValueError('Observed values need a number; missing/unsupported values must stay null')
        if self.basis == 'period':
            if not self.period_start or not self.period_end or not self.period_start < self.period_end <= self.captured_at:
                raise ValueError('Period estimates need an ordered, completed half-open interval')
        elif self.period_start or self.period_end:
            raise ValueError('Only period measurements take period boundaries')
        if self.metric in ('estimated_sales', 'estimated_revenue') and self.basis == 'point_in_time':
            raise ValueError('Sales estimates need a declared reporting basis')
        if self.metric == 'estimated_revenue' and (self.unit != 'currency' or not self.currency):
            raise ValueError('Revenue needs currency and its unit')
        if self.metric == 'estimated_sales' and self.unit in ('currency', 'count'):
            raise ValueError('Sales units must be explicit or unknown')
        if self.metadata and (self.metadata.listing_id != self.listing_id or self.metadata.available_at > self.available_at):
            raise ValueError('Metadata must match the listing and observation availability')
        return self


class Outcome(Input):
    listing_id: str = Field(pattern=r'^\d{1,30}$')
    shop: str = Field(min_length=1, max_length=120)
    shop_id: str = Field(pattern=r'^\d{1,30}$')
    period_start: datetime
    period_end: datetime
    available_at: datetime
    actual: int = Field(ge=0, le=1_000_000_000, strict=True)
    unit: Literal['units', 'purchases']
    source_ref: str = Field(min_length=3, max_length=500)
    attestation: str = Field(min_length=20, max_length=1000)

    @field_validator('period_start', 'period_end', 'available_at')
    @classmethod
    def timestamps(cls, value):
        return utc(value)

    @model_validator(mode='after')
    def complete_period(self):
        if not self.period_start < self.period_end <= self.available_at <= datetime.now(timezone.utc):
            raise ValueError('Actual outcomes need a completed period and known availability')
        return self
