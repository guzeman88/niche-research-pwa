import { useEffect } from 'react'
import LegalDocument from '../components/LegalDocument'

const sections = [
  {
    title: 'Information EtGen handles',
    body: (
      <>
        <p>EtGen handles the account information needed to sign you in, the research and planning information you choose to import or create, and basic technical records needed to operate and secure the service.</p>
        <p>If you connect an Etsy shop, EtGen receives the shop information and authorization data permitted by the access you approve. EtGen does not ask for or store your Etsy password.</p>
      </>
    ),
  },
  {
    title: 'How information is used',
    body: <p>Information is used to provide private keyword research, niche analysis, store and product planning, listing workflows, account support, security, and service reliability. EtGen does not sell personal information or use private workspace data for third-party advertising.</p>,
  },
  {
    title: 'Connected services',
    body: <p>EtGen relies on service providers for hosting, authentication, data storage, source control, and approved marketplace or research integrations. These providers process information only as needed to deliver their services and are subject to their own security and privacy terms.</p>,
  },
  {
    title: 'Etsy and Google data',
    body: (
      <>
        <p>Etsy data is accessed only after the seller authorizes the connection and is used for seller-controlled research, planning, reporting, and shop-management workflows.</p>
        <p>Google user data, if requested by a future user-authorized feature, will be used only to provide that feature. EtGen's use and transfer of information received from Google APIs will comply with the Google API Services User Data Policy, including its Limited Use requirements.</p>
      </>
    ),
  },
  {
    title: 'Retention and deletion',
    body: <p>Workspace information is retained while it is needed to provide the service or meet operational and legal requirements. You may disconnect an integration at its source. Requests to access, correct, export, or delete account information can be sent to the support address shown on EtGen's Google consent screen or from the account area in the app.</p>,
  },
  {
    title: 'Security',
    body: <p>EtGen uses access controls, encrypted connections, scoped authorization, and short-lived credentials where supported. No service can guarantee absolute security, so access should be limited to trusted devices and account credentials should remain private.</p>,
  },
  {
    title: 'Changes and contact',
    body: <p>This policy may be updated as EtGen adds integrations or changes how the service operates. Material changes will be reflected on this page. Privacy questions can be sent to the support address displayed on the EtGen Google consent screen.</p>,
  },
]

export default function Privacy() {
  useEffect(() => {
    document.title = 'Privacy Policy · EtGen'
  }, [])

  return (
    <LegalDocument
      title="Privacy Policy"
      summary="This policy explains what information EtGen handles, why it is used, and the controls available to people who use the service."
      updated="September 29, 2026"
      sections={sections}
    />
  )
}
