import Code from '@leafygreen-ui/code';

/** Documento BSON renderizado como JSON escuro, fonte mono. */
export default function JsonViewer({ doc, flashKey }) {
  return (
    <div className={`json-scroll ${flashKey ? 'flash' : ''}`} key={flashKey}>
      <Code language="json" darkMode copyable={false}>
        {JSON.stringify(doc, null, 2)}
      </Code>
    </div>
  );
}
