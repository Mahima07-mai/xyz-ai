export default function Tabs({ items, tab, onChange }) {
  return (
    <div className="mb-4 flex flex-wrap gap-1 rounded-xl bg-white p-1 ring-1 ring-chalk-200">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => onChange(item.key)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            tab === item.key ? "bg-chalk-800 text-chalk-25" : "text-ink-600 hover:bg-chalk-25"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
