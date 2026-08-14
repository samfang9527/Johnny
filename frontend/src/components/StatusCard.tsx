type StatusCardProps = {
  title: string
  value: string
  detail: string
}

export function StatusCard({ title, value, detail }: StatusCardProps) {
  return (
    <article className="status-card">
      <p className="status-card__title">{title}</p>
      <h2 className="status-card__value">{value}</h2>
      <p className="status-card__detail">{detail}</p>
    </article>
  )
}

