/**
 * Test fixtures for Shopee parser tests
 * Real HTML samples extracted from Shopee product listings
 */

/**
 * Complete product with all fields populated:
 * - Product name with LEGO set number
 * - Price with discount
 * - Sold units in "1k+" format
 * - Multiple badges (Shopee Lagi Murah, COD)
 * - Rating
 */
export const PRODUCT_WITH_DISCOUNT_AND_BADGES =
  `<div class="shop-search-result-view__item col-xs-2-4"><div style="height: 100%;"><div class="shopee_ic" style="display: contents;"><div class="h-full h-full duration-100 ease-sharp-motion-curve hover:shadow-hover active:shadow-active hover:-translate-y-[1px] active:translate-y-0 relative hover:z-[10] box-content relative border border-solid border-shopee-black9" aria-hidden="true" style="border-radius: 6px; box-sizing: border-box;"><a class="contents" href="/LEGO-Speed-Champions-77243-Oracle-Red-Bull-Racing-RB20-F1-Race-Car-(251-Pieces)-i.77251500.29577244923?extraParams=%7B%22display_model_id%22%3A198242610420%7D"><div class="flex flex-col bg-white cursor-pointer h-full overflow-hidden" style="border-radius: 6px;"><div class="w-full relative z-0" style="padding-top: 100%;"><img src="https://down-my.img.susercontent.com/file/my-11134207-7rasi-m6m79x9dqdzt5d_tn.webp" alt="LEGO Speed Champions 77243 Oracle Red Bull Racing RB20 F1 Race Car (251 Pieces)" class="inset-y-0 w-full h-full pointer-events-none object-contain absolute" loading="lazy" aria-hidden="true"><div class="absolute bottom-0 left-0 z-10 w-full w-full h-hull" aria-label="image overlay,src:https://down-my.img.susercontent.com/file/my-11134258-820l9-mgpydgiolafhe3"><img src="https://down-my.img.susercontent.com/file/my-11134258-820l9-mgpydgiolafhe3" class="w-full" alt="custom-overlay"></div><div class="absolute bottom-0 right-0 z-30 flex pr-1 pb-1" aria-hidden="true"><div data-testid="badge-video" class="w-5 h-5 stroke-none" style="background-image: url(&quot;https://deo.shopeemobile.com/shopee/modules-federation/live/0/shopee__item-card-centralisation/0.0.57/pc/43bd6a890841685e2fea.svg&quot;); background-size: cover; background-repeat: no-repeat;"></div></div></div><div class="p-2 flex-1 flex flex-col justify-between"><div class="space-y-1 mb-1 flex-1 flex flex-col justify-between"><div class="line-clamp-2 break-words min-w-0 min-h-[2.5rem] text-sm th:text-[12px] my:text-[12px] km:text-[12px]"><img src="https://down-my.img.susercontent.com/file/my-11134258-7r98t-lyaneblda3c031" alt="flag-label" class="mr-0.5 inline-block h-sp14">LEGO Speed Champions 77243 Oracle Red Bull Racing RB20 F1 Race Car (251 Pieces)</div><div class="flex items-center flex items-center" style="visibility: visible;"><div class="max-w-full min-w-0 flex-grow-1 flex-shrink-0 mr-1 truncate text-shopee-primary flex items-center font-medium"><span data-testid="a11y-label" aria-label="promotion price"></span><div class="truncate flex items-baseline"><span class="font-medium mr-px text-xs/sp14">RM</span><span class="truncate text-base/5 font-medium">126.00</span><span class="font-medium mr-px text-xs/sp14"></span></div></div><div class="text-shopee-primary font-medium bg-shopee-pink py-0.5 px-1 rounded-bl-[6px] text-sp10/3 h-4 flex items-center rounded-[2px] flex-shrink-0 mr-1"><span data-testid="a11y-label" aria-label="-3%"></span>-3%</div></div></div><div class="flex flex-col justify-between flex-1"><div class="box-border flex space-x-1 h-5 text-[0.625rem] my:text-[0.5rem] th:text-[0.5rem] km:text-[0.5rem] items-center self-auto overflow-hidden mb-2 flex items-center" aria-hidden="true"><div class="" style="width: auto;"><div class="relative relative flex items-center text-[0.625rem] my:text-[0.5rem] km:text-[0.5rem] leading-4 py-0.5 px-1 h-4 pointer-events-none text-ellipsis overflow-hidden max-w-full" style="margin: 1px; box-shadow: rgb(238, 77, 45) 0px 0px 0px 0.5px; border-radius: 2px;"><span class="truncate" style="color: rgb(238, 77, 45);">Shopee Lagi Murah</span></div></div><div class="" style="width: auto;"><div class="relative relative flex items-center text-[0.625rem] my:text-[0.5rem] km:text-[0.5rem] leading-4 py-0.5 px-1 h-4 pointer-events-none text-ellipsis overflow-hidden max-w-full" style="margin: 1px; box-shadow: rgb(38, 170, 153) 0px 0px 0px 0.5px; border-radius: 2px;"><span class="truncate" style="color: rgb(38, 170, 153);">COD</span></div></div></div><div class="flex items-center max-w-full space-x-1 justify-between mb-2" style="visibility: visible;"><div class="flex items-center space-x-1 min-w-0"><div class="relative px-1 flex items-center space-x-0.5 h-[1.125rem] flex-none" style="background-color: rgb(255, 248, 228); margin: 1px; box-shadow: rgb(255, 187, 0) 0px 0px 0px 0.5px; border-radius: 2px;"><img src="https://down-my.img.susercontent.com/file/id-11134258-7r98o-ly1pxywrszyh0b_tn.webp" alt="rating-star" class="inline-block align-middle" style="height: 0.625rem; width: 0.625rem;"><span class="inline-block truncate text-xs/sp14" style="color: rgb(0, 0, 0);">4.9</span></div><div class="ml-1 h-sp10 scale-x-50 border-l border-shopee-black9 mx-1"></div><div class="truncate text-shopee-black87 text-xs min-h-4 flex-shrink">1k+ sold</div></div></div></div><div class="flex-shrink"></div></div></div></a></div></div></div></div>`;

/**
 * Product with numeric sold units (no "k+" suffix):
 * - Regular sold count: 666
 * - Multiple badges (COD, Sea Shipping)
 * - 6% discount
 */
export const PRODUCT_WITH_NUMERIC_SOLD =
  `<div class="shop-search-result-view__item col-xs-2-4"><div style="height: 100%;"><div class="shopee_ic" style="display: contents;"><div class="h-full h-full duration-100 ease-sharp-motion-curve hover:shadow-hover active:shadow-active hover:-translate-y-[1px] active:translate-y-0 relative hover:z-[10] box-content relative border border-solid border-shopee-black9" aria-hidden="true" style="border-radius: 6px; box-sizing: border-box;"><a class="contents" href="/LEGO-Speed-Champions-77251-McLaren-F1-Team-MCL38-Race-Car-(269-Pieces)-i.77251500.28477273267?extraParams=%7B%22display_model_id%22%3A247714991641%7D"><div class="flex flex-col bg-white cursor-pointer h-full overflow-hidden" style="border-radius: 6px;"><div class="w-full relative z-0" style="padding-top: 100%;"><img src="https://down-my.img.susercontent.com/file/my-11134207-7rasf-m6me84n6mvlld8_tn.webp" alt="LEGO Speed Champions 77251 McLaren F1 Team MCL38 Race Car (269 Pieces)" class="inset-y-0 w-full h-full pointer-events-none object-contain absolute" loading="lazy" aria-hidden="true"><div class="absolute bottom-0 left-0 z-10 w-full w-full h-hull" aria-label="image overlay,src:https://down-my.img.susercontent.com/file/my-11134258-820l9-mgpydgiolafhe3"><img src="https://down-my.img.susercontent.com/file/my-11134258-820l9-mgpydgiolafhe3" class="w-full" alt="custom-overlay"></div><div class="absolute bottom-0 right-0 z-30 flex pr-1 pb-1" aria-hidden="true"><div data-testid="badge-video" class="w-5 h-5 stroke-none" style="background-image: url(&quot;https://deo.shopeemobile.com/shopee/modules-federation/live/0/shopee__item-card-centralisation/0.0.57/pc/43bd6a890841685e2fea.svg&quot;); background-size: cover; background-repeat: no-repeat;"></div></div></div><div class="p-2 flex-1 flex flex-col justify-between"><div class="space-y-1 mb-1 flex-1 flex flex-col justify-between"><div class="line-clamp-2 break-words min-w-0 min-h-[2.5rem] text-sm th:text-[12px] my:text-[12px] km:text-[12px]"><img src="https://down-my.img.susercontent.com/file/my-11134258-7r98t-lyaneblda3c031" alt="flag-label" class="mr-0.5 inline-block h-sp14">LEGO Speed Champions 77251 McLaren F1 Team MCL38 Race Car (269 Pieces)</div><div class="flex items-center flex items-center" style="visibility: visible;"><div class="max-w-full min-w-0 flex-grow-1 flex-shrink-0 mr-1 truncate text-shopee-primary flex items-center font-medium"><span data-testid="a11y-label" aria-label="promotion price"></span><div class="truncate flex items-baseline"><span class="font-medium mr-px text-xs/sp14">RM</span><span class="truncate text-base/5 font-medium">122.11</span><span class="font-medium mr-px text-xs/sp14"></span></div></div><div class="text-shopee-primary font-medium bg-shopee-pink py-0.5 px-1 rounded-bl-[6px] text-sp10/3 h-4 flex items-center rounded-[2px] flex-shrink-0 mr-1"><span data-testid="a11y-label" aria-label="-6%"></span>-6%</div></div></div><div class="flex flex-col justify-between flex-1"><div class="box-border flex space-x-1 h-5 text-[0.625rem] my:text-[0.5rem] th:text-[0.5rem] km:text-[0.5rem] items-center self-auto overflow-hidden mb-2 flex items-center" aria-hidden="true"><div class="" style="width: auto;"><div class="relative relative flex items-center text-[0.625rem] my:text-[0.5rem] km:text-[0.5rem] leading-4 py-0.5 px-1 h-4 pointer-events-none text-ellipsis overflow-hidden max-w-full" style="margin: 1px; box-shadow: rgb(38, 170, 153) 0px 0px 0px 0.5px; border-radius: 2px;"><span class="truncate" style="color: rgb(38, 170, 153);">COD</span></div></div><div class="" style="width: auto;"><div class="relative relative flex items-center text-[0.625rem] my:text-[0.5rem] km:text-[0.5rem] leading-4 py-0.5 px-1 h-4 pointer-events-none text-ellipsis overflow-hidden max-w-full" style="margin: 1px; box-shadow: rgb(38, 170, 153) 0px 0px 0px 0.5px; border-radius: 2px;"><span class="truncate" style="color: rgb(38, 170, 153);">Sea Shipping</span></div></div></div><div class="flex items-center max-w-full space-x-1 justify-between mb-2" style="visibility: visible;"><div class="flex items-center space-x-1 min-w-0"><div class="relative px-1 flex items-center space-x-0.5 h-[1.125rem] flex-none" style="background-color: rgb(255, 248, 228); margin: 1px; box-shadow: rgb(255, 187, 0) 0px 0px 0px 0.5px; border-radius: 2px;"><img src="https://down-my.img.susercontent.com/file/id-11134258-7r98o-ly1pxywrszyh0b_tn.webp" alt="rating-star" class="inline-block align-middle" style="height: 0.625rem; width: 0.625rem;"><span class="inline-block truncate text-xs/sp14" style="color: rgb(0, 0, 0);">5.0</span></div><div class="ml-1 h-sp10 scale-x-50 border-l border-shopee-black9 mx-1"></div><div class="truncate text-shopee-black87 text-xs min-h-4 flex-shrink">666 sold</div></div></div></div><div class="flex-shrink"></div></div></div></a></div></div></div></div>`;

/**
 * Full HTML with multiple products for integration testing
 */
export const SAMPLE_SHOPEE_HTML =
  `<div class="shop-search-result-view"><div class="row">${PRODUCT_WITH_DISCOUNT_AND_BADGES}${PRODUCT_WITH_NUMERIC_SOLD}</div></div>`;

/**
 * Expected parsed output for PRODUCT_WITH_DISCOUNT_AND_BADGES
 * (excluding product_id which is randomly generated)
 */
export const EXPECTED_PRODUCT_1 = {
  product_name:
    "LEGO Speed Champions 77243 Oracle Red Bull Racing RB20 F1 Race Car (251 Pieces)",
  brand: "LEGO",
  lego_set_number: "77243",
  price: 12600, // RM126.00 in cents
  price_string: "126.00", // Parser returns numeric portion without "RM"
  discount_percentage: 3,
  price_before_discount: 12990, // Calculated: 12600 / (1 - 0.03) rounded
  promotional_badges: ["shopeelagimurah", "cod", "verified"], // Includes flag-label badge
  units_sold: 1000, // "1k+" normalized
  units_sold_string: "1k+ sold",
  image:
    "https://down-my.img.susercontent.com/file/my-11134207-7rasi-m6m79x9dqdzt5d_tn.webp",
  product_url:
    "https://shopee.com.my/LEGO-Speed-Champions-77243-Oracle-Red-Bull-Racing-RB20-F1-Race-Car-(251-Pieces)-i.77251500.29577244923?extraParams=%7B%22display_model_id%22%3A198242610420%7D",
  shop_id: null,
  shop_name: "legoshopmy",
};

/**
 * Expected parsed output for PRODUCT_WITH_NUMERIC_SOLD
 */
export const EXPECTED_PRODUCT_2 = {
  product_name:
    "LEGO Speed Champions 77251 McLaren F1 Team MCL38 Race Car (269 Pieces)",
  brand: "LEGO",
  lego_set_number: "77251",
  price: 12211, // RM122.11 in cents
  price_string: "122.11", // Parser returns numeric portion without "RM"
  discount_percentage: 6,
  price_before_discount: 12990, // Calculated: 12211 / (1 - 0.06) rounded
  promotional_badges: ["cod", "seashipping", "verified"], // Includes flag-label badge
  units_sold: 666,
  units_sold_string: "666 sold",
  image:
    "https://down-my.img.susercontent.com/file/my-11134207-7rasf-m6me84n6mvlld8_tn.webp",
  product_url:
    "https://shopee.com.my/LEGO-Speed-Champions-77251-McLaren-F1-Team-MCL38-Race-Car-(269-Pieces)-i.77251500.28477273267?extraParams=%7B%22display_model_id%22%3A247714991641%7D",
  shop_id: null,
  shop_name: "legoshopmy",
};

/**
 * Edge case: Minimal product HTML (missing optional fields)
 */
export const PRODUCT_MINIMAL =
  `<div class="shop-search-result-view__item col-xs-2-4">
  <div class="line-clamp-2">Simple Product Name</div>
  <div class="truncate flex items-baseline">
    <span>RM</span>
    <span>99.99</span>
  </div>
</div>`;

/**
 * Edge case: Product with no LEGO set number
 */
export const PRODUCT_WITHOUT_SET_NUMBER =
  `<div class="shop-search-result-view__item col-xs-2-4">
  <div class="line-clamp-2">Generic Building Blocks Set</div>
  <div class="truncate flex items-baseline">
    <span>RM</span>
    <span>50.00</span>
  </div>
</div>`;

/**
 * Edge case: Empty HTML
 */
export const EMPTY_HTML =
  `<div class="shop-search-result-view"><div class="row"></div></div>`;

/**
 * Edge case: Malformed HTML
 */
export const MALFORMED_HTML = `<div class="broken">`;
