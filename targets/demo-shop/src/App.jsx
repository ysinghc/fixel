import PriceCard from './components/PriceCard.jsx'
import Perks from './components/Perks.jsx'
import CheckoutBar from './components/CheckoutBar.jsx'
import CookieBanner from './components/CookieBanner.jsx'

export default function App() {
  return (
    <div className="min-h-screen bg-neutral-100 text-neutral-900">
      <header className="border-b bg-white px-4 py-3 text-lg font-semibold">Demo shop</header>
      <main className="mx-auto max-w-3xl space-y-8 p-4">
        <h1 className="text-2xl font-bold">Weekend sale</h1>
        <PriceCard />
        <Perks />
        <CheckoutBar />
      </main>
      <CookieBanner />
    </div>
  )
}
