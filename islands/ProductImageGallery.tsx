import { useSignal } from "@preact/signals";

interface ProductImageGalleryProps {
  images: string[];
  productName: string;
}

export default function ProductImageGallery(
  { images, productName }: ProductImageGalleryProps,
) {
  const currentIndex = useSignal(0);
  const imageError = useSignal<Set<number>>(new Set());

  // Handle empty or invalid images array
  const validImages = images && images.length > 0
    ? images
    : ["/api/placeholder/400/400"];

  const goToPrevious = () => {
    currentIndex.value = currentIndex.value === 0
      ? validImages.length - 1
      : currentIndex.value - 1;
  };

  const goToNext = () => {
    currentIndex.value = currentIndex.value === validImages.length - 1
      ? 0
      : currentIndex.value + 1;
  };

  const goToImage = (index: number) => {
    currentIndex.value = index;
  };

  const handleImageError = (index: number) => {
    const errors = new Set(imageError.value);
    errors.add(index);
    imageError.value = errors;
  };

  const currentImage = validImages[currentIndex.value];
  const hasError = imageError.value.has(currentIndex.value);

  return (
    <div class="w-full space-y-4">
      {/* Main Image Display */}
      <div class="relative w-full aspect-square bg-base-200 rounded-lg overflow-hidden">
        {hasError
          ? (
            <div class="w-full h-full flex items-center justify-center text-base-content/50">
              <div class="text-center">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="h-16 w-16 mx-auto mb-2"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                <p>Image not available</p>
              </div>
            </div>
          )
          : (
            <img
              src={currentImage}
              alt={`${productName} - Image ${currentIndex.value + 1}`}
              class="w-full h-full object-contain"
              onError={() => handleImageError(currentIndex.value)}
            />
          )}

        {/* Navigation Buttons (only show if multiple images) */}
        {validImages.length > 1 && (
          <>
            <button
              onClick={goToPrevious}
              class="btn btn-sm btn-circle btn-outline absolute left-2 top-1/2 -translate-y-1/2 bg-base-100/80 hover:bg-base-100"
              aria-label="Previous image"
            >
              ❮
            </button>
            <button
              onClick={goToNext}
              class="btn btn-sm btn-circle btn-outline absolute right-2 top-1/2 -translate-y-1/2 bg-base-100/80 hover:bg-base-100"
              aria-label="Next image"
            >
              ❯
            </button>
          </>
        )}

        {/* Image Counter Badge */}
        {validImages.length > 1 && (
          <div class="badge badge-neutral absolute top-2 right-2 bg-base-100/80">
            {currentIndex.value + 1} / {validImages.length}
          </div>
        )}
      </div>

      {/* Thumbnail Navigation (only show if multiple images) */}
      {validImages.length > 1 && (
        <div class="flex gap-2 overflow-x-auto pb-2">
          {validImages.map((image, index) => (
            <button
              key={index}
              onClick={() => goToImage(index)}
              class={`flex-shrink-0 w-20 h-20 rounded-lg overflow-hidden border-2 transition-all ${
                currentIndex.value === index
                  ? "border-primary shadow-lg"
                  : "border-base-300 opacity-60 hover:opacity-100"
              }`}
              aria-label={`View image ${index + 1}`}
            >
              {imageError.value.has(index)
                ? (
                  <div class="w-full h-full bg-base-200 flex items-center justify-center">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      class="h-8 w-8 text-base-content/30"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </div>
                )
                : (
                  <img
                    src={image}
                    alt={`Thumbnail ${index + 1}`}
                    class="w-full h-full object-cover"
                    onError={() => handleImageError(index)}
                  />
                )}
            </button>
          ))}
        </div>
      )}

      {/* Indicator Dots (alternative to thumbnails for many images) */}
      {validImages.length > 10 && (
        <div class="flex gap-1 justify-center">
          {validImages.map((_, index) => (
            <button
              key={index}
              onClick={() => goToImage(index)}
              class={`badge badge-xs ${
                currentIndex.value === index ? "badge-primary" : "badge-ghost"
              }`}
              aria-label={`Go to image ${index + 1}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
