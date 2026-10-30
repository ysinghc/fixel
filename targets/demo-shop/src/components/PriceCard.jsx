// Planted defect: a fixed width wider than a phone.
export default function PriceCard() {
  return (
    <div className="w-[480px] rounded-2xl border bg-white p-6">
      <h2 className="text-xl font-semibold">Starter plan</h2>
      <p className="mt-2 text-neutral-700">Everything you need to get going, billed monthly.</p>
      <p className="mt-4 text-3xl font-bold">$12</p>
    </div>
  )
}
