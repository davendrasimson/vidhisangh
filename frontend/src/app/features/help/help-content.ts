/** User-facing help. Keep steps aligned with the feature controls when changing workflows. */
export interface HelpTopic {
  id: string;
  title: string;
  path: string;
  summary: string;
  steps: string[];
  tip: string;
  permission: string | null;
  featured: boolean;
}
export const HELP_TOPICS: HelpTopic[] = [
  {
    "id": "dashboard",
    "title": "Dashboard",
    "path": "/app/dashboard",
    "summary": "Start your day with an overview of your practice.",
    "steps": [
      "Review the dashboard cards and upcoming work.",
      "Use the navigation to open matters, documents, calendar and billing."
    ],
    "tip": "The navigation also includes My timesheets, Bare Acts and your firm’s Knowledge Library.",
    "permission": null,
    "featured": true
  },
  {
    "id": "matters",
    "title": "Matters and custom forms",
    "path": "/app/matters",
    "summary": "Create and organise cases, hearings and matter records.",
    "steps": [
      "Choose New matter, enter the case details and save.",
      "Use Fetch from eCourts to import available case information when your provider is configured.",
      "To customise forms, open Configure additional matter fields (the sliders icon). Add a section, then add fields and choose where they belong. This requires tenant management permission."
    ],
    "tip": "You can add custom fields and sections to matter forms, including sensitive fields. Ask your administrator if the configuration icon is missing.",
    "permission": "matter:read",
    "featured": true
  },
  {
    "id": "matter-board",
    "title": "Matter board",
    "path": "/app/matters/board",
    "summary": "Every open matter by stage, with its owner, next hearing, next task and what needs attention.",
    "steps": [
      "Open Board from the matters list. Columns are the stages; cards are the matters that are not closed.",
      "Each card shows the owner (lead counsel, else the assignee), the next scheduled hearing or registry date, the earliest-due open task and the limitation date.",
      "Use the chips to see only matters that need attention — a hearing today, limitation within 30 days or passed, an overdue task, no next step, or nothing touched for 30 days. Whole firm / My matters switches the view to your own."
    ],
    "tip": "The board is built from the hearings, tasks and notes you already record — keep a next hearing or an open task on every matter and nothing shows as 'No next step'.",
    "permission": "matter:read",
    "featured": false
  },
  {
    "id": "matter-detail",
    "title": "Matter workspace",
    "path": "/app/matters/:id",
    "summary": "Keep the case record and related work together.",
    "steps": [
      "Open a matter to review its details and available actions.",
      "Use Research or Bare Acts to continue from the case’s acts and sections.",
      "Review the matter’s hearings, team and linked work as your access allows."
    ],
    "tip": "Research and Bare Acts links carry case context, saving you from entering the same information again.",
    "permission": "matter:read",
    "featured": false
  },
  {
    "id": "matter-portal",
    "title": "Matter client portal",
    "path": "/app/matters/:id/portal",
    "summary": "Manage the information shared through a matter’s client portal.",
    "steps": [
      "Review the portal settings and client access for this matter.",
      "Choose the information to share before providing a client with their portal link."
    ],
    "tip": "The client portal provides a separate client-facing view of shared case information.",
    "permission": "matter:read",
    "featured": false
  },
  {
    "id": "documents",
    "title": "Documents and e-signatures",
    "path": "/app/documents",
    "summary": "Draft, upload, organise and send documents for signing.",
    "steps": [
      "Create a draft using a built-in format, or upload a file in the document workspace.",
      "For signing, open a file’s actions menu and choose Prepare for e-signature. Complete the recipients and signing setup before sending.",
      "Open E-signatures to track documents sent by you and those awaiting your signature."
    ],
    "tip": "You can collect signatures inside VidhiSangh. You can also upload your firm’s Word templates and edit their fields for reuse.",
    "permission": "document:read",
    "featured": true
  },
  {
    "id": "draft-editor",
    "title": "Document editor",
    "path": "/app/documents/drafts/:id",
    "summary": "Edit and export a draft in the full document editor.",
    "steps": [
      "Open a draft from Documents.",
      "Use the editor toolbar to format the document and review its contents.",
      "Check that your changes are saved before using Word export or Print/PDF."
    ],
    "tip": "Reusable Word templates let your firm preserve existing wording, tables and page setup.",
    "permission": "document:read",
    "featured": false
  },
  {
    "id": "calendar",
    "title": "Calendar and hearings",
    "path": "/app/calendar",
    "summary": "Plan hearings and other practice events.",
    "steps": [
      "Select the date or view you need.",
      "Create or open an event and review its time and related matter before saving."
    ],
    "tip": "Keep hearings connected to their matters so scheduling and case work stay together.",
    "permission": "hearing:read",
    "featured": true
  },
  {
    "id": "crm",
    "title": "CRM and leads",
    "path": "/app/crm",
    "summary": "Track enquiries through your intake pipeline.",
    "steps": [
      "Add an enquiry or open an existing lead.",
      "Update its details and follow-up activity.",
      "Open a lead when you are ready to convert it into a matter."
    ],
    "tip": "A lead can be converted into a matter from its detail page, avoiding a separate case-entry workflow.",
    "permission": "lead:read",
    "featured": true
  },
  {
    "id": "lead-detail",
    "title": "Lead details",
    "path": "/app/crm/:id",
    "summary": "Review an enquiry and move it toward an active matter.",
    "steps": [
      "Review the lead’s contact information and activity.",
      "Use the conversion action when the enquiry becomes a case."
    ],
    "tip": "After conversion, the Matter link takes you directly to the resulting case.",
    "permission": "lead:read",
    "featured": false
  },
  {
    "id": "clients",
    "title": "Clients and KYC",
    "path": "/app/clients",
    "summary": "Maintain individual and business client records.",
    "steps": [
      "Add a client and their contact information.",
      "Open the client record to review consent, tax defaults and KYC.",
      "Send the client a KYC form to confirm their details."
    ],
    "tip": "Clients can confirm their own details through a KYC link. Review their communication consent as well as their contact details.",
    "permission": "client:read",
    "featured": true
  },
  {
    "id": "client-detail",
    "title": "Client record",
    "path": "/app/clients/:id",
    "summary": "Review a client’s information and related work.",
    "steps": [
      "Review contact information, consent and tax defaults.",
      "Use the available KYC and related-record actions for this client."
    ],
    "tip": "GST and TDS defaults belong to the client record and help keep billing consistent.",
    "permission": "client:read",
    "featured": false
  },
  {
    "id": "billing",
    "title": "Billing and invoices",
    "path": "/app/billing",
    "summary": "Manage invoices and practice billing.",
    "steps": [
      "Open Billing and choose the relevant section.",
      "Create or open an invoice and review its client, line items and totals.",
      "Open an invoice to record receipts and review its balance."
    ],
    "tip": "Settings → Billing documents & branding lets authorised users customise firm identity, templates and numbering prefixes.",
    "permission": "invoice:read",
    "featured": true
  },
  {
    "id": "timesheets",
    "title": "My timesheets",
    "path": "/app/billing?section=timesheets",
    "summary": "Record time spent on practice work.",
    "steps": [
      "Open My timesheets from the navigation.",
      "Record time against the relevant work and review your entries."
    ],
    "tip": "Counsel rates are managed separately in Settings and can have effective dates.",
    "permission": "timeentry:read",
    "featured": true
  },
  {
    "id": "invoice-detail",
    "title": "Invoice and receipts",
    "path": "/app/billing/:id",
    "summary": "Review a billing document, balance and receipts.",
    "steps": [
      "Check the invoice details and current balance.",
      "Under Payment & receipt, enter the amount, date, method and reference, then choose Record receipt."
    ],
    "tip": "Invoices include a verification QR code. Receipts retain the payment reference or UTR for reconciliation.",
    "permission": "invoice:read",
    "featured": false
  },
  {
    "id": "payments",
    "title": "Payments",
    "path": "/app/payments",
    "summary": "Review payment activity for your practice.",
    "steps": [
      "Open Payments and review the available payment records.",
      "Check payment status and references against the associated invoice."
    ],
    "tip": "An invoice’s Payment & receipt area also supports recording bank, cash, cheque and online receipts.",
    "permission": "invoice:read",
    "featured": true
  },
  {
    "id": "research",
    "title": "Legal Research",
    "path": "/app/research",
    "summary": "Find judgments and case information.",
    "steps": [
      "Enter a query and refine the available filters.",
      "Open a judgment or case result to review its details and source material."
    ],
    "tip": "Start research from a matter’s Research link to carry over its case context.",
    "permission": "research:use",
    "featured": true
  },
  {
    "id": "cite-check",
    "title": "Cite check",
    "path": "/app/research/cite-check",
    "summary": "Verify every case citation in a draft against the judgment library.",
    "steps": [
      "Paste the text of the draft, or upload the Word (.docx) file — footnotes and tables are read too.",
      "Review each citation: Verified and Matched by name link to the record; Not found, Several possible matches and Cited by other judgments need your own check against the reporter.",
      "Download the CSV to keep with the matter file."
    ],
    "tip": "The check confirms that an authority exists, not that it supports your proposition — read the case before relying on it. SCC and AIR citations are matched by the case name and year, so name the case before the citation.",
    "permission": "research:use",
    "featured": false
  },
  {
    "id": "judgment",
    "title": "Judgment details",
    "path": "/app/research/:id",
    "summary": "Read and review a research result.",
    "steps": [
      "Review the judgment details and available source text.",
      "Check the original source and case context before relying on a result."
    ],
    "tip": "You can start a new search from a matter to include its acts and sections.",
    "permission": "research:use",
    "featured": false
  },
  {
    "id": "case",
    "title": "Case details",
    "path": "/app/research/case/:cnr",
    "summary": "Review information for a case identified by its CNR.",
    "steps": [
      "Review the case details returned by the configured provider.",
      "Check available hearing and case information against the source."
    ],
    "tip": "Fetch from eCourts in Matters can help bring available case information into your practice.",
    "permission": "research:use",
    "featured": false
  },
  {
    "id": "knowledge",
    "title": "Knowledge Library",
    "path": "/app/knowledge",
    "summary": "Build a shared library of practice resources.",
    "steps": [
      "Choose the firm library view and search or filter resources.",
      "Open a resource to read it, or add practice material with the available creation actions."
    ],
    "tip": "Save useful resources and use the saved-only filter to find them again.",
    "permission": "knowledge:read",
    "featured": true
  },
  {
    "id": "bare-acts",
    "title": "Bare Acts",
    "path": "/app/knowledge?view=acts",
    "summary": "Find legislation, guides and exact text.",
    "steps": [
      "Search or filter the acts library.",
      "Choose Read exact text for the reader or Plain-language guide for an overview.",
      "Review the status and version information for the Act."
    ],
    "tip": "Bookmark frequently used Acts and use the Bookmarks filter to return to them.",
    "permission": "knowledge:read",
    "featured": true
  },
  {
    "id": "act-reader",
    "title": "Act reader",
    "path": "/app/knowledge/reader",
    "summary": "Read legislation and inspect its context.",
    "steps": [
      "Open an Act using Read exact text.",
      "Review the available text, source and version information."
    ],
    "tip": "The reader includes a Use in a matter area to connect legislation with case work.",
    "permission": "knowledge:read",
    "featured": false
  },
  {
    "id": "news",
    "title": "Legal News",
    "path": "/app/news",
    "summary": "Browse legal news and open articles.",
    "steps": [
      "Browse the available news and use the page’s filters.",
      "Open an article to read its source."
    ],
    "tip": "Use Legal Research and Bare Acts alongside news when you need the underlying judgment or legislation.",
    "permission": null,
    "featured": true
  },
  {
    "id": "daily",
    "title": "VidhiSangh Daily",
    "path": "/app/daily",
    "summary": "One short brief every morning: a section of the new codes, a Supreme Court judgment, a question, a landmark decided on this date, legal news and who joined near you.",
    "steps": [
      "Open the page from the morning notification, the home screen card, or the menu.",
      "The lead item changes with the day of the week: section on Monday, judgment on Tuesday, question on Wednesday, On this day on Thursday, news on Friday, your fraternity on Saturday.",
      "Tap an option to answer the question; the answer, the explanation and how other members did appear at once. One attempt per question.",
      "Use the arrows at the top to read earlier days.",
      "If your profile names your court (the courts you practise in, or your headline), a Your court card shows the cause lists the court has published for today and the next listing day, with links to the court's website, eCourts and the court's group. Supreme Court and Allahabad High Court lists are read from the courts' own index pages; other High Courts link to their site. VidhiSangh opens no list and looks up no case.",
      "To get the morning message on WhatsApp as well, say yes on the Daily page or switch on \"VidhiSangh Daily on WhatsApp\" under Settings → Notifications (a verified mobile number is needed)."
    ],
    "tip": "Members without the app get the brief by email every morning (Settings → Notifications → VidhiSangh Daily by email, with a one-tap stop link in every email). Turn the morning notification off under Settings → Notifications → Push, or the WhatsApp message off under Settings → Notifications, if you would rather open the page yourself.",
    "permission": null,
    "featured": true
  },
  {
    "id": "network",
    "title": "Professional feed",
    "path": "/app/network",
    "summary": "Share updates with your professional network.",
    "steps": [
      "Browse the feed and open relevant discussions.",
      "Use the posting and interaction controls available to your account."
    ],
    "tip": "People, Groups and Messages provide other ways to continue a professional conversation.",
    "permission": null,
    "featured": true
  },
  {
    "id": "people",
    "title": "People",
    "path": "/app/people",
    "summary": "Find professionals and view their profiles.",
    "steps": [
      "Search or browse people.",
      "Open a profile to review professional details and available connection actions."
    ],
    "tip": "Complete your own profile and digital visiting card so others can recognise your practice.",
    "permission": null,
    "featured": true
  },
  {
    "id": "person",
    "title": "Professional profile",
    "path": "/app/people/:id",
    "summary": "Review a professional’s shared profile.",
    "steps": [
      "Review their professional information.",
      "Use the connection or messaging actions available on the profile."
    ],
    "tip": "Your own profile can generate a QR visiting card and downloadable vCard.",
    "permission": null,
    "featured": false
  },
  {
    "id": "groups",
    "title": "Groups",
    "path": "/app/groups",
    "summary": "Find professional communities and discussions.",
    "steps": [
      "Browse the groups available to you.",
      "Open a group to review membership and discussions.",
      "Group admins: use Get invite link and share it on WhatsApp — anyone who opens it joins at once."
    ],
    "tip": "Groups keep topic-specific discussions separate from your main feed. Reset the invite link if it was shared too widely; the old one stops working.",
    "permission": null,
    "featured": true
  },
  {
    "id": "group",
    "title": "Group workspace",
    "path": "/app/groups/:id",
    "summary": "Participate in a professional group.",
    "steps": [
      "Review the group description and membership.",
      "Read or contribute to discussions using the actions available to your role."
    ],
    "tip": "Group actions depend on membership and your role in the group.",
    "permission": null,
    "featured": false
  },
  {
    "id": "messages",
    "title": "Messages",
    "path": "/app/messages",
    "summary": "Continue direct professional conversations.",
    "steps": [
      "Select a conversation or start one using the available controls.",
      "Review your recipient and message before sending."
    ],
    "tip": "Messages are available throughout the workspace through the application’s live messaging connection.",
    "permission": null,
    "featured": true
  },
  {
    "id": "marketplace",
    "title": "Marketplace",
    "path": "/app/marketplace",
    "summary": "Browse professional service listings.",
    "steps": [
      "Browse or search listings.",
      "Open a listing to review its details and available actions."
    ],
    "tip": "Use listing details to check the scope of a service before proceeding.",
    "permission": "marketplace:read",
    "featured": true
  },
  {
    "id": "analytics",
    "title": "Analytics",
    "path": "/app/analytics",
    "summary": "Review practice performance and trends.",
    "steps": [
      "Open Analytics and select the available reporting filters.",
      "Review the displayed metrics in the context of the selected period."
    ],
    "tip": "A report’s date range matters: compare equivalent periods when assessing trends.",
    "permission": "analytics:view",
    "featured": true
  },
  {
    "id": "profile",
    "title": "My profile and visiting card",
    "path": "/app/profile",
    "summary": "Manage your professional identity.",
    "steps": [
      "Open My Profile from the account menu and review your details.",
      "Under Digital visiting card, choose Show QR or vCard."
    ],
    "tip": "Your digital visiting card is generated from your professional details; update them before sharing it.",
    "permission": null,
    "featured": true
  },
  {
    "id": "settings",
    "title": "Settings",
    "path": "/app/settings",
    "summary": "Configure your account and organisation.",
    "steps": [
      "Open a settings tile for the area you want to change.",
      "Review and save changes where the page provides a save action."
    ],
    "tip": "Some organisation settings require an administrator. Available features also depend on your plan and configuration.",
    "permission": null,
    "featured": true
  },
  {
    "id": "settings-appearance",
    "title": "Appearance",
    "path": "/app/settings/appearance",
    "summary": "Choose a comfortable workspace appearance.",
    "steps": [
      "Select a theme and accent colour."
    ],
    "tip": "The top bar also provides theme and accent controls.",
    "permission": null,
    "featured": false
  },
  {
    "id": "settings-notifications",
    "title": "Notification preferences",
    "path": "/app/settings/notifications",
    "summary": "Choose how you receive updates.",
    "steps": [
      "Review the notification channels and preferences shown on this page.",
      "Save any changes using the available control."
    ],
    "tip": "Check both the in-app notification bell and your delivery preferences.",
    "permission": null,
    "featured": false
  },
  {
    "id": "settings-security",
    "title": "Account security",
    "path": "/app/settings/security",
    "summary": "Manage sign-in protection.",
    "steps": [
      "Review the security options available to your account.",
      "Follow the on-screen instructions to enrol or manage a sign-in method."
    ],
    "tip": "Review your security settings before using a new device.",
    "permission": null,
    "featured": false
  },
  {
    "id": "settings-privacy",
    "title": "Privacy and data",
    "path": "/app/settings/privacy",
    "summary": "Manage your personal data choices.",
    "steps": [
      "Review directory visibility and available data export controls.",
      "Read the confirmation carefully before requesting account deletion or organisation offboarding."
    ],
    "tip": "Directory opt-out and data export are available here; deletion actions are separate.",
    "permission": null,
    "featured": false
  },
  {
    "id": "settings-counsel-rates",
    "title": "Counsel rates",
    "path": "/app/settings/counsel-rates",
    "summary": "Maintain billing rates for counsel.",
    "steps": [
      "Select counsel and add a rate with its effective dates.",
      "Use End today when an existing rate should stop applying."
    ],
    "tip": "Effective dates let you retain historical rates rather than overwrite them.",
    "permission": null,
    "featured": false
  },
  {
    "id": "settings-billing-branding",
    "title": "Billing documents & branding",
    "path": "/app/settings/billing-branding",
    "summary": "Customise your billing documents.",
    "steps": [
      "Choose a document template and enter firm identity.",
      "Review numbering prefixes and save your settings."
    ],
    "tip": "Templates and numbering prefixes are managed together here.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-feature-flags",
    "title": "Feature flags",
    "path": "/app/admin/feature-flags",
    "summary": "Manage feature availability.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Feature availability can also depend on the subscription and user permissions.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-subscription",
    "title": "Subscription",
    "path": "/app/admin/subscription",
    "summary": "Review the organisation’s plan.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Review plan limits when a feature is unavailable.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-users",
    "title": "Users and roles",
    "path": "/app/admin/users",
    "summary": "Manage organisation membership and access.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "A user’s role determines which navigation items and actions are available.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-audit",
    "title": "Audit log",
    "path": "/app/admin/audit",
    "summary": "Review recorded organisation activity.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Use the available filters to narrow down an event before reviewing its details.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-system",
    "title": "System settings",
    "path": "/app/admin/system",
    "summary": "Review organisation system configuration.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Provider configuration affects features such as external case lookups.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-webhooks",
    "title": "Webhooks",
    "path": "/app/admin/webhooks",
    "summary": "Configure integrations that receive event notifications.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Review an integration’s delivery information when investigating a missing event.",
    "permission": null,
    "featured": false
  },
  {
    "id": "admin-api-keys",
    "title": "API keys",
    "path": "/app/admin/api-keys",
    "summary": "Manage credentials for integrations.",
    "steps": [
      "Open this settings area with an authorised administrator account.",
      "Review the current configuration before using the available management actions."
    ],
    "tip": "Give integrations only the access they need and revoke unused keys.",
    "permission": null,
    "featured": false
  },
  {
    "id": "sign",
    "title": "Sign a document",
    "path": "/esign/:token",
    "summary": "Review and sign a document shared with you.",
    "steps": [
      "Review the document and recipient details.",
      "Follow the email verification and consent steps before completing your signature."
    ],
    "tip": "Ask the sender for a new link if this signing invitation has expired.",
    "permission": null,
    "featured": false
  },
  {
    "id": "unsubscribe",
    "title": "Stop invitation emails",
    "path": "/unsubscribe/:token",
    "summary": "Remove your address from VidhiSangh invitation emails.",
    "steps": [
      "Tap Unsubscribe to confirm.",
      "Your address goes on the do-not-email list and is never emailed again."
    ],
    "tip": "Your mail app's own Unsubscribe button works too, without opening this page.",
    "permission": null,
    "featured": false
  },
  {
    "id": "join-group",
    "title": "Join a group from an invite link",
    "path": "/join/:code",
    "summary": "Join a bar association, college or chamber group someone shared with you.",
    "steps": [
      "Open the invite link: it shows the group and how many members it has.",
      "Signed in: tap Join the group. New to VidhiSangh: sign up first and you are added as soon as you are in."
    ],
    "tip": "If the link says it has expired, ask the group's admin for a new one.",
    "permission": null,
    "featured": false
  },
  {
    "id": "kyc",
    "title": "Client KYC form",
    "path": "/kyc/:token",
    "summary": "Confirm your client details.",
    "steps": [
      "Check your details and communication preferences.",
      "Read the privacy notice and confirmation before submitting."
    ],
    "tip": "You can choose the contact channels you consent to on the form.",
    "permission": null,
    "featured": false
  },
  {
    "id": "portal",
    "title": "Client portal",
    "path": "/portal/:token",
    "summary": "View case information shared by your legal team.",
    "steps": [
      "Review the matter information and shared items.",
      "Contact your legal team if access has expired or an item is missing."
    ],
    "tip": "The portal shows information your legal team has chosen to share.",
    "permission": null,
    "featured": false
  },
  {
    "id": "pay",
    "title": "Pay an invoice",
    "path": "/pay/:token",
    "summary": "Review an invoice shared with you.",
    "steps": [
      "Check the invoice and amount due.",
      "Follow the available payment instructions."
    ],
    "tip": "Keep the payment reference for reconciliation with your legal team.",
    "permission": null,
    "featured": false
  },
  {
    "id": "verify-invoice",
    "title": "Verify an invoice",
    "path": "/verify/invoice/:code",
    "summary": "Check a billing document’s verification record.",
    "steps": [
      "Compare the displayed record with the document you received."
    ],
    "tip": "The invoice QR code opens this verification page.",
    "permission": null,
    "featured": false
  },
  {
    "id": "privacy-notice",
    "title": "Privacy notice",
    "path": "/privacy",
    "summary": "Read how personal data is handled.",
    "steps": [
      "Review the notice and its contact information."
    ],
    "tip": "Your account also has Privacy and data settings for available data choices.",
    "permission": null,
    "featured": false
  },
  {
    "id": "terms",
    "title": "Terms",
    "path": "/terms",
    "summary": "Read the terms for using VidhiSangh.",
    "steps": [
      "Review the terms and associated schedules."
    ],
    "tip": "Use the support desk if you need assistance with your account.",
    "permission": null,
    "featured": false
  },
  {
    "id": "trust",
    "title": "Security and privacy status",
    "path": "/trust",
    "summary": "Review the published security and privacy status.",
    "steps": [
      "Read the status and any stated limitations."
    ],
    "tip": "This page distinguishes available controls from work still in progress.",
    "permission": null,
    "featured": false
  },
  {
    "id": "about",
    "title": "About VidhiSangh",
    "path": "/about",
    "summary": "What VidhiSangh offers and who builds it: developed and managed by Simson Softwares Private Limited.",
    "steps": [
      "Read what the network, research and practice tools cover.",
      "Use the contact address on the page for questions, complaints or data requests."
    ],
    "tip": "VidhiSangh does not advertise or solicit work for advocates.",
    "permission": null,
    "featured": false
  },
  {
    "id": "platform-admin",
    "title": "Platform administration",
    "path": "/platform-admin",
    "summary": "Manage authorised platform operations.",
    "steps": [
      "Review the administration area available to your account.",
      "Check the target organisation before taking an action."
    ],
    "tip": "Platform administration is separate from an organisation’s Settings.",
    "permission": null,
    "featured": false
  },
  {
    "id": "app-platform-admin",
    "title": "Platform admin in the app",
    "path": "/app/platform-admin",
    "summary": "For VidhiSangh administrators: registrations and growth, members, firms, content and grievances, inside the app.",
    "steps": [
      "Open Platform admin from the menu (shown only to administrators).",
      "Start on Growth for sign-ups by day, week and month; switch sections with the tabs at the top.",
      "Give a reason when blocking a member or removing content: every action is recorded."
    ],
    "tip": "The same console is also at admin.vidhisangh.com on a computer.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-login",
    "title": "Sign in",
    "path": "/auth/login",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-register",
    "title": "Create an account",
    "path": "/auth/register",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-callback",
    "title": "Complete sign-in",
    "path": "/auth/callback",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-forgot",
    "title": "Forgot password",
    "path": "/auth/forgot",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-reset",
    "title": "Reset password",
    "path": "/auth/reset/:token",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-verify-email",
    "title": "Verify email",
    "path": "/auth/verify-email/:token",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "auth-change-password",
    "title": "Change password",
    "path": "/auth/change-password",
    "summary": "Access your VidhiSangh account.",
    "steps": [
      "Follow the instructions on this page.",
      "For an expired email link, return to sign-in and request a new link using the relevant recovery flow."
    ],
    "tip": "Never share your password, one-time codes or recovery links.",
    "permission": null,
    "featured": false
  },
  {
    "id": "help",
    "title": "Help and feature tour",
    "path": "/app/help",
    "summary": "Learn what you can do in VidhiSangh.",
    "steps": [
      "Search the help library or choose a feature below.",
      "Start the feature tour for a guided overview."
    ],
    "tip": "The Help and light-bulb buttons always explain the page you are currently using.",
    "permission": null,
    "featured": false
  }
];

/** Match complete route segments; specific detail routes win over parameter routes.
 * Only known view selectors are read. IDs, signing tokens and unrelated queries
 * never enter a help URL, storage or analytics.
 */
export function topicForUrl(url: string): HelpTopic {
  const parsed = new URL(url, 'https://help.local');
  const path = parsed.pathname.replace(/\/$/, '');
  if (path === '/help') return HELP_TOPICS.find(t => t.id === 'help')!;
  const matches = HELP_TOPICS.filter(topic => {
    const candidate = new URL(topic.path, 'https://help.local');
    const expected = candidate.pathname.split('/');
    const actual = path.split('/');
    let queryMatches = true;
    candidate.searchParams.forEach((value, key) => {
      if (parsed.searchParams.get(key) !== value) queryMatches = false;
    });
    return expected.length === actual.length && expected.every((part, i) => part.startsWith(':') || part === actual[i]) &&
      queryMatches;
  });
  matches.sort((a, b) => specificity(b.path) - specificity(a.path));
  return matches[0] ?? HELP_TOPICS.find(t => t.id === 'help')!;
}
function specificity(path: string): number {
  const url = new URL(path, 'https://help.local');
  return url.pathname.split('/').filter(part => part && !part.startsWith(':')).length * 10 + (url.search ? 1 : 0);
}
