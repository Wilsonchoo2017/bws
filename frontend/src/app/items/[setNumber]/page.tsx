import { ItemDetailView } from '@/features/items/detail/item-detail';

export default async function ItemDetailPage({
  params
}: {
  params: Promise<{ setNumber: string }>;
}) {
  const { setNumber } = await params;

  return (
    <div className='flex h-screen flex-col p-6'>
      <ItemDetailView setNumber={setNumber} />
    </div>
  );
}
