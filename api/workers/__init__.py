"""Worker registry -- maps scraper_id to source worker instances."""

from api.workers.brickeconomy import BrickeconomyWorker
from api.workers.bricklink_catalog import BricklinkCatalogWorker
from api.workers.carousell import CarousellWorker
from api.workers.enrichment import EnrichmentWorker
from api.workers.google_trends import GoogleTrendsWorker
from api.workers.keepa import KeepaWorker
from api.workers.mightyutan import MightyutanWorker
from api.workers.shopee import ShopeeWorker
from api.workers.shopee_saturation import ShopeeSaturationWorker
from api.workers.toysrus import ToysrusWorker

WORKER_REGISTRY = {
    w.scraper_id: w
    for w in [
        ShopeeWorker(),
        ToysrusWorker(),
        MightyutanWorker(),
        ShopeeSaturationWorker(),
        BricklinkCatalogWorker(),
        EnrichmentWorker(),
        CarousellWorker(),
        BrickeconomyWorker(),
        KeepaWorker(),
        GoogleTrendsWorker(),
    ]
}
