"""The courts VidhiSangh follows: one entry per official court group (``groups/official.py``).

Public facts only: the court's website and the page where it publishes its
cause lists. Nothing here, and nothing the fetchers read, concerns a member or a
party: the job takes the cause-list **index** (which lists exist for which
day), never opens a list, and never submits a party, counsel or AOR search.

``fetcher`` names how the index is read (``courts/fetch.py``); courts without
one get a link-only card. Website addresses were checked on 16 November 2026;
the eCourts High Court services page is the fallback that covers every High
Court (its cause-list search is CAPTCHA-protected, so members open it
themselves).
"""

from __future__ import annotations

from dataclasses import dataclass

ECOURTS_HC = "https://hcservices.ecourts.gov.in/hcservices/main.php"


@dataclass(frozen=True)
class Court:
    slug: str            # the official group's slug
    name: str
    website: str
    cause_list_url: str  # where members open the lists
    fetcher: str | None = None  # sci | allahabad


COURTS: tuple[Court, ...] = (
    Court("supreme-court-of-india", "Supreme Court of India", "https://www.sci.gov.in/",
          "https://www.sci.gov.in/cause-list/", "sci"),
    Court("allahabad-high-court", "Allahabad High Court", "https://www.allahabadhighcourt.in/",
          "https://www.allahabadhighcourt.in/causelist/", "allahabad"),
    Court("delhi-high-court", "Delhi High Court", "https://delhihighcourt.nic.in/", "https://delhihighcourt.nic.in/"),
    Court("punjab-and-haryana-high-court", "Punjab & Haryana High Court", "https://www.phhc.gov.in/", "https://www.phhc.gov.in/"),
    Court("bombay-high-court", "Bombay High Court", "https://bombayhighcourt.nic.in/", "https://bombayhighcourt.nic.in/"),
    Court("madras-high-court", "Madras High Court", "https://www.hcmadras.tn.gov.in/", "https://www.hcmadras.tn.gov.in/"),
    Court("karnataka-high-court", "Karnataka High Court", "https://karnatakajudiciary.kar.nic.in/",
          "https://karnatakajudiciary.kar.nic.in/"),
    Court("calcutta-high-court", "Calcutta High Court", "https://www.calcuttahighcourt.gov.in/",
          "https://www.calcuttahighcourt.gov.in/"),
    Court("gujarat-high-court", "Gujarat High Court", "https://gujarathighcourt.nic.in/", "https://gujarathighcourt.nic.in/"),
    Court("rajasthan-high-court", "Rajasthan High Court", "https://hcraj.nic.in/", "https://hcraj.nic.in/"),
    Court("madhya-pradesh-high-court", "Madhya Pradesh High Court", "https://mphc.gov.in/", "https://mphc.gov.in/"),
    Court("chhattisgarh-high-court", "Chhattisgarh High Court", "https://highcourt.cg.gov.in/", "https://highcourt.cg.gov.in/"),
    Court("patna-high-court", "Patna High Court", "https://patnahighcourt.gov.in/", "https://patnahighcourt.gov.in/"),
    Court("jharkhand-high-court", "Jharkhand High Court", "https://jharkhandhighcourt.nic.in/",
          "https://jharkhandhighcourt.nic.in/"),
    Court("orissa-high-court", "Orissa High Court", "https://www.orissahighcourt.nic.in/", "https://www.orissahighcourt.nic.in/"),
    Court("telangana-high-court", "Telangana High Court", "https://tshc.gov.in/", "https://tshc.gov.in/"),
    Court("andhra-pradesh-high-court", "Andhra Pradesh High Court", "https://aphc.gov.in/", "https://aphc.gov.in/"),
    Court("kerala-high-court", "Kerala High Court", "https://hckerala.gov.in/", "https://hckerala.gov.in/"),
    Court("gauhati-high-court", "Gauhati High Court", "https://ghconline.gov.in/", "https://ghconline.gov.in/"),
    Court("jammu-kashmir-ladakh-high-court", "High Court of J&K and Ladakh", "https://jkhighcourt.nic.in/",
          "https://jkhighcourt.nic.in/"),
    Court("himachal-pradesh-high-court", "Himachal Pradesh High Court", "https://hphighcourt.nic.in/", "https://hphighcourt.nic.in/"),
    Court("uttarakhand-high-court", "Uttarakhand High Court", "https://highcourtofuttarakhand.gov.in/",
          "https://highcourtofuttarakhand.gov.in/"),
    Court("tripura-high-court", "Tripura High Court", "https://thc.nic.in/", "https://thc.nic.in/"),
    Court("meghalaya-high-court", "Meghalaya High Court", "https://meghalayahighcourt.nic.in/",
          "https://meghalayahighcourt.nic.in/"),
    Court("manipur-high-court", "Manipur High Court", "https://hcmimphal.nic.in/", "https://hcmimphal.nic.in/"),
    Court("sikkim-high-court", "Sikkim High Court", "https://hcs.gov.in/", "https://hcs.gov.in/"),
)

BY_SLUG: dict[str, Court] = {c.slug: c for c in COURTS}
