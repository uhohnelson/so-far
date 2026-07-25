export default function NotFound({ path }: { path: string }) {
  return (
    <div className="login">
      <div className="mark">S</div>
      <div className="brand">sofar</div>
      <p className="tagline">
        Nothing at <code>{path}</code>
      </p>
      <a className="primary-btn" href="/" style={{ textDecoration: 'none' }}>
        Back to my list
      </a>
    </div>
  )
}
