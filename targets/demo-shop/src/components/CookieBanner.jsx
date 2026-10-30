// Planted defect: the banner covers the last button on the page, and the page has no bottom padding to make room.
export default function CookieBanner() {
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 h-32 bg-neutral-900 p-4 text-white">
      <p className="text-sm">We use cookies to improve your experience.</p>
    </div>
  )
}
