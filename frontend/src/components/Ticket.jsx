// The recurring signature element: a torn-ticket card whose left rail
// color is the single signal for state (waiting / satisfied / closed /
// risk), echoing a paper trade ticket rather than a generic bordered box.
export default function Ticket({ color = 'var(--color-hairline)', children, className = '' }) {
  return (
    <div className={`ticket bg-surface rounded-r-md ${className}`} style={{ '--rail-color': color }}>
      {children}
    </div>
  )
}
