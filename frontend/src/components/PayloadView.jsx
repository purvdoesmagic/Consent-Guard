// Displays a decrypted synthetic record payload as key/value pairs.
export default function PayloadView({ payload }) {
  return (
    <div className="payload" aria-label="Decrypted record content">
      <dl>
        {Object.entries(payload).map(([key, value]) => (
          <div key={key} style={{ display: "contents" }}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
