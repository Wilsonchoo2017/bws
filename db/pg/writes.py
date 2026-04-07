"""Postgres write helpers for repository code.

Each function takes a SQLAlchemy Session and writes to Postgres.
Failures are logged and swallowed to avoid breaking the caller.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("bws.pg.writes")


def pg_write(fn_name: str):
    """Decorator that catches and logs Postgres write failures."""
    def decorator(fn):
        def wrapper(pg: "Session", *args: Any, **kwargs: Any) -> None:
            try:
                fn(pg, *args, **kwargs)
                pg.flush()
            except Exception:
                logger.warning("PG write failed: %s", fn_name, exc_info=True)
                pg.rollback()
        return wrapper
    return decorator


def _get_pg(conn: Any) -> "Session | None":
    """Extract Postgres session from a DualWriter, or return None."""
    if hasattr(conn, "pg_session"):
        return conn.pg_session()
    return None


# -- lego_items --

@pg_write("upsert_lego_item")
def pg_upsert_lego_item(
    pg: "Session",
    set_number: str,
    *,
    title: str | None = None,
    theme: str | None = None,
    year_released: int | None = None,
    year_retired: int | None = None,
    parts_count: int | None = None,
    weight: str | None = None,
    image_url: str | None = None,
    rrp_cents: int | None = None,
    rrp_currency: str | None = None,
    retiring_soon: bool | None = None,
    minifig_count: int | None = None,
    dimensions: str | None = None,
    release_date: str | None = None,
    retired_date: str | None = None,
) -> None:
    """Upsert a lego_items row in Postgres."""
    from db.pg.models.catalog import LegoItem

    existing = pg.query(LegoItem).filter_by(set_number=set_number).first()
    if existing is None:
        obj = LegoItem(
            set_number=set_number,
            title=title,
            theme=theme,
            year_released=year_released,
            year_retired=year_retired,
            parts_count=parts_count,
            weight=weight,
            image_url=image_url,
            rrp_cents=rrp_cents,
            rrp_currency=rrp_currency,
            retiring_soon=retiring_soon,
            minifig_count=minifig_count,
            dimensions=dimensions,
            release_date=release_date,
            retired_date=retired_date,
        )
        pg.add(obj)
    else:
        # COALESCE semantics: only update if new value is not None
        if title is not None:
            existing.title = title
        if theme is not None:
            existing.theme = theme
        if year_released is not None:
            existing.year_released = year_released
        if year_retired is not None:
            existing.year_retired = year_retired
        if parts_count is not None:
            existing.parts_count = parts_count
        if weight is not None:
            existing.weight = weight
        if image_url is not None:
            existing.image_url = image_url
        if rrp_cents is not None:
            existing.rrp_cents = rrp_cents
        if rrp_currency is not None:
            existing.rrp_currency = rrp_currency
        if retiring_soon is not None:
            existing.retiring_soon = retiring_soon
        if minifig_count is not None:
            existing.minifig_count = minifig_count
        if dimensions is not None:
            existing.dimensions = dimensions
        if release_date is not None:
            existing.release_date = release_date
        if retired_date is not None:
            existing.retired_date = retired_date


# -- price_records --

@pg_write("insert_price_record")
def pg_insert_price_record(
    pg: "Session",
    set_number: str,
    source: str,
    price_cents: int,
    *,
    currency: str = "MYR",
    title: str | None = None,
    url: str | None = None,
    shop_name: str | None = None,
    condition: str | None = None,
) -> None:
    """Insert a price_records row in Postgres."""
    from db.pg.models.market import PriceRecord

    obj = PriceRecord(
        set_number=set_number,
        source=source,
        price_cents=price_cents,
        currency=currency,
        title=title,
        url=url,
        shop_name=shop_name,
        condition=condition,
    )
    pg.add(obj)


# -- lego_items updates --

@pg_write("update_buy_rating")
def pg_update_buy_rating(
    pg: "Session", set_number: str, rating: int | None
) -> None:
    """Update buy_rating in Postgres."""
    from db.pg.models.catalog import LegoItem

    item = pg.query(LegoItem).filter_by(set_number=set_number).first()
    if item is not None:
        item.buy_rating = rating


@pg_write("toggle_watchlist")
def pg_toggle_watchlist(
    pg: "Session", set_number: str, new_value: bool
) -> None:
    """Set watchlist value in Postgres."""
    from db.pg.models.catalog import LegoItem

    item = pg.query(LegoItem).filter_by(set_number=set_number).first()
    if item is not None:
        item.watchlist = new_value


@pg_write("delete_item")
def pg_delete_item(pg: "Session", set_number: str) -> None:
    """Delete a lego_items row and all related data in Postgres."""
    from db.pg.models.catalog import LegoItem
    from db.pg.models.market import PriceRecord, ShopeeSaturation
    from db.pg.models.minifigures import SetMinifigure
    from db.pg.models.ml import MlFeatureStore
    from db.pg.models.other import ImageAsset
    from db.pg.models.scrape_queue import ScrapeTask
    from db.pg.models.snapshots import (
        BrickeconomySnapshot,
        GoogleTrendsSnapshot,
        KeepaSnapshot,
    )

    pg.query(PriceRecord).filter_by(set_number=set_number).delete()
    pg.query(BrickeconomySnapshot).filter_by(set_number=set_number).delete()
    pg.query(KeepaSnapshot).filter_by(set_number=set_number).delete()
    pg.query(GoogleTrendsSnapshot).filter_by(set_number=set_number).delete()
    pg.query(ShopeeSaturation).filter_by(set_number=set_number).delete()
    pg.query(ScrapeTask).filter_by(set_number=set_number).delete()
    pg.query(MlFeatureStore).filter_by(set_number=set_number).delete()
    pg.query(SetMinifigure).filter_by(set_item_id=set_number).delete()
    pg.query(ImageAsset).filter(
        ImageAsset.asset_type == "set", ImageAsset.item_id == set_number
    ).delete()
    pg.query(LegoItem).filter_by(set_number=set_number).delete()


# -- brickeconomy_snapshots --

@pg_write("insert_be_snapshot")
def pg_insert_be_snapshot(pg: "Session", **kwargs: Any) -> None:
    """Insert a brickeconomy_snapshots row in Postgres."""
    from db.pg.models.snapshots import BrickeconomySnapshot

    obj = BrickeconomySnapshot(**kwargs)
    pg.add(obj)


# -- keepa_snapshots --

@pg_write("insert_keepa_snapshot")
def pg_insert_keepa_snapshot(pg: "Session", **kwargs: Any) -> None:
    """Insert a keepa_snapshots row in Postgres."""
    from db.pg.models.snapshots import KeepaSnapshot

    obj = KeepaSnapshot(**kwargs)
    pg.add(obj)


# -- google_trends_snapshots --

@pg_write("insert_gtrends_snapshot")
def pg_insert_gtrends_snapshot(pg: "Session", **kwargs: Any) -> None:
    """Insert a google_trends_snapshots row in Postgres."""
    from db.pg.models.snapshots import GoogleTrendsSnapshot

    obj = GoogleTrendsSnapshot(**kwargs)
    pg.add(obj)


# -- bricklink writes --

@pg_write("insert_bricklink_price_history")
def pg_insert_bricklink_price_history(pg: "Session", **kwargs: Any) -> None:
    """Insert a bricklink_price_history row in Postgres."""
    from db.pg.models.snapshots import BricklinkPriceHistory

    obj = BricklinkPriceHistory(**kwargs)
    pg.add(obj)


@pg_write("upsert_bricklink_monthly_sales")
def pg_upsert_bricklink_monthly_sales(pg: "Session", **kwargs: Any) -> None:
    """Upsert a bricklink_monthly_sales row in Postgres."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.pg.models.market import BricklinkMonthlySales

    stmt = pg_insert(BricklinkMonthlySales).values(**kwargs)
    update_cols = {
        k: v for k, v in kwargs.items()
        if k not in ("item_id", "year", "month", "condition")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_bricklink_monthly_sales",
        set_=update_cols,
    )
    pg.execute(stmt)


@pg_write("upsert_bricklink_item")
def pg_upsert_bricklink_item(pg: "Session", **kwargs: Any) -> None:
    """Upsert a bricklink_items row in Postgres."""
    from db.pg.models.catalog import BricklinkItem

    item_id = kwargs.get("item_id")
    existing = pg.query(BricklinkItem).filter_by(item_id=item_id).first()
    if existing is None:
        pg.add(BricklinkItem(**kwargs))
    else:
        for key, val in kwargs.items():
            if val is not None and key != "item_id":
                setattr(existing, key, val)


# -- minifigures --

@pg_write("upsert_minifigure")
def pg_upsert_minifigure(pg: "Session", **kwargs: Any) -> None:
    """Upsert a minifigures row in Postgres."""
    from db.pg.models.minifigures import Minifigure

    minifig_id = kwargs.get("minifig_id")
    existing = pg.query(Minifigure).filter_by(minifig_id=minifig_id).first()
    if existing is None:
        pg.add(Minifigure(**kwargs))
    else:
        for key, val in kwargs.items():
            if val is not None and key != "minifig_id":
                setattr(existing, key, val)


@pg_write("upsert_set_minifigure")
def pg_upsert_set_minifigure(pg: "Session", **kwargs: Any) -> None:
    """Upsert a set_minifigures row in Postgres."""
    from db.pg.models.minifigures import SetMinifigure

    existing = pg.query(SetMinifigure).filter_by(
        set_item_id=kwargs["set_item_id"],
        minifig_id=kwargs["minifig_id"],
    ).first()
    if existing is None:
        pg.add(SetMinifigure(**kwargs))
    else:
        if "quantity" in kwargs:
            existing.quantity = kwargs["quantity"]


@pg_write("insert_minifig_price_history")
def pg_insert_minifig_price_history(pg: "Session", **kwargs: Any) -> None:
    """Insert a minifig_price_history row in Postgres."""
    from db.pg.models.snapshots import MinifigPriceHistorySnapshot

    obj = MinifigPriceHistorySnapshot(**kwargs)
    pg.add(obj)


# -- shopee --

@pg_write("upsert_shopee_product")
def pg_upsert_shopee_product(pg: "Session", **kwargs: Any) -> None:
    """Upsert a shopee_products row in Postgres."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.pg.models.market import ShopeeProduct

    stmt = pg_insert(ShopeeProduct).values(**kwargs)
    update_cols = {k: v for k, v in kwargs.items() if k != "product_url"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["product_url"],
        set_=update_cols,
    )
    pg.execute(stmt)


@pg_write("insert_scrape_history")
def pg_insert_scrape_history(pg: "Session", **kwargs: Any) -> None:
    """Insert a shopee_scrape_history row in Postgres."""
    from db.pg.models.market import ShopeeScrapeHistory

    pg.add(ShopeeScrapeHistory(**kwargs))


@pg_write("insert_saturation_snapshot")
def pg_insert_saturation_snapshot(pg: "Session", **kwargs: Any) -> None:
    """Insert a shopee_saturation row in Postgres."""
    from db.pg.models.market import ShopeeSaturation

    pg.add(ShopeeSaturation(**kwargs))


# -- mightyutan / toysrus --

@pg_write("upsert_mightyutan_product")
def pg_upsert_mightyutan_product(pg: "Session", **kwargs: Any) -> None:
    """Upsert a mightyutan_products row in Postgres."""
    from db.pg.models.other import MightyutanProduct

    sku = kwargs.get("sku")
    existing = pg.query(MightyutanProduct).filter_by(sku=sku).first()
    if existing is None:
        pg.add(MightyutanProduct(**kwargs))
    else:
        for key, val in kwargs.items():
            if val is not None and key != "sku":
                setattr(existing, key, val)


@pg_write("insert_mightyutan_price_history")
def pg_insert_mightyutan_price_history(pg: "Session", **kwargs: Any) -> None:
    """Insert a mightyutan_price_history row in Postgres."""
    from db.pg.models.snapshots import MightyutanPriceHistory

    pg.add(MightyutanPriceHistory(**kwargs))


@pg_write("upsert_toysrus_product")
def pg_upsert_toysrus_product(pg: "Session", **kwargs: Any) -> None:
    """Upsert a toysrus_products row in Postgres."""
    from db.pg.models.other import ToysrusProduct

    sku = kwargs.get("sku")
    existing = pg.query(ToysrusProduct).filter_by(sku=sku).first()
    if existing is None:
        pg.add(ToysrusProduct(**kwargs))
    else:
        for key, val in kwargs.items():
            if val is not None and key != "sku":
                setattr(existing, key, val)


@pg_write("insert_toysrus_price_history")
def pg_insert_toysrus_price_history(pg: "Session", **kwargs: Any) -> None:
    """Insert a toysrus_price_history row in Postgres."""
    from db.pg.models.snapshots import ToysrusPriceHistory

    pg.add(ToysrusPriceHistory(**kwargs))


# -- portfolio --

@pg_write("insert_portfolio_transaction")
def pg_insert_portfolio_transaction(pg: "Session", **kwargs: Any) -> None:
    """Insert a portfolio_transactions row in Postgres."""
    from db.pg.models.portfolio import PortfolioTransaction

    pg.add(PortfolioTransaction(**kwargs))


@pg_write("delete_portfolio_transaction")
def pg_delete_portfolio_transaction(pg: "Session", txn_id: int) -> None:
    """Delete a portfolio_transactions row in Postgres."""
    from db.pg.models.portfolio import PortfolioTransaction

    pg.query(PortfolioTransaction).filter_by(id=txn_id).delete()


# -- images --

@pg_write("upsert_image_asset")
def pg_upsert_image_asset(pg: "Session", **kwargs: Any) -> None:
    """Upsert an image_assets row in Postgres."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.pg.models.other import ImageAsset

    stmt = pg_insert(ImageAsset).values(**kwargs)
    update_cols = {
        k: v for k, v in kwargs.items()
        if k not in ("asset_type", "item_id")
    }
    if update_cols:
        stmt = stmt.on_conflict_do_update(
            constraint="uq_image_assets",
            set_=update_cols,
        )
    else:
        stmt = stmt.on_conflict_do_nothing(constraint="uq_image_assets")
    pg.execute(stmt)


@pg_write("mark_image_downloaded")
def pg_mark_image_downloaded(
    pg: "Session", asset_type: str, item_id: str, **kwargs: Any
) -> None:
    """Update image_assets status to downloaded."""
    from db.pg.models.other import ImageAsset

    asset = pg.query(ImageAsset).filter_by(
        asset_type=asset_type, item_id=item_id
    ).first()
    if asset is not None:
        for key, val in kwargs.items():
            setattr(asset, key, val)


@pg_write("mark_image_failed")
def pg_mark_image_failed(
    pg: "Session", asset_type: str, item_id: str, **kwargs: Any
) -> None:
    """Update image_assets status to failed."""
    from db.pg.models.other import ImageAsset

    asset = pg.query(ImageAsset).filter_by(
        asset_type=asset_type, item_id=item_id
    ).first()
    if asset is not None:
        for key, val in kwargs.items():
            setattr(asset, key, val)


# -- ML --

@pg_write("insert_ml_prediction_snapshot")
def pg_insert_ml_prediction_snapshot(pg: "Session", **kwargs: Any) -> None:
    """Insert a ml_prediction_snapshots row (ON CONFLICT DO NOTHING)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from db.pg.models.ml import MlPredictionSnapshot

    stmt = pg_insert(MlPredictionSnapshot).values(**kwargs)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_ml_prediction_snapshot")
    pg.execute(stmt)


@pg_write("backfill_ml_actuals")
def pg_backfill_ml_actuals(
    pg: "Session",
    snapshot_date: Any,
    set_number: str,
    actual_growth_pct: float,
    actual_measured_at: Any,
) -> None:
    """Update actual values in ml_prediction_snapshots."""
    from db.pg.models.ml import MlPredictionSnapshot

    row = pg.query(MlPredictionSnapshot).filter_by(
        snapshot_date=snapshot_date, set_number=set_number
    ).first()
    if row is not None:
        row.actual_growth_pct = actual_growth_pct
        row.actual_measured_at = actual_measured_at
