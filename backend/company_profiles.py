from typing import Any, Dict, Iterable, List


COMPANY_PROFILES: Dict[str, Dict[str, str]] = {
    "article": {
        "description": "Article designs and sells modern furniture with a focus on direct-to-consumer delivery and transparent pricing.",
        "industry": "Furniture and e-commerce",
        "website": "https://www.article.com",
        "headquarters": "Vancouver, Canada",
        "company_size": "Established private company",
    },
    "amazon": {
        "description": "Amazon is a global technology and commerce company operating online retail, AWS cloud computing, logistics, digital streaming, and consumer technology businesses.",
        "industry": "Technology, cloud computing, and e-commerce",
        "website": "https://www.amazon.com",
        "headquarters": "Seattle, United States",
        "company_size": "Enterprise",
    },
    "apple": {
        "description": "Apple designs consumer hardware, software, and services including iPhone, Mac, iOS, macOS, and Apple services.",
        "industry": "Consumer technology",
        "website": "https://www.apple.com",
        "headquarters": "Cupertino, United States",
        "company_size": "Enterprise",
    },
    "cfc": {
        "description": "CFC is a specialist insurance provider that develops technology-enabled commercial insurance products for businesses and brokers.",
        "industry": "Insurance and financial services",
        "website": "https://www.cfc.com",
        "headquarters": "London, United Kingdom",
        "company_size": "Established private company",
    },
    "cloudflare": {
        "description": "Cloudflare provides connectivity, security, performance, and developer services that help organisations operate applications and networks on the Internet.",
        "industry": "Internet infrastructure and cybersecurity",
        "website": "https://www.cloudflare.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Public technology company",
    },
    "cloudtalk": {
        "description": "CloudTalk provides cloud-based business calling and contact-centre software for sales and customer-support teams.",
        "industry": "Cloud communications and customer support software",
        "website": "https://www.cloudtalk.io",
        "headquarters": "Bratislava, Slovakia",
        "company_size": "Growth-stage private company",
    },
    "databricks": {
        "description": "Databricks provides a Data Intelligence Platform that brings together data engineering, analytics, machine learning, and generative AI for organisations.",
        "industry": "Data, cloud software, and artificial intelligence",
        "website": "https://www.databricks.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Enterprise technology company",
    },
    "docker": {
        "description": "Docker builds tools and services that help developers package, share, and run applications using containers.",
        "industry": "Developer tools and cloud software",
        "website": "https://www.docker.com",
        "headquarters": "Palo Alto, United States",
        "company_size": "Established private company",
    },
    "embraer": {
        "description": "Embraer designs and manufactures commercial, executive, and defence aircraft and provides aviation services worldwide.",
        "industry": "Aerospace and aviation",
        "website": "https://www.embraer.com",
        "headquarters": "São José dos Campos, Brazil",
        "company_size": "Global industrial company",
    },
    "figma": {
        "description": "Figma develops collaborative design and product-development tools that allow teams to create, prototype, and manage digital experiences together.",
        "industry": "Design software and collaboration tools",
        "website": "https://www.figma.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Established private technology company",
    },
    "freeup": {
        "description": "FreeUp connects businesses with vetted freelance professionals for operational, administrative, creative, and e-commerce work.",
        "industry": "Staffing and freelance services",
        "website": "https://freeup.net",
        "headquarters": "United States",
        "company_size": "Private company",
    },
    "google": {
        "description": "Google develops Search, Android, YouTube, Google Cloud, advertising, and other products and infrastructure used by people and organisations worldwide.",
        "industry": "Internet technology and cloud computing",
        "website": "https://about.google",
        "headquarters": "Mountain View, United States",
        "company_size": "Enterprise",
    },
    "linear": {
        "description": "Linear develops issue tracking and product-management software designed for modern software and product teams.",
        "industry": "Productivity and developer software",
        "website": "https://linear.app",
        "headquarters": "San Francisco, United States",
        "company_size": "Private technology company",
    },
    "meta": {
        "description": "Meta builds social, communication, virtual-reality, and augmented-reality products including Facebook, Instagram, WhatsApp, and Messenger.",
        "industry": "Social technology and digital media",
        "website": "https://about.meta.com",
        "headquarters": "Menlo Park, United States",
        "company_size": "Enterprise",
    },
    "nvidia": {
        "description": "NVIDIA develops accelerated computing platforms, graphics processors, networking technology, and AI software for gaming, data centres, and professional applications.",
        "industry": "Semiconductors and artificial intelligence",
        "website": "https://www.nvidia.com",
        "headquarters": "Santa Clara, United States",
        "company_size": "Enterprise",
    },
    "notion": {
        "description": "Notion provides a connected workspace for notes, documents, project management, wikis, and team knowledge.",
        "industry": "Productivity and collaboration software",
        "website": "https://www.notion.so",
        "headquarters": "San Francisco, United States",
        "company_size": "Private technology company",
    },
    "oracle corporation": {
        "description": "Oracle provides database technology, cloud infrastructure, enterprise applications, and business software for organisations worldwide.",
        "industry": "Enterprise software and cloud computing",
        "website": "https://www.oracle.com",
        "headquarters": "Austin, United States",
        "company_size": "Enterprise",
    },
    "ramp": {
        "description": "Ramp provides corporate cards, expense management, bill payment, and financial operations software for businesses.",
        "industry": "Fintech and business financial software",
        "website": "https://ramp.com",
        "headquarters": "New York, United States",
        "company_size": "Growth-stage private company",
    },
    "reddit": {
        "description": "Reddit operates a community platform where people share, discuss, and discover content across thousands of interest-based communities.",
        "industry": "Social media and online communities",
        "website": "https://www.redditinc.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Public technology company",
    },
    "salesforce": {
        "description": "Salesforce provides cloud-based customer relationship management software and applications for sales, service, marketing, analytics, and collaboration.",
        "industry": "Enterprise software and customer relationship management",
        "website": "https://www.salesforce.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Enterprise",
    },
    "spotify": {
        "description": "Spotify provides audio streaming for music, podcasts, and other audio content, supported by personalised discovery and creator tools.",
        "industry": "Audio streaming and digital media",
        "website": "https://www.spotify.com",
        "headquarters": "Stockholm, Sweden",
        "company_size": "Global public technology company",
    },
    "stripe": {
        "description": "Stripe builds financial infrastructure and payment software that businesses use to accept payments, manage revenue, and launch internet businesses.",
        "industry": "Fintech and payments",
        "website": "https://stripe.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Global private technology company",
    },
    "switchboard": {
        "description": "Switchboard provides collaborative online workspaces that help teams bring documents, applications, and conversations together.",
        "industry": "Collaboration software",
        "website": "https://www.switchboard.app",
        "headquarters": "United States",
        "company_size": "Private technology company",
    },
    "target": {
        "description": "Target is a major general merchandise retailer operating stores and digital commerce services across the United States.",
        "industry": "Retail and e-commerce",
        "website": "https://corporate.target.com",
        "headquarters": "Minneapolis, United States",
        "company_size": "Enterprise",
    },
    "twitch": {
        "description": "Twitch is a live-streaming service focused on gaming, creative content, music, and online communities.",
        "industry": "Live streaming and digital media",
        "website": "https://www.twitch.tv",
        "headquarters": "San Francisco, United States",
        "company_size": "Large technology company",
    },
    "webox": {
        "description": "WeBox provides digital services and software solutions for businesses and their online operations.",
        "industry": "Digital services and software",
        "website": "https://webox.io",
        "headquarters": "United States",
        "company_size": "Private company",
    },
    "zapier": {
        "description": "Zapier provides automation software that connects web applications and helps teams automate repetitive workflows without building integrations from scratch.",
        "industry": "Automation and productivity software",
        "website": "https://zapier.com",
        "headquarters": "San Francisco, United States",
        "company_size": "Large private technology company",
    },
}


def _profile_key(company: Any) -> str:
    return str(company or "").strip().casefold()


def get_company_profile(company: Any) -> Dict[str, str]:
    return dict(COMPANY_PROFILES.get(_profile_key(company), {}))


def enrich_jobs_with_company_profiles(jobs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for job in jobs:
        profile = get_company_profile(job.get("company"))
        enriched.append({
            **job,
            "company_description": job.get("company_description") or profile.get("description"),
            "industry": job.get("industry") or profile.get("industry"),
            "company_website": job.get("company_website") or profile.get("website"),
            "company_headquarters": job.get("company_headquarters") or profile.get("headquarters"),
            "company_size": job.get("company_size") or profile.get("company_size"),
        })
    return enriched
