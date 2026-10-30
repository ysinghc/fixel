const PERKS = ['Free shipping', '30-day returns', 'Gift wrapping', 'Price match', 'Secure checkout', 'Member discounts']

// Planted defect: a row of chips that never wraps.
export default function Perks() {
  return (
    <section className="rounded-xl bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold">Perks</h2>
      <ul className="flex flex-nowrap gap-2">
        {PERKS.map((p) => (
          <li key={p} className="shrink-0 rounded-full border px-3 py-1 text-sm">
            {p}
          </li>
        ))}
      </ul>
    </section>
  )
}
