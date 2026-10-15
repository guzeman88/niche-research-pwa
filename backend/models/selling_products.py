"""Private research inputs. Measurements retain their source, scope and dates."""
from datetime import date, datetime, timezone, timedelta
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Family = Literal['planner', 'worksheet', 'wall_art', 'mug', 'apparel', 'other']
Source = Literal['manual', 'everbee', 'alura', 'erank', 'ehunt', 'saved_research',
                 'seller_records', 'etsy_marketplace_insights', 'google_ads', 'other']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator('*', mode='before')
    @classmethod
    def no_boolean_numbers(cls, value, info):
        if isinstance(value, bool) and info.field_name in {'value', 'rating', 'readability'}:
            raise ValueError('Use a number, not a checkbox value')
        return value


class Opportunity(Input):
    name: str = Field(min_length=3, max_length=140)
    keyword: str = Field(min_length=3, max_length=160)
    family: Family = 'other'
    audience: str = Field(default='', max_length=500)
    buyer_task: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=2000)
    stage: Literal['watching', 'shortlisted', 'archived'] = 'watching'


class Listing(Input):
    listing_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    shop: str = Field(default='', max_length=120)
    url: str = Field(default='', max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    created_on: date | None = None
    source: Source = 'manual'
    source_ref: str = Field(min_length=3, max_length=1000)

    @field_validator('url')
    @classmethod
    def public_listing_url(cls, value):
        if value:
            parsed = urlparse(value)
            if parsed.scheme != 'https' or parsed.hostname not in ('etsy.com', 'www.etsy.com') or parsed.username or parsed.password:
                raise ValueError('Use an HTTPS Etsy listing URL, or leave the URL blank')
        return value

    @field_validator('tags')
    @classmethod
    def bounded_tags(cls, value):
        if any(not tag.strip() or len(tag) > 100 for tag in value):
            raise ValueError('Tags must contain 1–100 characters')
        return list(dict.fromkeys(tag.strip() for tag in value))

    @field_validator('created_on')
    @classmethod
    def creation_not_future(cls, value):
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError('Listing creation date cannot be in the future')
        return value


class Observation(Input):
    listing_id: str = Field(min_length=1, max_length=100)
    metric: Literal['estimated_sales', 'seller_reported_sales', 'reviews', 'favorites',
                    'shop_sales', 'price', 'keyword_searches', 'listing_count']
    value: float | None = Field(default=None, ge=0, le=1e12)
    basis: Literal['period', 'lifetime', 'lifetime_average', 'point_in_time'] = 'point_in_time'
    observed_at: datetime
    period_start: date | None = None
    period_end: date | None = None
    currency: str = Field(default='', pattern=r'^([A-Z]{3})?$')
    keyword: str = Field(default='', max_length=160)
    geography: str = Field(default='', max_length=80)
    source: Source = 'manual'
    source_ref: str = Field(min_length=3, max_length=1000)
    note: str = Field(default='', max_length=1500)

    @field_validator('observed_at')
    @classmethod
    def captured_date(cls, value):
        if value.tzinfo is None:
            raise ValueError('Observation time needs a timezone')
        value = value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('Observation time cannot be in the future')
        return value

    @model_validator(mode='after')
    def reporting_scope(self):
        if bool(self.period_start) != bool(self.period_end):
            raise ValueError('Supply both reporting dates')
        if self.period_start and (self.period_start > self.period_end or self.period_end > self.observed_at.date()):
            raise ValueError('Reporting dates must be ordered and no later than observation time')
        if self.basis == 'period' and not self.period_start:
            raise ValueError('Period measurements need a reporting window')
        if self.basis != 'period' and self.period_start:
            raise ValueError('Only period measurements take reporting dates')
        if self.metric in ('estimated_sales', 'seller_reported_sales') and self.basis == 'point_in_time':
            raise ValueError('Sales need a period, lifetime or lifetime-average basis')
        if self.metric == 'seller_reported_sales' and (self.source != 'seller_records' or len(self.note) < 10):
            raise ValueError('Seller-reported sales need seller records and an evidence note; they are not independently verified')
        if self.metric == 'keyword_searches' and (not self.keyword or not self.geography or self.basis != 'period'):
            raise ValueError('Search demand needs a keyword, geography and reporting window')
        if self.metric == 'price' and (not self.currency or self.basis != 'point_in_time'):
            raise ValueError('Price needs a currency and point-in-time basis')
        if self.metric in ('reviews', 'favorites', 'shop_sales') and self.basis != 'lifetime':
            raise ValueError('Review, favorite and shop-sales counters need a lifetime basis')
        if self.metric in ('reviews', 'favorites', 'shop_sales', 'listing_count', 'seller_reported_sales') and self.value is not None and self.value != int(self.value):
            raise ValueError('Counts must be whole numbers')
        if self.metric != 'price' and self.currency:
            raise ValueError('Currency applies only to price observations')
        return self


class Review(Input):
    review_id: str = Field(min_length=1, max_length=160)
    listing_id: str = Field(min_length=1, max_length=100)
    reviewed_on: date
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=5000)
    source_ref: str = Field(min_length=3, max_length=1000)

    @field_validator('reviewed_on')
    @classmethod
    def not_future(cls, value):
        if value > datetime.now(timezone.utc).date():
            raise ValueError('Review date cannot be in the future')
        return value


class Pattern(Input):
    listing_id: str = Field(min_length=1, max_length=100)
    typography: Literal['unknown', 'serif', 'sans_serif', 'handwritten', 'mixed'] = 'unknown'
    layout: Literal['unknown', 'minimal', 'structured', 'illustrated', 'text_led'] = 'unknown'
    palette: str = Field(default='', max_length=100)
    features: list[str] = Field(default_factory=list, max_length=20)
    readability: int | None = Field(default=None, ge=1, le=5)
    notes: str = Field(default='', max_length=1000)
    source_ref: str = Field(min_length=3, max_length=1000)

    @field_validator('features')
    @classmethod
    def bounded_features(cls, value):
        if any(not item.strip() or len(item) > 100 for item in value):
            raise ValueError('Features must contain 1–100 characters')
        return list(dict.fromkeys(item.casefold().strip() for item in value))


class Packet(Input):
    schema_version: Literal[1] = 1
    listings: list[Listing] = Field(default_factory=list, max_length=500)
    observations: list[Observation] = Field(default_factory=list, max_length=1000)
    reviews: list[Review] = Field(default_factory=list, max_length=1000)
    patterns: list[Pattern] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def bounded(self):
        if sum(len(getattr(self, key)) for key in ('listings', 'observations', 'reviews', 'patterns')) > 2000:
            raise ValueError('Import at most 2,000 rows at a time')
        return self


class Brief(Input):
    name: str = Field(min_length=3, max_length=120)
    buyer: str = Field(min_length=3, max_length=300)
    purpose: str = Field(min_length=10, max_length=2000)
    improvements: list[str] = Field(min_length=1, max_length=12)
    original_direction: str = Field(min_length=10, max_length=2000)
    family: Family
    notes: str = Field(default='', max_length=2000)

    @field_validator('improvements')
    @classmethod
    def clear_improvements(cls, value):
        if any(len(item.strip()) < 3 or len(item) > 500 for item in value):
            raise ValueError('Improvements need 3–500 characters each')
        return list(dict.fromkeys(item.strip() for item in value))
