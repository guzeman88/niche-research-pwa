import { useEffect } from 'react'
import LegalDocument from '../components/LegalDocument'

const sections = [
  {
    title: 'Using EtGen',
    body: <p>EtGen provides research, analysis, planning, and workflow tools for sellers. You must use the service lawfully, provide accurate account information, protect access to your account, and use connected marketplaces and data sources in accordance with their terms.</p>,
  },
  {
    title: 'Your workspace and content',
    body: <p>You retain ownership of the research, product ideas, listing drafts, and other material you add to your workspace. You grant EtGen the limited permission needed to store, process, and display that material so the service can work for you.</p>,
  },
  {
    title: 'Connected accounts',
    body: <p>When you connect a third-party account, you authorize EtGen to use the access you approve for the features you choose. You are responsible for the connected account and may revoke access through the third party. EtGen is not endorsed by Etsy, Google, or any other connected service unless explicitly stated.</p>,
  },
  {
    title: 'Research and generated suggestions',
    body: <p>Keyword metrics, competition estimates, trends, scores, product ideas, and generated copy are decision-support information, not guarantees of traffic, ranking, sales, profit, intellectual-property clearance, or marketplace approval. You are responsible for reviewing suggestions before using or publishing them.</p>,
  },
  {
    title: 'Prohibited use',
    body: <p>You may not use EtGen to violate law or marketplace rules, access data without authorization, interfere with the service, introduce malicious code, misrepresent ownership, or infringe another person's rights.</p>,
  },
  {
    title: 'Service availability',
    body: <p>EtGen may change, suspend, or discontinue features as the product develops or as third-party services change their APIs, permissions, or limits. Reasonable care is taken to keep the service reliable, but uninterrupted or error-free operation is not guaranteed.</p>,
  },
  {
    title: 'Limitation and changes',
    body: <p>To the extent permitted by law, EtGen is provided without warranties and is not liable for indirect, incidental, or consequential losses arising from use of the service. These terms may be updated as the product evolves; the current version and update date will remain available on this page.</p>,
  },
  {
    title: 'Contact',
    body: <p>Questions about these terms can be sent to the support address displayed on the EtGen Google consent screen or through the account area in the app.</p>,
  },
]

export default function Terms() {
  useEffect(() => {
    document.title = 'Terms of Service · EtGen'
  }, [])

  return (
    <LegalDocument
      title="Terms of Service"
      summary="These terms govern access to EtGen and set expectations for using its research, planning, and connected-account features."
      updated="September 29, 2026"
      sections={sections}
    />
  )
}
